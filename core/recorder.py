"""Microphone capture using sounddevice."""

import threading
from collections.abc import Generator

import numpy as np
import sounddevice as sd

from core.config import AudioConfig


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

        with self._open_stream(chunk_frames, device) as stream:
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

    def _open_stream(self, chunk_frames: int, device: int | None) -> sd.InputStream:
        """Open the mic InputStream, self-healing from a stale PortAudio host.

        macOS's CoreAudio backend can leave PortAudio's cached host state
        invalid after the default input device changes underneath the app
        (Bluetooth headset connect/disconnect, sleep/wake) — every stream open
        then fails with a generic PortAudioError [-9986] until the process
        restarts. Reinitializing PortAudio forces it to re-enumerate devices,
        which recovers without requiring the user to relaunch the app.
        """
        kwargs = dict(
            samplerate=self._config.sample_rate,
            channels=self._config.channels,
            dtype="float32",
            blocksize=chunk_frames,
            device=device,
        )
        try:
            return sd.InputStream(**kwargs)
        except sd.PortAudioError:
            sd._terminate()
            sd._initialize()
            return sd.InputStream(**kwargs)
