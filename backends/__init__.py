"""Selects the platform shell for this OS.

Importing this module always succeeds, on every platform. Anything the current
OS has no implementation for is replaced by a stub that raises only when used,
so `core/` stays importable on CI runners and on a Mac while the macOS backend
is being built out one piece at a time.
"""

import sys

_PLATFORM = sys.platform

#: True when every piece of the shell exists for this OS.
SUPPORTED = _PLATFORM == "win32"


def _unsupported(what: str):
    def raiser(*_args, **_kwargs):
        raise RuntimeError(
            f"flow-st8 has no {what} backend for {_PLATFORM!r} yet. "
            "See PROGRESS.md for the port status."
        )

    return raiser


class _AutostartStub:
    """Reports "not enabled" and declines silently, so boot never breaks."""

    @staticmethod
    def is_enabled() -> bool:
        return False

    @staticmethod
    def enable() -> bool:
        return False

    @staticmethod
    def disable() -> bool:
        return False

    @staticmethod
    def sync(desired: bool) -> None:
        return None


def _no_conflict(hotkey_str: str) -> str | None:
    return None


if _PLATFORM == "win32":
    from backends.windows import autostart
    from backends.windows.hotkey import HotkeyManager, check_combo_conflict
    from backends.windows.injector import TextInjector
    from backends.windows.overlay import WaveOverlay
    from backends.windows.tray import TrayIcon

elif _PLATFORM == "darwin":
    # Fase 2 in progress: hotkey and injection are real, the UI is still stubbed.
    from backends.macos.hotkey import HotkeyManager, check_combo_conflict
    from backends.macos.injector import TextInjector

    WaveOverlay = _unsupported("overlay")
    TrayIcon = _unsupported("tray")
    autostart = _AutostartStub()

else:
    HotkeyManager = _unsupported("hotkey")
    TextInjector = _unsupported("text injection")
    WaveOverlay = _unsupported("overlay")
    TrayIcon = _unsupported("tray")
    check_combo_conflict = _no_conflict
    autostart = _AutostartStub()


__all__ = [
    "SUPPORTED",
    "HotkeyManager",
    "TextInjector",
    "TrayIcon",
    "WaveOverlay",
    "autostart",
    "check_combo_conflict",
]
