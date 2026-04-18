"""Whisper transcription wrapper with lazy loading."""

import logging
import re
import threading

import numpy as np
import torch
import whisper

from config import ModelConfig

log = logging.getLogger(__name__)


class Transcriber:
    def __init__(self, config: ModelConfig):
        self._config = config
        self._model: whisper.Whisper | None = None
        self._lock = threading.Lock()
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._use_fp16 = self._device == "cuda"

    def preload(self) -> None:
        """Load model in advance (call from background thread at startup)."""
        log.info(
            "Loading Whisper model '%s' on %s...",
            self._config.name,
            self._device.upper(),
        )
        with self._lock:
            if self._model is None:
                self._model = whisper.load_model(
                    self._config.name, device=self._device
                )
        log.info("Whisper model loaded.")

    def _ensure_loaded(self) -> None:
        if self._model is None:
            self.preload()

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe float32 16kHz mono audio. Returns cleaned text."""
        self._ensure_loaded()

        # Energy check - reject if audio is essentially silent.
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.005:
            log.info("Audio RMS too low (%.5f), skipping transcription.", rms)
            return ""

        audio = _trim_trailing_silence(audio)

        with self._lock:
            result = whisper.transcribe(
                self._model,
                audio,
                language=self._config.language,
                fp16=self._use_fp16,
                task="transcribe",
                initial_prompt=self._config.initial_prompt or None,
                # condition_on_previous_text=False prevents the decoder feedback
                # loop that causes repetitive hallucinations on trailing silence.
                condition_on_previous_text=False,
                no_speech_threshold=0.6,
                logprob_threshold=-1.0,
                compression_ratio_threshold=2.4,
                temperature=(0.0,),
            )

        segments = result.get("segments", [])
        good_segments = [
            s for s in segments if s.get("no_speech_prob", 0.0) < 0.6
        ]

        if not good_segments:
            return ""

        text = " ".join(s["text"].strip() for s in good_segments).strip()
        return _postprocess(text)


def _trim_trailing_silence(
    audio: np.ndarray, sample_rate: int = 16000, threshold: float = 0.01
) -> np.ndarray:
    """Remove trailing silence to reduce hallucination surface."""
    window = sample_rate // 10  # 100ms windows
    for i in range(len(audio) - window, 0, -window):
        if np.abs(audio[i : i + window]).mean() > threshold:
            return audio[: i + window]
    return audio


def _remove_repetition_loops(text: str) -> str:
    """Remove trailing repetition loops — a Whisper hallucination artifact."""
    pattern = r"(.{10,}?)(?:\1){2,}$"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        text = text[: match.start()] + match.group(1)
    return text.strip()


def _postprocess(text: str) -> str:
    """Light cleanup of transcribed text."""
    if not text:
        return text
    while "  " in text:
        text = text.replace("  ", " ")
    text = _remove_repetition_loops(text)
    text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
    return text.strip()
