"""Audio feedback via winsound (stdlib, zero dependencies)."""

import threading
import winsound


def _beep(freq: int, duration_ms: int) -> None:
    threading.Thread(
        target=winsound.Beep, args=(freq, duration_ms), daemon=True
    ).start()


def beep_start() -> None:
    """Recording started - low short beep (same as stop)."""
    _beep(440, 100)


def beep_stop() -> None:
    """Recording stopped, processing - low short beep."""
    _beep(440, 100)


def beep_done() -> None:
    """Transcription done and pasted - mid quick beep."""
    _beep(660, 80)


def beep_error() -> None:
    """Error occurred - low longer beep."""
    _beep(220, 300)


def beep_warning() -> None:
    """Time near limit - two subtle high ticks."""
    def _seq() -> None:
        winsound.Beep(1200, 40)
        winsound.Beep(1400, 40)
    threading.Thread(target=_seq, daemon=True).start()
