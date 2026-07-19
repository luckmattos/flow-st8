"""flow-st8 application orchestrator."""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import numpy as np

import audio_feedback as feedback
from config import Config, save_config
from hotkey import HotkeyManager, check_combo_conflict
from injector import TextInjector
from overlay import WaveOverlay
from recorder import AudioRecorder
from transcriber import Transcriber
from tray import TrayIcon
from vad import SileroVAD

log = logging.getLogger(__name__)

_STREAM_THRESHOLD = 15 * 16000  # 15s in samples — trigger partial flush
_HOLD_DELAY = 0.5               # seconds to hold before recording starts


class FlowSt8App:
    def __init__(self, config: Config):
        self.config = config
        self._state = "idle"
        self._recording_mode = "idle"  # "idle" | "pending_hold" | "hold" | "toggle"
        self._state_lock = threading.Lock()
        self._hold_timer: threading.Timer | None = None

        # Components
        self.transcriber = Transcriber(config.model)
        self.recorder = AudioRecorder(config.audio)
        self.vad = SileroVAD() if config.vad.enabled else None
        self.injector = TextInjector(config.injection)
        self.hotkey = HotkeyManager(self._build_hotkey_bindings())
        self.tray = TrayIcon(self)

        self._executor = ThreadPoolExecutor(max_workers=4)
        self._model_loading = False
        self.overlay = WaveOverlay()

    def start(self) -> None:
        """Start background services. Call tray.run() after this (blocks main thread)."""
        self._model_loading = True
        self.tray.set_state("processing")
        self.tray.set_title("flow-st8 — Loading model...")
        self.overlay.show_loading()
        self._executor.submit(self._preload_with_feedback)
        if self.vad:
            self._executor.submit(self.vad.preload)
        self.hotkey.start()
        log.info("flow-st8 started. Press %s to record.", self.config.hotkey.key)

    def _preload_with_feedback(self) -> None:
        """Load the Whisper model at startup, showing a loading badge until ready."""
        try:
            self.transcriber.preload()
        finally:
            self._model_loading = False
            self.overlay.hide()
            self.tray.set_state("idle")

    @property
    def is_model_loading(self) -> bool:
        return self._model_loading

    def switch_model(self, name: str) -> None:
        if name == self.config.model.name:
            return
        self._model_loading = True
        self.tray.set_state("processing")
        self.config.model.name = name
        save_config(self.config)
        self.overlay.show_loading()
        self._executor.submit(self._reload_model)

    def _reload_model(self) -> None:
        self.transcriber.reload(self.config.model)
        self._model_loading = False
        self.overlay.hide()
        self.tray.set_state("idle")

    def shutdown(self) -> None:
        """Clean shutdown."""
        self.hotkey.stop()
        self._executor.shutdown(wait=False)
        log.info("flow-st8 stopped.")

    def on_hotkey(self) -> None:
        """Called from tray menu 'Gravar / Parar'."""
        with self._state_lock:
            if self._recording_mode == "idle":
                self._recording_mode = "toggle"
                self._state = "recording"
                self._executor.submit(self._recording_pipeline)
            elif self._recording_mode in ("hold", "toggle"):
                self._recording_mode = "idle"
                self.recorder.stop()

    def _build_hotkey_bindings(self) -> list[tuple[str, str, Callable[[], None]]]:
        return [
            ("hold_down", self.config.hotkey.hold_key, self._handle_hold_start),
            ("hold_up",   self.config.hotkey.hold_key, self._handle_hold_stop),
            ("toggle",    self.config.hotkey.toggle_key, self._handle_toggle_event),
        ]

    # --- hold / toggle handlers ---

    def _handle_hold_start(self) -> None:
        with self._state_lock:
            if self._recording_mode != "idle":
                return
            self._recording_mode = "pending_hold"
            t = threading.Timer(_HOLD_DELAY, self._start_hold_after_delay)
            self._hold_timer = t
        t.start()

    def _start_hold_after_delay(self) -> None:
        with self._state_lock:
            if self._recording_mode != "pending_hold":
                return
            self._hold_timer = None
            self._recording_mode = "hold"
            self._state = "recording"
        self._executor.submit(self._recording_pipeline)

    def _handle_hold_stop(self) -> None:
        timer = None
        with self._state_lock:
            if self._recording_mode == "pending_hold":
                timer = self._hold_timer
                self._hold_timer = None
                self._recording_mode = "idle"
            elif self._recording_mode == "hold":
                self._recording_mode = "idle"
                self.recorder.stop()
            # if "toggle" — releasing ctrl+win doesn't stop (transition already occurred)
        if timer:
            timer.cancel()

    def _handle_toggle_event(self) -> None:
        """ctrl+win+o: start toggle, stop toggle, or transition hold→toggle."""
        timer = None
        start_pipeline = False
        with self._state_lock:
            if self._recording_mode == "idle":
                self._recording_mode = "toggle"
                self._state = "recording"
                start_pipeline = True
            elif self._recording_mode == "pending_hold":
                # Pressed 'o' before 0.5s hold → cancel timer, start toggle
                timer = self._hold_timer
                self._hold_timer = None
                self._recording_mode = "toggle"
                self._state = "recording"
                start_pipeline = True
            elif self._recording_mode == "hold":
                # Pressed 'o' while recording in hold → switch to toggle
                self._recording_mode = "toggle"
            elif self._recording_mode == "toggle":
                self._recording_mode = "idle"
                self.recorder.stop()
        if timer:
            timer.cancel()
        if start_pipeline:
            self._executor.submit(self._recording_pipeline)

    def _handle_stop_hotkey(self) -> None:
        with self._state_lock:
            if self._state == "recording":
                self.recorder.stop()

    # --- hotkey capture ---

    def start_hotkey_capture(self, target: str) -> None:
        """target: 'hold' or 'toggle'."""
        with self._state_lock:
            if self._recording_mode in ("hold", "toggle", "pending_hold"):
                if self._hold_timer:
                    self._hold_timer.cancel()
                    self._hold_timer = None
                self._recording_mode = "idle"
                self._state = "idle"
        self.recorder.stop()
        self.tray.set_state("idle")

        if target == "toggle":
            hold = self.config.hotkey.hold_key
            msg = f"Hold {hold}, press new toggle key (Esc cancels)"
        else:
            msg = "Press new hold combo (Esc cancels)"
        self.overlay.show_message(msg)
        self.hotkey.capture_next_combo(
            on_captured=lambda key: self._on_hotkey_captured(key, target),
            on_cancel=self.overlay.hide,
        )

    def _on_hotkey_captured(self, new_key: str, target: str) -> None:
        self.overlay.hide()

        warning = check_combo_conflict(new_key)
        if warning and "reserved by the system" in warning:
            self.tray.notify(warning)
            return

        _MODS = {"ctrl", "control", "win", "super", "shift", "alt"}

        if target == "hold":
            non_mod = {p.strip().lower() for p in new_key.split("+")} - _MODS
            if non_mod:
                self.tray.notify(
                    f"Hold must be modifier keys only (e.g. ctrl+win). Got: {new_key}"
                )
                return

        if target == "toggle":
            hold_parts = {p.strip().lower() for p in self.config.hotkey.hold_key.split("+")}
            new_parts = {p.strip().lower() for p in new_key.split("+")}
            if not hold_parts <= new_parts:
                missing = hold_parts - new_parts
                self.tray.notify(
                    f"Toggle must include hold keys ({self.config.hotkey.hold_key}). "
                    f"Missing: {', '.join(sorted(missing))}"
                )
                return
            extra_non_mod = (new_parts - hold_parts) - _MODS
            if not extra_non_mod:
                self.tray.notify(
                    f"Toggle needs one extra key beyond hold. "
                    f"Example: {self.config.hotkey.hold_key}+o"
                )
                return

        prev_hold = self.config.hotkey.hold_key
        prev_toggle = self.config.hotkey.toggle_key

        if target == "hold":
            self.config.hotkey.hold_key = new_key
        else:
            self.config.hotkey.toggle_key = new_key

        save_config(self.config)
        ok = self.hotkey.update_bindings(self._build_hotkey_bindings())

        if ok:
            label = "Hold" if target == "hold" else "Toggle"
            msg = f"{label} hotkey: {new_key}"
            if warning:
                msg += f"\n{warning}"
            self.tray.notify(msg)
        else:
            self.config.hotkey.hold_key = prev_hold
            self.config.hotkey.toggle_key = prev_toggle
            save_config(self.config)
            self.hotkey.update_bindings(self._build_hotkey_bindings())
            self.tray.notify(f"Conflict: '{new_key}' is already in use. Try another shortcut.")

    def _recording_pipeline(self) -> None:
        """Full pipeline: record -> VAD-trim -> transcribe -> inject."""
        from concurrent.futures import Future

        self.overlay.show()
        try:
            self.tray.set_state("recording")
            if self.config.feedback.enabled:
                feedback.beep_start()

            if self.vad:
                self.vad.reset()

            partial_futures: list[Future] = []
            last_text: list[str] = [""]

            def on_flush(segment: np.ndarray) -> None:
                context = last_text[0][-50:] if last_text[0] else None
                log.info("Flushing partial segment (%d samples)...", len(segment))
                f = self._executor.submit(self.transcriber.transcribe, segment, context)
                partial_futures.append(f)

            audio = self._collect_audio(flush_callback=on_flush)

            self.tray.set_state("processing")
            if self.config.feedback.enabled:
                feedback.beep_stop()

            # Gather partial results (may still be running in background)
            partial_texts: list[str] = []
            for f in partial_futures:
                t = f.result()
                if t:
                    partial_texts.append(t)
                    last_text[0] = t

            # Transcribe remaining audio (after last flush, or full audio if no flush)
            if audio is not None and len(audio) >= 4800:
                audio = self._apply_audio_boost(audio)
                context = last_text[0][-50:] if last_text[0] else None
                log.info("Transcribing %d samples (%.1fs)...", len(audio), len(audio) / 16000)
                final = self.transcriber.transcribe(audio, context)
                if final:
                    partial_texts.append(final)
            elif not partial_texts:
                log.info("Recording too short, ignoring.")
                self._reset_to_idle()
                return

            text = " ".join(t for t in partial_texts if t)

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
            self.overlay.hide()
            self._reset_to_idle()

    def _collect_audio(
        self, flush_callback: "Callable[[np.ndarray], None] | None" = None
    ) -> np.ndarray | None:
        """Record until user stops. Drop silence, keep only speech segments (with padding).

        flush_callback: if provided and VAD is active, called with a boosted segment
        whenever accumulated audio exceeds _STREAM_THRESHOLD after a natural silence break.
        The returned audio contains only what remains after the last flush.
        """
        from collections import deque

        # Without VAD: no flush (can't detect natural silence breaks)
        if not self.vad:
            chunks = []
            for chunk in self.recorder.record_stream():
                self.overlay.push_chunk(chunk, True)
                chunks.append(chunk)
            return np.concatenate(chunks) if chunks else None

        chunk_ms = self.config.audio.chunk_ms
        pre_pad = max(1, 300 // chunk_ms)   # ~300ms leading padding
        post_pad = max(1, 500 // chunk_ms)  # ~500ms trailing padding
        speech_threshold = self.config.vad.speech_threshold

        warn_at_chunks = max(1, (self.config.audio.max_seconds - 15) * 1000 // chunk_ms)
        handsfree_at_chunks = max(1, 15000 // chunk_ms)
        warned = False
        handsfree_notified = False
        elapsed_chunks = 0

        prebuffer: deque[np.ndarray] = deque(maxlen=pre_pad)
        kept: list[np.ndarray] = []
        kept_samples = 0
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

            if not handsfree_notified and elapsed_chunks >= handsfree_at_chunks:
                handsfree_notified = True
                with self._state_lock:
                    is_hold = self._recording_mode == "hold"
                if is_hold:
                    toggle_key = self.config.hotkey.toggle_key
                    self.overlay.show_hint(f"{toggle_key} → hands-free")

            is_speech = self.vad.is_speech(chunk) > speech_threshold
            self.overlay.push_chunk(chunk, is_speech)

            if is_speech:
                if not in_speech:
                    if has_prior_speech:
                        kept.append(separator)
                        kept_samples += len(separator)
                    kept.extend(prebuffer)
                    kept_samples += sum(len(c) for c in prebuffer)
                    prebuffer.clear()
                    in_speech = True
                    has_prior_speech = True
                kept.append(chunk)
                kept_samples += len(chunk)
                silence_run = 0
            else:
                if in_speech:
                    kept.append(chunk)
                    kept_samples += len(chunk)
                    silence_run += 1
                    if silence_run >= post_pad:
                        in_speech = False
                        silence_run = 0
                        # Flush if we've accumulated enough for a partial transcription
                        if flush_callback and kept_samples >= _STREAM_THRESHOLD:
                            segment = self._apply_audio_boost(np.concatenate(kept))
                            flush_callback(segment)
                            kept.clear()
                            kept_samples = 0
                            has_prior_speech = False
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
        timer = None
        with self._state_lock:
            self._state = "idle"
            self._recording_mode = "idle"
            timer = self._hold_timer
            self._hold_timer = None
        if timer:
            timer.cancel()
        self.tray.set_state("idle")
