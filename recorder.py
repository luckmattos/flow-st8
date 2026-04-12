"""Microphone capture using sounddevice."""

import threading
from collections.abc import Generator

import numpy as np
import sounddevice as sd

from config import AudioConfig


class AudioRecorder:
    def __init__(self, config: AudioConfig):
        self._config = config
        self._stop_event = threading.Event()

    @property
    def stop_event(self) -> threading.Event:
        return self._stop_event

    def record_stream(self) -> Generator[np.ndarray, None, None]:
        """Yield 30ms float32 chunks at 16kHz mono until stop_event is set."""
        self._stop_event.clear()
        chunk_frames = self._config.chunk_frames
        max_chunks = int(self._config.max_seconds * 1000 / self._config.chunk_ms)

        device = self._config.device_index if self._config.device_index >= 0 else None

        with sd.InputStream(
            samplerate=self._config.sample_rate,
            channels=self._config.channels,
            dtype="float32",
            blocksize=chunk_frames,
            device=device,
        ) as stream:
            for _ in range(max_chunks):
                if self._stop_event.is_set():
                    break
                data, _overflowed = stream.read(chunk_frames)
                yield data[:, 0] if data.ndim > 1 else data.ravel()

    def record_full(self) -> np.ndarray | None:
        """Record until stop_event, return concatenated audio or None if empty."""
        chunks = list(self.record_stream())
        if not chunks:
            return None
        return np.concatenate(chunks)

    def stop(self) -> None:
        self._stop_event.set()
