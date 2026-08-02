"""Text injection via synthetic Unicode keyboard events.

Decision 11 in PROGRESS.md: the default path posts the transcribed text as the
Unicode payload of a keyboard event instead of copying it and faking Cmd+V.
That avoids four separate problems at once — inheriting whatever modifiers the
user still holds, re-entering our own event tap, assuming the target app binds
paste to Cmd+V, and clobbering the clipboard.

The clipboard route stays available through `injection.method = "clipboard"`
for apps that read raw keycodes and ignore Unicode payloads (terminals in raw
mode, remote-desktop clients).
"""

from __future__ import annotations

import logging
import time

import Quartz

from backends.macos.hotkey import SYNTHETIC_MARK
from core.config import InjectionConfig
from core.permissions import secure_input_active

log = logging.getLogger(__name__)

# Long payloads get dropped by some apps; this size is widely safe.
_CHUNK = 20
_CHUNK_PAUSE = 0.002
_KEY_V = 9


def _event_source():
    """Private source so our events are distinguishable from real typing."""
    return Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)


def _tag(event) -> None:
    Quartz.CGEventSetIntegerValueField(
        event, Quartz.kCGEventSourceUserData, SYNTHETIC_MARK
    )
    # Clear inherited modifiers: the user may still be holding the hotkey.
    Quartz.CGEventSetFlags(event, 0)


def _post_text(text: str) -> None:
    source = _event_source()
    for start in range(0, len(text), _CHUNK):
        chunk = text[start : start + _CHUNK]
        for pressed in (True, False):
            event = Quartz.CGEventCreateKeyboardEvent(source, 0, pressed)
            Quartz.CGEventKeyboardSetUnicodeString(event, len(chunk), chunk)
            _tag(event)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(_CHUNK_PAUSE)


def _post_cmd_v() -> None:
    source = _event_source()
    for pressed in (True, False):
        event = Quartz.CGEventCreateKeyboardEvent(source, _KEY_V, pressed)
        Quartz.CGEventSetIntegerValueField(
            event, Quartz.kCGEventSourceUserData, SYNTHETIC_MARK
        )
        Quartz.CGEventSetFlags(event, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        time.sleep(0.01)


class TextInjector:
    """Mirrors backends.windows.injector.TextInjector."""

    def __init__(self, config: InjectionConfig):
        self._config = config

    def inject(self, text: str) -> bool:
        if not text:
            return False

        if secure_input_active():
            # A password field is focused. macOS blocks every synthetic key
            # event — ours and everyone else's. Say so instead of looking dead.
            log.warning(
                "Secure input is active (password field focused); macOS blocks "
                "synthetic keystrokes. Text left untyped."
            )
            return False

        try:
            if self._config.method == "clipboard":
                return self._inject_clipboard(text)
            _post_text(text)
            return True
        except Exception:
            log.exception("Failed to inject text")
            return False

    def _inject_clipboard(self, text: str) -> bool:
        import pyperclip

        previous = None
        if self._config.restore_clipboard:
            try:
                previous = pyperclip.paste()
            except Exception:
                previous = None

        pyperclip.copy(text)
        time.sleep(0.05)
        _post_cmd_v()
        time.sleep(0.1)

        if previous is not None:
            time.sleep(0.2)
            try:
                pyperclip.copy(previous)
            except Exception:
                log.debug("Could not restore the previous clipboard.", exc_info=True)
        return True
