"""Global hotkey capture via CGEventTap.

The macOS counterpart of backends/windows/hotkey.py. Same contract, no shared
code: WH_KEYBOARD_LL + GetMessage there, CGEventTap + CFRunLoop here.

Per decision 12 in PROGRESS.md the tap never suppresses during normal use — it
observes and passes every event through. The one exception is hotkey capture
(remapping from the tray), where the keystroke must not also reach the focused
app; that is why the tap is created with OptionDefault rather than ListenOnly.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

import Quartz

from core import keys
from core.permissions import accessibility_granted

log = logging.getLogger(__name__)

# Tag the injector puts on events it posts, so we never react to our own typing.
SYNTHETIC_MARK = 0x5F8A7E

_FLAGS = {
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
}

# Physical key positions (kVK_ANSI_*). Layout-independent: on ABNT2, pt-BR or
# US the letter positions are identical, which is what a hotkey should track.
_KEYCODES: dict[str, int] = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8,
    "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26,
    "8": 28, "0": 29, "o": 31, "u": 32, "i": 34, "p": 35, "l": 37, "j": 38,
    "k": 40, "n": 45, "m": 46,
    "=": 24, "-": 27, "]": 30, "[": 33, "'": 39, ";": 41, "\\": 42, ",": 43,
    "/": 44, ".": 47, "`": 50,
    "return": 36, "enter": 36, "tab": 48, "space": 49, "backspace": 51,
    "escape": 53, "delete": 117, "home": 115, "end": 119, "pageup": 116,
    "pagedown": 121, "left": 123, "right": 124, "down": 125, "up": 126,
    "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98,
    "f8": 100, "f9": 101, "f10": 109, "f11": 103, "f12": 111,
}

_NAMES = {code: name for name, code in reversed(list(_KEYCODES.items()))}

_ESCAPE_KEYCODE = 53

# Combos carrying Cmd are held for seconds during push-to-talk, and every
# destructive macOS shortcut has Cmd in it.
_CMD_WARNING = (
    "'{combo}' usa Cmd. Em push-to-talk o acorde fica preso enquanto você fala, "
    "e qualquer tecla encostada vira atalho do sistema (Cmd+Q fecha o app, "
    "Ctrl+Cmd+Q bloqueia a tela). Prefira ctrl+option."
)


def _parse(combo: str) -> tuple[int, int | None]:
    """Return (required modifier flags, keycode or None) for a combo."""
    flags = 0
    keycode: int | None = None
    for part in keys.normalize(combo).split("+"):
        if part in _FLAGS:
            flags |= _FLAGS[part]
        elif part in _KEYCODES:
            keycode = _KEYCODES[part]
        elif part:
            raise ValueError(f"Unknown key: {part}")
    return flags, keycode


def check_combo_conflict(hotkey_str: str) -> str | None:
    """Warn about combos macOS makes dangerous. None when the combo is fine."""
    parts = keys.parts(hotkey_str)
    if not parts:
        return f"'{hotkey_str}' não é um atalho válido."
    if "cmd" in parts:
        return _CMD_WARNING.format(combo=hotkey_str)
    return None


def _keycode_name(code: int) -> str:
    return _NAMES.get(code, "")


class HotkeyManager:
    """Mirrors backends.windows.hotkey.HotkeyManager."""

    def __init__(self, bindings: list[tuple[str, str, Callable[[], None]]]):
        self._bindings = bindings
        self._lock = threading.Lock()

        self._tap = None
        self._runloop = None
        self._source = None
        self._callback_ref = None  # keep alive: the tap holds no Python ref
        self._thread: threading.Thread | None = None

        self._hold_flags = 0
        self._toggle_flags = 0
        self._toggle_keycode: int | None = None
        self._hold_active = False

        self._on_hold_down: Callable[[], None] | None = None
        self._on_hold_up: Callable[[], None] | None = None
        self._on_toggle: Callable[[], None] | None = None

        self._capture_lock = threading.Lock()
        self._capture_callback: Callable[[str], None] | None = None
        self._capture_cancel_callback: Callable[[], None] | None = None

        self._apply_bindings(bindings)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="hotkey-tap", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        if self._tap is not None:
            Quartz.CGEventTapEnable(self._tap, False)
        if self._runloop is not None:
            Quartz.CFRunLoopStop(self._runloop)

    def update_bindings(
        self, bindings: list[tuple[str, str, Callable[[], None]]]
    ) -> bool:
        """Rebind without reinstalling the tap — the tap matches on flags."""
        try:
            self._apply_bindings(bindings)
        except ValueError:
            log.exception("Rejected hotkey bindings")
            return False
        return True

    def capture_next_combo(
        self,
        on_captured: Callable[[str], None],
        on_cancel: Callable[[], None] | None = None,
    ) -> None:
        with self._capture_lock:
            self._capture_callback = on_captured
            self._capture_cancel_callback = on_cancel

    def cancel_capture(self) -> None:
        with self._capture_lock:
            self._capture_callback = None
            self._capture_cancel_callback = None

    # ------------------------------------------------------------------
    # Wiring
    # ------------------------------------------------------------------

    def _apply_bindings(
        self, bindings: list[tuple[str, str, Callable[[], None]]]
    ) -> None:
        hold_flags = toggle_flags = 0
        toggle_keycode: int | None = None
        on_hold_down = on_hold_up = on_toggle = None

        for event, combo, callback in bindings:
            if event == "hold_down":
                hold_flags, _ = _parse(combo)
                on_hold_down = callback
            elif event == "hold_up":
                on_hold_up = callback
            elif event == "toggle":
                toggle_flags, toggle_keycode = _parse(combo)
                on_toggle = callback

        with self._lock:
            self._bindings = bindings
            self._hold_flags = hold_flags
            self._toggle_flags = toggle_flags
            self._toggle_keycode = toggle_keycode
            self._on_hold_down = on_hold_down
            self._on_hold_up = on_hold_up
            self._on_toggle = on_toggle

    def _install(self) -> bool:
        if not accessibility_granted():
            log.error(
                "Accessibility permission missing — the tap would install but "
                "never fire. Grant it in System Settings > Privacy & Security."
            )
            return False

        mask = Quartz.CGEventMaskBit(Quartz.kCGEventFlagsChanged) | Quartz.CGEventMaskBit(
            Quartz.kCGEventKeyDown
        )
        self._callback_ref = self._on_event
        self._tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            # Default (not ListenOnly) so capture mode can swallow a keystroke.
            # Normal operation still returns every event untouched.
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._callback_ref,
            None,
        )
        if not self._tap:
            log.error("CGEventTapCreate failed (permission revoked mid-run?).")
            return False

        self._source = Quartz.CFMachPortCreateRunLoopSource(None, self._tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetCurrent(), self._source, Quartz.kCFRunLoopCommonModes
        )
        Quartz.CGEventTapEnable(self._tap, True)
        log.info("CGEventTap installed.")
        return True

    def _run(self) -> None:
        if not self._install():
            return
        self._runloop = Quartz.CFRunLoopGetCurrent()
        Quartz.CFRunLoopRun()
        log.info("Hotkey tap thread stopped.")

    # ------------------------------------------------------------------
    # Tap callback (runs on the tap thread — keep it quick)
    # ------------------------------------------------------------------

    def _on_event(self, proxy, event_type, event, refcon):
        # The system disables a tap that takes too long, or on user input.
        # Re-arm instead of going deaf for the rest of the session.
        if event_type in (
            Quartz.kCGEventTapDisabledByTimeout,
            Quartz.kCGEventTapDisabledByUserInput,
        ):
            log.warning("Event tap disabled by the system; re-enabling.")
            Quartz.CGEventTapEnable(self._tap, True)
            return event

        # Never react to keystrokes the injector posted.
        if (
            Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
            == SYNTHETIC_MARK
        ):
            return event

        flags = Quartz.CGEventGetFlags(event)
        keycode = int(
            Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        )

        with self._capture_lock:
            capturing = self._capture_callback is not None
        if capturing:
            return self._handle_capture(event, event_type, flags, keycode)

        try:
            if event_type == Quartz.kCGEventFlagsChanged:
                self._handle_modifiers(flags)
            elif event_type == Quartz.kCGEventKeyDown:
                self._handle_keydown(flags, keycode)
        except Exception:
            log.exception("Hotkey callback error")

        return event

    def _handle_modifiers(self, flags: int) -> None:
        with self._lock:
            required = self._hold_flags
            on_down, on_up = self._on_hold_down, self._on_hold_up
        if not required:
            return

        held = (flags & required) == required
        if held and not self._hold_active:
            self._hold_active = True
            if on_down:
                on_down()
        elif not held and self._hold_active:
            self._hold_active = False
            if on_up:
                on_up()

    def _handle_keydown(self, flags: int, keycode: int) -> None:
        with self._lock:
            required = self._toggle_flags
            wanted = self._toggle_keycode
            on_toggle = self._on_toggle
        if wanted is None or keycode != wanted:
            return
        if required and (flags & required) != required:
            return
        if on_toggle:
            on_toggle()

    def _handle_capture(self, event, event_type, flags: int, keycode: int):
        """Swallow keys until a non-modifier arrives, then report the combo."""
        if event_type != Quartz.kCGEventKeyDown:
            return None  # eat modifier changes too, so nothing leaks through

        with self._capture_lock:
            captured = self._capture_callback
            cancelled = self._capture_cancel_callback
            self._capture_callback = None
            self._capture_cancel_callback = None

        if keycode == _ESCAPE_KEYCODE:
            if cancelled:
                try:
                    cancelled()
                except Exception:
                    log.exception("capture cancel callback error")
            return None

        parts = [name for name, flag in _FLAGS.items() if flags & flag]
        name = _keycode_name(keycode)
        if name and captured:
            parts.append(name)
            try:
                captured("+".join(parts))
            except Exception:
                log.exception("capture_next_combo callback error")
        return None
