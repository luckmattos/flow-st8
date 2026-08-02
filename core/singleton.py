"""Single-instance guard.

Needed on macOS specifically: CGEventTap has no exclusivity, so two processes
can each install a tap and both fire on the same physical keypress — unlike
Windows, where RegisterHotKey simply fails for the second caller. The trigger
is autostart itself: enabling it calls `launchctl bootstrap` immediately so
the change applies without a logout, and combined with RunAtLoad that starts
a second process right away whenever autostart flips on while the app is
already running manually — which is every first launch, since autostart
defaults to on.

An OS-level advisory lock (not a PID file) is used deliberately: the OS
releases it automatically on process exit or crash, so there is no stale-lock
file to detect or clean up.
"""

import logging
import sys
from pathlib import Path

from core.paths import APP_DIR

log = logging.getLogger(__name__)

_LOCK_PATH = APP_DIR / "flow-st8.lock"

# Held for the process lifetime — closing it releases the lock, so it must
# outlive every caller's stack frame.
_handle = None


def acquire() -> bool:
    """True if this is the only running instance. Safe to call once, at boot."""
    global _handle

    APP_DIR.mkdir(parents=True, exist_ok=True)
    _handle = open(_LOCK_PATH, "w")

    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(_handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        _handle.close()
        _handle = None
        return False

    return True
