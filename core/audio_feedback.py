"""Audio feedback via short generated tones.

Replaces winsound.Beep, which is Windows-only. sounddevice is already a
dependency for microphone capture, so this adds nothing to the install.
"""

import logging
import threading

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

_SAMPLE_RATE = 44100
_VOLUME = 0.18
_FADE_MS = 5  # avoids the click a hard-edged sine produces

# Serializes playback so a beep sequence is not interleaved with the next one.
_play_lock = threading.Lock()


def _tone(freq: int, duration_ms: int) -> np.ndarray:
    frames = int(_SAMPLE_RATE * duration_ms / 1000)
    t = np.arange(frames, dtype=np.float32) / _SAMPLE_RATE
    wave = np.sin(2 * np.pi * freq * t).astype(np.float32)

    fade = min(frames // 2, int(_SAMPLE_RATE * _FADE_MS / 1000)) or 1
    envelope = np.ones(frames, dtype=np.float32)
    envelope[:fade] = np.linspace(0.0, 1.0, fade, dtype=np.float32)
    envelope[-fade:] = np.linspace(1.0, 0.0, fade, dtype=np.float32)

    return wave * envelope * _VOLUME


def _play(*tones: tuple[int, int]) -> None:
    """Play tones in order on a daemon thread. Never raises into the caller."""

    def run() -> None:
        try:
            with _play_lock:
                for freq, duration_ms in tones:
                    sd.play(_tone(freq, duration_ms), _SAMPLE_RATE, blocking=True)
        except Exception:
            # No output device, or the device disappeared mid-play. Feedback is
            # cosmetic — never let it take the recording pipeline down.
            log.debug("Audio feedback unavailable.", exc_info=True)

    threading.Thread(target=run, daemon=True).start()


def beep_start() -> None:
    """Recording started - low short beep (same as stop)."""
    _play((440, 100))


def beep_stop() -> None:
    """Recording stopped, processing - low short beep."""
    _play((440, 100))


def beep_done() -> None:
    """Transcription done and pasted - mid quick beep."""
    _play((660, 80))


def beep_error() -> None:
    """Error occurred - low longer beep."""
    _play((220, 300))


def beep_warning() -> None:
    """Time near limit - two subtle high ticks."""
    _play((1200, 40), (1400, 40))
