"""Launch at login via a LaunchAgent.

The macOS counterpart of the Windows Startup-folder VBS launcher. launchd is
the supported mechanism and needs no elevated rights: dropping a plist in
~/Library/LaunchAgents is enough, and `launchctl` only has to be told about it
so the change applies without a logout.
"""

from __future__ import annotations

import logging
import plistlib
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

LABEL = "com.luckmattos.flow-st8"
_PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"

# Matches the Windows launcher's delay: starting at the very moment of login
# races the audio stack and the window server.
_START_DELAY_SECONDS = 10


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _program_arguments() -> list[str]:
    """How to relaunch this app, frozen or from source."""
    if _is_frozen():
        return [sys.executable]
    main_py = Path(__file__).resolve().parents[2] / "main.py"
    return [sys.executable, str(main_py)]


def _plist_body() -> dict:
    # `sleep N && exec ...` through sh is the least surprising way to delay a
    # LaunchAgent: launchd has no start-delay key for RunAtLoad.
    quoted = " ".join(f'"{arg}"' for arg in _program_arguments())
    return {
        "Label": LABEL,
        "ProgramArguments": [
            "/bin/sh",
            "-c",
            f"sleep {_START_DELAY_SECONDS}; exec {quoted}",
        ],
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProcessType": "Interactive",
        "WorkingDirectory": str(Path(_program_arguments()[-1]).parent),
    }


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["launchctl", *args], capture_output=True, text=True, check=False
    )


def is_enabled() -> bool:
    return _PLIST.exists()


def enable() -> bool:
    try:
        _PLIST.parent.mkdir(parents=True, exist_ok=True)
        with _PLIST.open("wb") as handle:
            plistlib.dump(_plist_body(), handle)
    except OSError:
        log.exception("Could not write the LaunchAgent plist: %s", _PLIST)
        return False

    # bootout first so a rewritten plist actually replaces the loaded one.
    domain = f"gui/{_uid()}"
    _launchctl("bootout", f"{domain}/{LABEL}")
    result = _launchctl("bootstrap", domain, str(_PLIST))
    if result.returncode != 0:
        # The plist is on disk, so it still applies at next login. Not fatal.
        log.warning(
            "LaunchAgent written but not loaded now (%s). It will start at the "
            "next login.",
            (result.stderr or result.stdout).strip(),
        )
    else:
        log.info("Autostart enabled via LaunchAgent: %s", _PLIST)
    return True


def disable() -> bool:
    _launchctl("bootout", f"gui/{_uid()}/{LABEL}")
    try:
        _PLIST.unlink()
    except FileNotFoundError:
        pass
    except OSError:
        log.exception("Could not remove the LaunchAgent plist: %s", _PLIST)
        return False
    log.info("Autostart disabled.")
    return True


def deactivate_session() -> None:
    """Unload the LaunchAgent from the current session, keeping the plist.

    macOS's Background Items registry (`sfltool dumpbtm`) treats a Login Item
    as something that should always be running: if the process disappears
    while the item is still enabled there, macOS relaunches it within a
    second or two — indistinguishable, from the Quit menu item's point of
    view, from the app refusing to close. `bootout` removes the job from
    launchd's live registry for this session only; the plist on disk is
    untouched, so the real login-time RunAtLoad still fires next time.
    """
    if not is_enabled():
        return
    _launchctl("bootout", f"gui/{_uid()}/{LABEL}")


def sync(desired: bool) -> None:
    """Ensure autostart matches the desired state."""
    if desired == is_enabled():
        return
    enable() if desired else disable()


def _uid() -> int:
    import os

    return os.getuid()
