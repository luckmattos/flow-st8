"""Selects the platform shell for this OS.

Importing this module always succeeds, on every platform — unsupported systems
get stubs that raise only when something is actually used. That keeps `core/`
importable on CI runners and on a Mac while the macOS backend is being built.
"""

import sys

SUPPORTED = sys.platform == "win32"

if SUPPORTED:
    from backends.windows import autostart
    from backends.windows.hotkey import HotkeyManager, check_combo_conflict
    from backends.windows.injector import TextInjector
    from backends.windows.overlay import WaveOverlay
    from backends.windows.tray import TrayIcon
else:

    def _unsupported(what: str):
        def raiser(*_args, **_kwargs):
            raise RuntimeError(
                f"flow-st8 has no {what} backend for {sys.platform!r} yet. "
                "See PROGRESS.md for the port status."
            )

        return raiser

    HotkeyManager = _unsupported("hotkey")
    TextInjector = _unsupported("text injection")
    WaveOverlay = _unsupported("overlay")
    TrayIcon = _unsupported("tray")

    def check_combo_conflict(hotkey_str: str) -> str | None:
        """No known reserved combos on an unsupported platform."""
        return None

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
