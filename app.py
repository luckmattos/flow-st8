"""flow-st8 application orchestrator."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np

import audio_feedback as feedback
from config import Config
from hotkey import HOTKEY_STOP_ID, HotkeyManager
from injector import TextInjector
from recorder import AudioRecorder
from transcriber import Transcriber
from tray import TrayIcon
from vad import SileroVAD

log = logging.getLogger(__name__)


class FlowSt8App:
    def __init__(self, config: Config):
        self.config = config
        self._state = "idle"
        self._state_lock = threading.Lock()

        # Components
        self.transcriber = Transcriber(config.model)
        self.recorder = AudioRecorder(config.audio)
        self.vad = SileroVAD() if config.vad.enabled else None
        self.injector = TextInjector(config.injection)
        self.hotkey = HotkeyManager(self._build_hotkey_bindings())
        self.tray = TrayIcon(self)

        self._executor = ThreadPoolExecutor(max_workers=2)

    def start(self) -> None:
        """Start background services. Call tray.run() after this (blocks main thread)."""
        self._executor.submit(self.transcriber.preload)
        if self.vad:
            self._executor.submit(self.vad.preload)
        self.hotkey.start()
        log.info("flow-st8 started. Press %s to record.", self.config.hotkey.key)

    def shutdown(self) -> None:
        """Clean shutdown."""
        self.hotkey.stop()
        self._executor.shutdown(wait=False)
        log.info("flow-st8 stopped.")

    def on_hotkey(self) -> None:
        """Called from tray menu action."""
        self._handle_main_hotkey()

    def _build_hotkey_bindings(self) -> list[tuple[str, Callable[[], None]]]:
        bindings = [(self.config.hotkey.key, self._handle_main_hotkey)]
        return bindings

    def _handle_main_hotkey(self) -> None:
        with self._state_lock:
            if self.config.hotkey.mode == "constant":
                if self._state == "idle":
                    if self.hotkey.register_hotkey(
                        self.config.hotkey.stop_key,
                        self._handle_stop_hotkey,
                        HOTKEY_STOP_ID,
                    ):
                        self._state = "recording"
                        self._executor.submit(self._recording_pipeline)
                    else:
                        log.error("Unable to register stop key '%s'", self.config.hotkey.stop_key)
            else:
                if self._state == "idle":
                    self._state = "recording"
                    self._executor.submit(self._recording_pipeline)
                elif self._state == "recording":
                    self.recorder.stop()

    def _handle_stop_hotkey(self) -> None:
        with self._state_lock:
            if self._state == "recording":
                self.recorder.stop()

    def _recording_pipeline(self) -> None:
        """Full pipeline: record -> VAD-trim -> transcribe -> inject."""
        try:
            self.tray.set_state("recording")
            if self.config.feedback.enabled:
                feedback.beep_start()

            if self.vad:
                self.vad.reset()

            audio = self._collect_audio()

            # Need at least 0.3s of audio (4800 samples at 16kHz)
            if audio is None or len(audio) < 4800:
                log.info("Recording too short, ignoring.")
                self._reset_to_idle()
                return

            self.tray.set_state("processing")
            if self.config.feedback.enabled:
                feedback.beep_stop()

            audio = self._apply_audio_boost(audio)
            log.info("Transcribing %d samples (%.1fs)...", len(audio), len(audio) / 16000)
            text = self.transcriber.transcribe(audio)

            if text:
                log.info("Transcribed: %s", text[:80])
                success = self.injector.inject(text)
                if self.config.feedback.enabled:
                    feedback.beep_done() if success else feedback.beep_error()
            else:
                log.info("No speech detected.")
                if self.config.feedback.enabled:
                    feedback.beep_error()

        except Exception:
            log.exception("Error in recording pipeline")
            self.tray.set_state("error")
            if self.config.feedback.enabled:
                feedback.beep_error()
        finally:
            self._reset_to_idle()

    def _collect_audio(self) -> np.ndarray | None:
        """Record until user stops. Drop silence, keep only speech segments (with padding)."""
        from collections import deque

        # Without VAD we can't detect silence — keep everything.
        if not self.vad:
            chunks = list(self.recorder.record_stream())
            return np.concatenate(chunks) if chunks else None

        chunk_ms = self.config.audio.chunk_ms
        pre_pad = max(1, 300 // chunk_ms)   # ~300ms leading padding
        post_pad = max(1, 500 // chunk_ms)  # ~500ms trailing padding
        speech_threshold = self.config.vad.speech_threshold

        warn_at_chunks = max(1, (self.config.audio.max_seconds - 15) * 1000 // chunk_ms)
        warned = False
        elapsed_chunks = 0

        prebuffer: deque[np.ndarray] = deque(maxlen=pre_pad)
        kept: list[np.ndarray] = []
        in_speech = False
        silence_run = 0
        has_prior_speech = False
        separator = np.zeros(
            int(self.config.audio.sample_rate * 0.2), dtype=np.float32
        )

        for chunk in self.recorder.record_stream():
            elapsed_chunks += 1
            if not warned and elapsed_chunks >= warn_at_chunks:
                warned = True
                if self.config.feedback.enabled:
                    feedback.beep_warning()

            is_speech = self.vad.is_speech(chunk) > speech_threshold

            if is_speech:
                if not in_speech:
                    if has_prior_speech:
                        kept.append(separator)
                    kept.extend(prebuffer)
                    prebuffer.clear()
                    in_speech = True
                    has_prior_speech = True
                kept.append(chunk)
                silence_run = 0
            else:
                if in_speech:
                    kept.append(chunk)
                    silence_run += 1
                    if silence_run >= post_pad:
                        in_speech = False
                        silence_run = 0
                else:
                    prebuffer.append(chunk)

        if not kept:
            return None
        return np.concatenate(kept)

    def _apply_audio_boost(self, audio: np.ndarray) -> np.ndarray:
        """Apply internal gain to make quiet recordings louder."""
        gain = getattr(self.config.audio, "gain", 1.0)
        if gain == 1.0:
            return audio

        peak = float(np.max(np.abs(audio)))
        if peak <= 0.0:
            return audio

        boosted = audio * gain
        boosted = np.clip(boosted, -1.0, 1.0)
        if gain != 1.0:
            log.info("Applied audio gain %.2fx (peak %.4f -> %.4f)", gain, peak, float(np.max(np.abs(boosted))))
        return boosted

    def _reset_to_idle(self) -> None:
        with self._state_lock:
            self._state = "idle"
        if self.config.hotkey.mode == "constant":
            self.hotkey.unregister_hotkey(HOTKEY_STOP_ID)
        self.tray.set_state("idle")
