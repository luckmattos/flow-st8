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
        # When language == "auto", detection is restricted to these only.
        self._allowed_langs = ("pt", "en")

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

    def reload(self, new_config: "ModelConfig") -> None:
        """Swap model in-place (call from background thread)."""
        log.info("Reloading Whisper model '%s'...", new_config.name)
        with self._lock:
            self._model = None
            self._config = new_config
        self.preload()

    def _ensure_loaded(self) -> None:
        if self._model is None:
            self.preload()

    def _detect_restricted_lang(self, audio: np.ndarray) -> str:
        """Detect language but restrict the choice to self._allowed_langs.

        Whisper has no native way to limit auto-detect to a subset, so we read
        the full language-probability distribution and pick the most likely
        among the allowed set. Anything else (e.g. Arabic) can never be chosen.
        """
        try:
            mel = whisper.log_mel_spectrogram(
                whisper.pad_or_trim(audio),
                n_mels=self._model.dims.n_mels,
            ).to(self._model.device)
            if self._use_fp16:
                mel = mel.half()
            _, probs = self._model.detect_language(mel)
            best = max(self._allowed_langs, key=lambda l: probs.get(l, 0.0))
            log.info(
                "Restricted lang detect: pt=%.2f en=%.2f -> %s",
                probs.get("pt", 0.0),
                probs.get("en", 0.0),
                best,
            )
            return best
        except Exception:
            log.exception("Language detection failed, defaulting to pt.")
            return self._allowed_langs[0]

    def transcribe(self, audio: np.ndarray, context_hint: str | None = None) -> str:
        """Transcribe float32 16kHz mono audio. Returns cleaned text.

        context_hint: tail of previous segment text — used as initial_prompt for
        coherence in streaming mode (ignored when language == 'auto').
        """
        self._ensure_loaded()

        # Energy check - reject if audio is essentially silent.
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < 0.005:
            log.info("Audio RMS too low (%.5f), skipping transcription.", rms)
            return ""

        audio = _trim_trailing_silence(audio)

        if self._config.language == "auto":
            # Restricted auto-detect: only pt or en, never other languages.
            lang = self._detect_restricted_lang(audio)
        else:
            lang = self._config.language

        prompt = context_hint or self._config.initial_prompt or None

        with self._lock:
            result = whisper.transcribe(
                self._model,
                audio,
                language=lang,
                fp16=self._use_fp16,
                task="transcribe",
                initial_prompt=prompt,
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
    audio: np.ndarray, sample_rate: int = 16000, threshold: float = 0.003
) -> np.ndarray:
    """Remove trailing silence to reduce hallucination surface."""
    window = sample_rate // 10   # 100ms windows
    tail_pad = sample_rate // 5  # 200ms buffer after last active window
    for i in range(len(audio) - window, 0, -window):
        if np.abs(audio[i : i + window]).mean() > threshold:
            end = min(len(audio), i + window + tail_pad)
            return audio[:end]
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
