"""Voice Activity Detection using Silero VAD v6."""

import torch
import silero_vad


class SileroVAD:
    """Wraps Silero VAD for chunk-level speech detection."""

    SAMPLE_RATE = 16000
    CHUNK_SAMPLES = 512  # Required by Silero v6 at 16kHz

    def __init__(self):
        self._model = silero_vad.load_silero_vad()

    def is_speech(self, audio_chunk) -> float:
        """Return speech probability (0.0-1.0) for a 512-sample chunk.

        Args:
            audio_chunk: numpy float32 array of 512 samples at 16kHz.
        """
        tensor = torch.from_numpy(audio_chunk).float()
        prob = self._model(tensor, self.SAMPLE_RATE)
        return prob.item()

    def reset(self) -> None:
        """Reset internal RNN state between recordings."""
        self._model.reset_states()
