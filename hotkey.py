"""Global hotkey registration via Win32 RegisterHotKey."""

import ctypes
import ctypes.wintypes
import logging
import threading
from collections.abc import Callable

log = logging.getLogger(__name__)

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

kernel32.GetModuleHandleW.restype = ctypes.c_void_p
kernel32.GetModuleHandleW.argtypes = [ctypes.c_wchar_p]

# Virtual key codes
VK_MAP = {
    "space": 0x20, "enter": 0x0D, "tab": 0x09, "escape": 0x1B,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "lwin": 0x5B, "rwin": 0x5C,
}

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
HOTKEY_MAIN_ID = 1
HOTKEY_STOP_ID = 2

# Low-level keyboard hook (for modifier-only combos like ctrl+win)
WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LWIN = 0x5B
VK_RWIN = 0x5C

_CTRL_VKS = {VK_LCONTROL, VK_RCONTROL}
_WIN_VKS = {VK_LWIN, VK_RWIN}


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", ctypes.wintypes.DWORD),
        ("scanCode", ctypes.wintypes.DWORD),
        ("flags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM
)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [
    ctypes.c_int,
    HOOKPROC,
    ctypes.c_void_p,
    ctypes.wintypes.DWORD,
]
user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.wintypes.WPARAM,
    ctypes.wintypes.LPARAM,
]


def _parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """Parse 'ctrl+shift+space' into (modifiers, vk_code)."""
    parts = [p.strip().lower() for p in hotkey_str.split("+")]
    modifiers = MOD_NOREPEAT
    vk = 0
    win_seen = False

    for part in parts:
        if part in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif part in ("shift",):
            modifiers |= MOD_SHIFT
        elif part in ("alt",):
            modifiers |= MOD_ALT
        elif part in ("win", "super"):
            modifiers |= MOD_WIN
            win_seen = True
        elif part in VK_MAP:
            vk = VK_MAP[part]
        elif len(part) == 1 and part.isalnum():
            vk = ord(part.upper())
        else:
            raise ValueError(f"Unknown key: {part}")

    # Allow modifier-only combos like "ctrl+win": drop MOD_WIN and use VK_LWIN as key.
    if vk == 0 and win_seen:
        modifiers &= ~MOD_WIN
        vk = 0x5B  # VK_LWIN

    if vk == 0:
        raise ValueError(f"No key found in hotkey string: {hotkey_str}")

    return modifiers, vk


def _is_modifier_only_ctrl_win(hotkey_str: str) -> bool:
    parts = {p.strip().lower() for p in hotkey_str.split("+")}
    if not parts:
        return False
    allowed = {"ctrl", "control", "win", "super"}
    if not parts.issubset(allowed):
        return False
    has_ctrl = bool(parts & {"ctrl", "control"})
    has_win = bool(parts & {"win", "super"})
    return has_ctrl and has_win


class HotkeyManager:
    def __init__(self, hotkey_bindings: list[tuple[str, Callable[[], None]]]):
        self._hotkey_bindings = hotkey_bindings
        self._id_to_callback: dict[int, Callable[[], None]] = {}
        self._thread: threading.Thread | None = None
        self._running = False
        self._thread_id: int | None = None
        self._lock = threading.Lock()
        self._hook_handle = None
        self._hook_proc_ref: HOOKPROC | None = None
        self._hook_callback: Callable[[], None] | None = None
        self._ctrl_down = False
        self._win_down = False
        self._combo_fired = False
        self._suppress_win_keyup = False

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(
                self._thread_id, 0x0012, 0, 0  # WM_QUIT
            )

    def register_hotkey(
        self,
        hotkey_str: str,
        callback: Callable[[], None],
        hotkey_id: int,
    ) -> bool:
        modifiers, vk = _parse_hotkey(hotkey_str)
        if not user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
            log.error("Failed to register hotkey '%s' (may be in use)", hotkey_str)
            return False

        with self._lock:
            self._id_to_callback[hotkey_id] = callback

        log.info("Hotkey '%s' registered (id=%d).", hotkey_str, hotkey_id)
        return True

    def unregister_hotkey(self, hotkey_id: int) -> None:
        user32.UnregisterHotKey(None, hotkey_id)
        with self._lock:
            self._id_to_callback.pop(hotkey_id, None)

    def _ll_hook_proc(self, nCode, wParam, lParam):
        if nCode < 0 or self._hook_callback is None:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = kbd.vkCode
        msg = wParam
        suppress = False

        if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
            if vk in _CTRL_VKS:
                self._ctrl_down = True
                if self._win_down and not self._combo_fired:
                    self._combo_fired = True
                    try:
                        self._hook_callback()
                    except Exception:
                        log.exception("Hotkey callback error")
            elif vk in _WIN_VKS:
                self._win_down = True
                if self._ctrl_down:
                    suppress = True
                    self._suppress_win_keyup = True
                    if not self._combo_fired:
                        self._combo_fired = True
                        try:
                            self._hook_callback()
                        except Exception:
                            log.exception("Hotkey callback error")
        elif msg in (WM_KEYUP, WM_SYSKEYUP):
            if vk in _CTRL_VKS:
                self._ctrl_down = False
            elif vk in _WIN_VKS:
                self._win_down = False
                if self._suppress_win_keyup:
                    suppress = True
                    self._suppress_win_keyup = False
            if not self._ctrl_down and not self._win_down:
                self._combo_fired = False

        if suppress:
            return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _install_ll_hook(self, callback: Callable[[], None]) -> bool:
        self._hook_callback = callback
        self._hook_proc_ref = HOOKPROC(self._ll_hook_proc)
        hmod = kernel32.GetModuleHandleW(None)
        self._hook_handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc_ref, hmod, 0
        )
        if not self._hook_handle:
            err = ctypes.get_last_error() or ctypes.GetLastError()
            log.error("Failed to install low-level keyboard hook (err=%s)", err)
            return False
        log.info("Low-level keyboard hook installed for ctrl+win combo.")
        return True

    def _message_loop(self) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

        idx = 0
        for hotkey_str, callback in self._hotkey_bindings:
            if _is_modifier_only_ctrl_win(hotkey_str):
                if not self._install_ll_hook(callback):
                    for cleanup_id in range(1, idx + 1):
                        user32.UnregisterHotKey(None, cleanup_id)
                    return
                continue
            idx += 1
            if not self.register_hotkey(hotkey_str, callback, idx):
                for cleanup_id in range(1, idx):
                    user32.UnregisterHotKey(None, cleanup_id)
                return

        msg = ctypes.wintypes.MSG()

        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            if msg.message == WM_HOTKEY:
                with self._lock:
                    callback = self._id_to_callback.get(int(msg.wParam))
                if callback:
                    callback()
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_handle:
            user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None
        for hotkey_id in list(self._id_to_callback):
            user32.UnregisterHotKey(None, hotkey_id)
        log.info("Hotkey unregistered.")
