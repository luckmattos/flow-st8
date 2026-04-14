"""Voice Activity Detection using Silero VAD v6."""

import logging
import threading

import torch
import silero_vad

log = logging.getLogger(__name__)


class SileroVAD:
    """Wraps Silero VAD for chunk-level speech detection."""

    SAMPLE_RATE = 16000
    CHUNK_SAMPLES = 512  # Required by Silero v6 at 16kHz

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()

    def preload(self) -> None:
        """Load VAD model in advance (call from background thread at startup)."""
        with self._lock:
            if self._model is None:
                log.info("Loading Silero VAD model...")
                self._model = silero_vad.load_silero_vad()
                log.info("Silero VAD model loaded.")

    def _ensure_loaded(self) -> None:
        if self._model is None:
            self.preload()

    def is_speech(self, audio_chunk) -> float:
        """Return speech probability (0.0-1.0) for a 512-sample chunk."""
        self._ensure_loaded()
        tensor = torch.from_numpy(audio_chunk).float()
        prob = self._model(tensor, self.SAMPLE_RATE)
        return prob.item()

    def reset(self) -> None:
        """Reset internal RNN state between recordings."""
        if self._model is not None:
            self._model.reset_states()
