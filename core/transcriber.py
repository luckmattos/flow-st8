"""Transcription facade.

Everything that is not engine-specific lives here — the energy gate, silence
trimming, restricted language detection and the anti-hallucination cleanup —
so both backends behave identically. Swapping engines must change how fast the
text arrives, never what it says.
"""

import logging
import re
import threading

import numpy as np

from core.config import ModelConfig
from core.stt import create_backend, describe_device

log = logging.getLogger(__name__)

#: Below this RMS the recording is treated as silence, not speech.
_SILENCE_RMS = 0.005
_NO_SPEECH_MAX = 0.6
#: How far a non-preferred language must lead before it is chosen.
_LANG_MARGIN = 0.15


class Transcriber:
    def __init__(self, config: ModelConfig):
        self._config = config
        self._backend = None
        self._lock = threading.Lock()
        # When language == "auto", detection is restricted to these only.
        self._allowed_langs = ("pt", "en")

    @property
    def device(self) -> str:
        """Engine actually in use: "cuda", "mlx" or "cpu"."""
        return describe_device()

    def preload(self) -> None:
        """Load model in advance (call from background thread at startup)."""
        with self._lock:
            if self._backend is not None:
                return
            backend = create_backend(self._config.name)
        backend.load()
        with self._lock:
            self._backend = backend

    def reload(self, new_config: "ModelConfig") -> None:
        """Swap model in-place (call from background thread)."""
        log.info("Reloading Whisper model '%s'...", new_config.name)
        with self._lock:
            self._backend = None
            self._config = new_config
        self.preload()

    def _ensure_loaded(self) -> None:
        if self._backend is None:
            self.preload()

    def _detect_language(self, backend, audio: np.ndarray) -> str:
        """Restricted auto-detect: only the allowed languages, first preferred.

        The order of _allowed_langs is a preference, not a tie-break, so a later
        language has to win by a clear margin. Measured on this project:
        genuinely English audio scores en≈0.95-1.00, while Portuguese speech the
        model is unsure about lands around pt=0.37/en=0.44 — close enough to flip
        on noise, and picking English there mangles the whole transcription.
        """
        preferred = self._allowed_langs[0]
        try:
            probs = backend.language_probs(audio, self._allowed_langs)
        except Exception:
            log.exception("Language detection failed, defaulting to %s.", preferred)
            return preferred

        best = max(self._allowed_langs, key=lambda lang: probs.get(lang, 0.0))
        chosen = best
        if best != preferred:
            margin = probs.get(best, 0.0) - probs.get(preferred, 0.0)
            if margin < _LANG_MARGIN:
                chosen = preferred

        log.info(
            "Restricted lang detect: %s -> %s",
            " ".join(f"{lang}={probs.get(lang, 0.0):.2f}" for lang in self._allowed_langs),
            chosen + (f" (over {best}, margin too small)" if chosen != best else ""),
        )
        return chosen

    def transcribe(self, audio: np.ndarray, context_hint: str | None = None) -> str:
        """Transcribe float32 16kHz mono audio. Returns cleaned text.

        context_hint: tail of previous segment text — used as initial_prompt for
        coherence in streaming mode.
        """
        self._ensure_loaded()

        # Energy check - reject if audio is essentially silent.
        rms = float(np.sqrt(np.mean(audio ** 2)))
        if rms < _SILENCE_RMS:
            log.info("Audio RMS too low (%.5f), skipping transcription.", rms)
            return ""

        audio = _trim_trailing_silence(audio)

        with self._lock:
            backend = self._backend
            config = self._config

        if config.language == "auto":
            lang = self._detect_language(backend, audio)
        else:
            lang = config.language

        prompt = context_hint or config.initial_prompt or None

        with self._lock:
            segments = backend.transcribe(audio, lang, prompt)

        good_segments = [
            s for s in segments if s.get("no_speech_prob", 0.0) < _NO_SPEECH_MAX
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
