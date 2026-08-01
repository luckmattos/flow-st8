"""Contracts every platform backend must satisfy.

Win32 and Quartz share no implementation, so nothing here is a base class to
inherit from — these are structural protocols that document the seam between
`core/` and a platform shell. A new backend is written from scratch against
them; it never subclasses another platform's code.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import numpy as np

# (event, combo, callback) where event is
# "hold_down" | "hold_up" | "toggle" | "generic".
HotkeyBinding = tuple[str, str, Callable[[], None]]


class HotkeyBackend(Protocol):
    """Global hotkey capture, running its own OS event loop on a side thread."""

    def start(self) -> None: ...
    def stop(self) -> None: ...

    def update_bindings(self, bindings: list[HotkeyBinding]) -> bool:
        """Replace all bindings. False if any combo could not be registered."""
        ...

    def capture_next_combo(
        self,
        on_captured: Callable[[str], None],
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        """Swallow the next keypress and report it as a combo string."""
        ...

    def cancel_capture(self) -> None: ...


class Injector(Protocol):
    """Puts text into whatever window currently has focus."""

    def inject(self, text: str) -> bool: ...


class Overlay(Protocol):
    """Floating, non-focusable status badge."""

    def show(self) -> None: ...
    def hide(self) -> None: ...
    def show_message(self, text: str) -> None: ...
    def show_loading(self, hint: str = ...) -> None: ...
    def show_hint(self, text: str) -> None: ...
    def hide_hint(self) -> None: ...
    def push_chunk(self, chunk: np.ndarray, is_speech: bool) -> None: ...


class Tray(Protocol):
    """Menu-bar / system-tray icon. `run` owns the main thread."""

    def run(self) -> None: ...
    def notify(self, message: str, title: str = ...) -> None: ...
    def set_state(self, state: str) -> None: ...
    def set_title(self, title: str) -> None: ...


class Autostart(Protocol):
    """Launch-at-login registration. Implemented as a module, not a class."""

    def is_enabled(self) -> bool: ...
    def enable(self) -> bool: ...
    def disable(self) -> bool: ...
    def sync(self, desired: bool) -> None: ...
