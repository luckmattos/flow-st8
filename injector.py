"""Text injection into the active window via clipboard + SendInput."""

import ctypes
import ctypes.wintypes
import logging
import time

import pyperclip

from config import InjectionConfig

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
user32.SendInput.argtypes = [
    ctypes.wintypes.UINT,
    ctypes.c_void_p,
    ctypes.c_int,
]
user32.SendInput.restype = ctypes.wintypes.UINT

# SendInput constants
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_CONTROL = 0x11  # Generic Control (not left-specific)
VK_V = 0x56

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# ULONG_PTR is PVOID-sized (8 bytes on 64-bit, 4 on 32-bit)
ULONG_PTR = ctypes.c_size_t


class MOUSEINPUT(ctypes.Structure):
    """Needed so the INPUT union has the correct maximum size."""
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("_u",)
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("_u", _INPUT_UNION),
    ]


def _make_key_input(vk: int, flags: int = 0) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.wScan = 0
    inp.ki.dwFlags = flags
    inp.ki.time = 0
    inp.ki.dwExtraInfo = 0
    return inp


def _send_ctrl_v() -> bool:
    """Send Ctrl+V via SendInput. Returns True if all events were sent."""
    inputs = (INPUT * 4)(
        _make_key_input(VK_CONTROL),
        _make_key_input(VK_V),
        _make_key_input(VK_V, KEYEVENTF_KEYUP),
        _make_key_input(VK_CONTROL, KEYEVENTF_KEYUP),
    )
    sent = user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))
    if sent != 4:
        err = ctypes.get_last_error()
        log.error("SendInput sent only %d/4 events (error=%d, INPUT size=%d)",
                  sent, err, ctypes.sizeof(INPUT))
        return False
    return True


def _get_clipboard_text() -> str | None:
    if not user32.OpenClipboard(None):
        return None

    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None

        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None

        try:
            return ctypes.wstring_at(ptr)
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def _set_clipboard_text(text: str) -> bool:
    if not user32.OpenClipboard(None):
        return False

    try:
        if not user32.EmptyClipboard():
            return False

        buffer = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(buffer)
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        if not handle:
            return False

        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            kernel32.GlobalFree(handle)
            return False

        try:
            ctypes.memmove(ptr, buffer, size)
        finally:
            kernel32.GlobalUnlock(handle)

        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            return False

        return True
    finally:
        user32.CloseClipboard()


class TextInjector:
    def __init__(self, config: InjectionConfig):
        self._config = config

    def inject(self, text: str) -> bool:
        """Inject text into the active window. Returns True on success."""
        if not text:
            return False

        try:
            return self._inject_clipboard(text)
        except Exception:
            log.exception("Failed to inject text")
            return False

    def _inject_clipboard(self, text: str) -> bool:
        prev = None
        if self._config.restore_clipboard:
            try:
                prev = _get_clipboard_text()
            except Exception:
                prev = None

        pyperclip.copy(text)
        time.sleep(0.05)

        _send_ctrl_v()
        time.sleep(0.1)

        if self._config.restore_clipboard and prev is not None:
            time.sleep(0.2)
            _set_clipboard_text(prev)

        return True
