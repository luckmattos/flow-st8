"""Global hotkey registration via Win32 RegisterHotKey + LL keyboard hook."""

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

# Win+letter combos the OS handles — warn user if chosen
_WIN_OS_LETTERS = set("edrstvwxzqf123456789")

# Kernel-level combos that cannot be intercepted
_KERNEL_RESERVED = {"win+l", "ctrl+alt+del", "ctrl+esc"}

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
HOTKEY_MAIN_ID = 1
HOTKEY_STOP_ID = 2

WH_KEYBOARD_LL = 13
WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105

VK_LCONTROL = 0xA2
VK_RCONTROL = 0xA3
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_O = 0x4F

_CTRL_VKS = {VK_LCONTROL, VK_RCONTROL}
_WIN_VKS = {VK_LWIN, VK_RWIN}
_MOD_VKS = _CTRL_VKS | _WIN_VKS | {0xA0, 0xA1, 0xA4, 0xA5}  # shift, alt too


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
    ctypes.c_int, HOOKPROC, ctypes.c_void_p, ctypes.wintypes.DWORD,
]
user32.UnhookWindowsHookEx.restype = ctypes.wintypes.BOOL
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.CallNextHookEx.restype = ctypes.c_ssize_t
user32.CallNextHookEx.argtypes = [
    ctypes.c_void_p, ctypes.c_int, ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM,
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


def _is_ll_hook_combo(hotkey_str: str) -> bool:
    """Returns True if this combo must be handled via LL hook (modifier-only or contains Win+letter)."""
    parts = {p.strip().lower() for p in hotkey_str.split("+")}
    has_ctrl = bool(parts & {"ctrl", "control"})
    has_win = bool(parts & {"win", "super"})
    non_mod = parts - {"ctrl", "control", "win", "super", "shift", "alt"}
    # Pure modifier combo or ctrl+win+letter (Win key in combo → LL hook)
    return has_ctrl and has_win


def _normalize(hotkey_str: str) -> str:
    return hotkey_str.strip().lower()


def check_combo_conflict(hotkey_str: str) -> str | None:
    """
    Returns a warning string if the combo conflicts with OS reserved keys,
    or None if safe. Does NOT test RegisterHotKey (caller must do that).
    """
    norm = _normalize(hotkey_str)
    parts = {p.strip() for p in norm.split("+")}

    if norm in _KERNEL_RESERVED:
        return f"'{hotkey_str}' is reserved by the system and cannot be used."

    has_win = bool(parts & {"win", "super"})
    non_mod = parts - {"ctrl", "control", "win", "super", "shift", "alt"}
    if has_win and non_mod and non_mod.issubset(_WIN_OS_LETTERS):
        letter = next(iter(non_mod))
        return (
            f"Warning: '{hotkey_str}' overrides a Windows shortcut "
            f"(Win+{letter.upper()}). It will work, but Windows will no longer respond to it."
        )
    return None


def _extract_toggle_extra_vk(toggle_str: str, hold_str: str) -> int:
    """Return the VK code of the extra key in toggle that is not in hold."""
    hold_parts = {p.strip().lower() for p in hold_str.split("+")}
    _MODS = {"ctrl", "control", "win", "super", "shift", "alt"}
    for part in (p.strip().lower() for p in toggle_str.split("+")):
        if part in hold_parts or part in _MODS:
            continue
        if part in VK_MAP:
            return VK_MAP[part]
        if len(part) == 1 and part.isalnum():
            return ord(part.upper())
    return VK_O  # fallback to default


class HotkeyManager:
    def __init__(self, bindings: "list[tuple[str, str, Callable[[], None]]]"):
        """
        bindings: list of (event, hotkey_str, callback)
        event: "hold_down" | "hold_up" | "toggle" | "generic"
        """
        self._bindings = bindings
        self._id_to_callback: dict[int, Callable[[], None]] = {}
        self._thread: threading.Thread | None = None
        self._running = False
        self._thread_id: int | None = None
        self._lock = threading.Lock()

        # LL hook state
        self._hook_handle = None
        self._hook_proc_ref: HOOKPROC | None = None
        self._ctrl_down = False
        self._win_down = False
        self._shift_down = False
        self._alt_down = False
        self._suppress_win_keyup = False
        self._hold_active = False  # prevents hold_down from firing on key-repeat

        # Callbacks wired by _install_ll_hook
        self._on_hold_down: Callable[[], None] | None = None
        self._on_hold_up: Callable[[], None] | None = None
        self._on_toggle: Callable[[], None] | None = None
        self._toggle_extra_vk: int = VK_O  # configurable extra key for toggle (default o)

        # Capture mode
        self._capture_lock = threading.Lock()
        self._capture_callback: Callable[[str], None] | None = None
        self._capture_cancel_callback: Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._message_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread_id is not None:
            user32.PostThreadMessageW(self._thread_id, 0x0012, 0, 0)  # WM_QUIT

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

    def unregister_all(self) -> None:
        with self._lock:
            for hotkey_id in list(self._id_to_callback):
                user32.UnregisterHotKey(None, hotkey_id)
            self._id_to_callback.clear()

    def update_bindings(self, bindings: "list[tuple[str, str, Callable[[], None]]]") -> bool:
        """Replace all bindings. Returns False if any RegisterHotKey failed."""
        self.unregister_all()
        self._bindings = bindings
        self._on_hold_down = None
        self._on_hold_up = None
        self._on_toggle = None
        return self._register_bindings()

    def cancel_capture(self) -> None:
        """Cancel any active capture without calling the captured callback."""
        with self._capture_lock:
            self._capture_callback = None
            self._capture_cancel_callback = None

    def capture_next_combo(
        self,
        on_captured: Callable[[str], None],
        on_cancel: "Callable[[], None] | None" = None,
    ) -> None:
        """Next non-modifier keypress (with active modifiers) calls on_captured(key_str).
        Pressing Escape calls on_cancel (if provided) and aborts capture."""
        with self._capture_lock:
            self._capture_callback = on_captured
            self._capture_cancel_callback = on_cancel

    # ------------------------------------------------------------------
    # LL hook
    # ------------------------------------------------------------------

    def _ll_hook_proc(self, nCode, wParam, lParam):
        if nCode < 0:
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
        vk = kbd.vkCode
        msg = wParam
        suppress = False

        is_down = msg in (WM_KEYDOWN, WM_SYSKEYDOWN)
        is_up = msg in (WM_KEYUP, WM_SYSKEYUP)

        # --- Capture mode: suppress all keys, track modifiers, fire on first non-modifier ---
        with self._capture_lock:
            cap_cb = self._capture_callback
            cancel_cb = self._capture_cancel_callback

        if cap_cb is not None:
            if is_down:
                if vk in _CTRL_VKS:
                    self._ctrl_down = True
                elif vk in _WIN_VKS:
                    self._win_down = True
                elif vk in {0xA0, 0xA1}:  # shift
                    self._shift_down = True
                elif vk in {0xA4, 0xA5}:  # alt
                    self._alt_down = True
                elif vk == 0x1B:  # Escape — cancel
                    with self._capture_lock:
                        self._capture_callback = None
                        self._capture_cancel_callback = None
                    self._ctrl_down = self._win_down = self._shift_down = self._alt_down = False
                    if cancel_cb:
                        try:
                            cancel_cb()
                        except Exception:
                            log.exception("capture cancel callback error")
                else:
                    with self._capture_lock:
                        self._capture_callback = None
                        self._capture_cancel_callback = None
                    parts = []
                    if self._ctrl_down:
                        parts.append("ctrl")
                    if self._win_down:
                        parts.append("win")
                    if self._shift_down:
                        parts.append("shift")
                    if self._alt_down:
                        parts.append("alt")
                    key_name = _vk_to_name(vk)
                    if key_name:
                        parts.append(key_name)
                        combo = "+".join(parts)
                        try:
                            cap_cb(combo)
                        except Exception:
                            log.exception("capture_next_combo callback error")
            elif is_up:
                if vk in _CTRL_VKS:
                    self._ctrl_down = False
                elif vk in _WIN_VKS:
                    self._win_down = False
                elif vk in {0xA0, 0xA1}:
                    self._shift_down = False
                elif vk in {0xA4, 0xA5}:
                    self._alt_down = False
            return 1  # suppress all keys during capture

        # --- Normal processing ---
        if is_down:
            if vk in _CTRL_VKS:
                self._ctrl_down = True
            elif vk in _WIN_VKS:
                self._win_down = True
                if self._ctrl_down:
                    suppress = True
                    self._suppress_win_keyup = True
            elif vk == self._toggle_extra_vk and self._ctrl_down and self._win_down:
                # ctrl+win+o → toggle event
                suppress = True
                if self._on_toggle:
                    try:
                        self._on_toggle()
                    except Exception:
                        log.exception("Toggle hotkey callback error")
        elif is_up:
            if vk in _CTRL_VKS:
                self._ctrl_down = False
                if not self._win_down and self._hold_active:
                    self._hold_active = False
                    if self._on_hold_up:
                        try:
                            self._on_hold_up()
                        except Exception:
                            log.exception("Hold-up callback error")
            elif vk in _WIN_VKS:
                self._win_down = False
                if self._suppress_win_keyup:
                    suppress = True
                    self._suppress_win_keyup = False
                if not self._ctrl_down and self._hold_active:
                    self._hold_active = False
                    if self._on_hold_up:
                        try:
                            self._on_hold_up()
                        except Exception:
                            log.exception("Hold-up callback error")

        # Fire hold_down once when ctrl+win both become pressed (guard against repeat)
        if is_down and vk in (_CTRL_VKS | _WIN_VKS):
            if self._ctrl_down and self._win_down and not self._hold_active:
                self._hold_active = True
                if self._on_hold_down:
                    try:
                        self._on_hold_down()
                    except Exception:
                        log.exception("Hold-down callback error")

        if suppress:
            return 1
        return user32.CallNextHookEx(None, nCode, wParam, lParam)

    def _install_ll_hook(self) -> bool:
        self._hook_proc_ref = HOOKPROC(self._ll_hook_proc)
        hmod = kernel32.GetModuleHandleW(None)
        self._hook_handle = user32.SetWindowsHookExW(
            WH_KEYBOARD_LL, self._hook_proc_ref, hmod, 0
        )
        if not self._hook_handle:
            err = ctypes.get_last_error() or ctypes.GetLastError()
            log.error("Failed to install low-level keyboard hook (err=%s)", err)
            return False
        log.info("Low-level keyboard hook installed.")
        return True

    # ------------------------------------------------------------------
    # Message loop
    # ------------------------------------------------------------------

    def _register_bindings(self) -> bool:
        ok = True
        needs_ll = False
        idx = 1
        hold_str = ""
        toggle_str = ""

        for event, hotkey_str, callback in self._bindings:
            if event in ("hold_down", "hold_up", "toggle"):
                needs_ll = True
                if event == "hold_down":
                    self._on_hold_down = callback
                    hold_str = hotkey_str
                elif event == "hold_up":
                    self._on_hold_up = callback
                elif event == "toggle":
                    self._on_toggle = callback
                    toggle_str = hotkey_str
            else:
                # Generic: use RegisterHotKey
                if not self.register_hotkey(hotkey_str, callback, idx):
                    ok = False
                idx += 1

        if hold_str and toggle_str:
            self._toggle_extra_vk = _extract_toggle_extra_vk(toggle_str, hold_str)

        if needs_ll and not self._hook_handle:
            if not self._install_ll_hook():
                ok = False

        return ok

    def _message_loop(self) -> None:
        self._thread_id = kernel32.GetCurrentThreadId()
        self._register_bindings()

        msg = ctypes.wintypes.MSG()
        while self._running:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            if msg.message == WM_HOTKEY:
                with self._lock:
                    cb = self._id_to_callback.get(int(msg.wParam))
                if cb:
                    cb()
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        if self._hook_handle:
            user32.UnhookWindowsHookEx(self._hook_handle)
            self._hook_handle = None
        for hotkey_id in list(self._id_to_callback):
            user32.UnregisterHotKey(None, hotkey_id)
        log.info("Hotkey thread stopped.")


def _vk_to_name(vk: int) -> str:
    """Convert a VK code to a key name string."""
    for name, code in VK_MAP.items():
        if code == vk:
            return name
    if 0x41 <= vk <= 0x5A:
        return chr(vk).lower()
    if 0x30 <= vk <= 0x39:
        return chr(vk)
    return ""
