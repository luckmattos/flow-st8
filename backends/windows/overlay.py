"""Floating status badge for recording, processing, and short messages."""

from __future__ import annotations

import ctypes
import math
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont

import numpy as np
from PIL import Image, ImageTk

from core.resources import resource_path

_BADGE = 68
_MESSAGE_H = 30
_HINT_H = 14
_FPS_MS = 30
_MARGIN_X = 22
_MARGIN_Y = 76

# Transparency: root/canvas bg is this color -> color-keyed to transparent by Win32.
_KEY_COLOR = "#000002"
_KEY_COLORREF = 0x00020000  # COLORREF (0x00BBGGRR): B=2, G=0, R=0

_TEXT_COLOR = "#e0e0ff"
_HINT_COLOR = "#7a8aaa"

# Exact fills from assets/flow-st8-icon.svg, so the badge we draw matches the
# logo pixel-for-pixel instead of approximating the brand green.
_BRAND_GREEN = "#B7F700"
_BRAND_DARK = "#2D3325"

_LOGO = "assets/flow-st8-icon.png"

# Pulsing recording dot, mirroring assets/flow-st8-icon-recording.svg (a fixed
# r=13 circle in a 100px canvas) but animated: radius tracks live audio level
# instead of staying static.
_DOT_MIN_R = 7.0
_DOT_MAX_R = 15.0

_SPIN_SECONDS = 2.0  # one full loading-spinner turn

_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_LAYERED = 0x00080000
_LWA_COLORKEY = 0x00000001
_LWA_ALPHA = 0x00000002
_ALPHA_BYTE = int(0.94 * 255)


class WaveOverlay:
    """Always-on-top bottom-right badge with live audio bars."""

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=128)
        self._ready = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=3.0)

    # ------------------------------------------------------------------
    # Public API (thread-safe)
    # ------------------------------------------------------------------

    def show(self) -> None:
        self._queue.put(("show",))

    def hide(self) -> None:
        self._queue.put(("hide",))

    def show_message(self, text: str) -> None:
        self._queue.put(("message", text))

    def show_loading(self, hint: str = "Carregando modelo…") -> None:
        self._queue.put(("loading", hint))

    def show_hint(self, text: str) -> None:
        self._queue.put(("hint", text))

    def hide_hint(self) -> None:
        self._queue.put(("hint", ""))

    def push_chunk(self, chunk: np.ndarray, is_speech: bool) -> None:
        amp = float(np.abs(chunk).mean())
        try:
            self._queue.put_nowait(("chunk", amp, is_speech))
        except queue.Full:
            pass

    # ------------------------------------------------------------------
    # Tkinter thread
    # ------------------------------------------------------------------

    def _run(self) -> None:
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.config(bg=_KEY_COLOR)
        root.withdraw()

        self._sw = root.winfo_screenwidth()
        self._sh = root.winfo_screenheight()

        canvas = tk.Canvas(
            root,
            width=_BADGE,
            height=_BADGE,
            bg=_KEY_COLOR,
            highlightthickness=0,
            bd=0,
        )
        canvas.pack()

        self._root = root
        self._canvas = canvas
        self._icon = self._load_icon()
        self._spin_photo: ImageTk.PhotoImage | None = None  # kept alive against Tk's GC
        self._visible = False
        self._mode = "wave"  # "wave" | "message" | "loading"
        self._message = ""
        self._amp = 0.0
        self._smoothed_amp = 0.0
        self._is_speech = False
        self._phase = 0.0
        self._spin_deg = 0.0
        self._hint_text = ""
        self._current_w = _BADGE
        self._current_h = _BADGE
        self._setup_done = False

        self._place_window(_BADGE, _BADGE)
        self._ready.set()
        root.after(_FPS_MS, self._poll)
        root.mainloop()

    def _load_icon(self) -> Image.Image | None:
        """Full logo, kept as a PIL Image (not PhotoImage) — the loading
        spinner rotates it fresh from this source every frame."""
        try:
            image = Image.open(resource_path(_LOGO)).convert("RGBA")
            return image.resize((_BADGE, _BADGE), Image.Resampling.LANCZOS)
        except Exception:
            return None

    def _setup_window(self) -> None:
        """Color-key layered window; call once after first deiconify."""
        try:
            hwnd = self._root.winfo_id()
            style = ctypes.windll.user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, _GWL_EXSTYLE, style | _WS_EX_LAYERED | _WS_EX_TRANSPARENT
            )
            ctypes.windll.user32.SetLayeredWindowAttributes(
                hwnd, _KEY_COLORREF, _ALPHA_BYTE, _LWA_COLORKEY | _LWA_ALPHA
            )
        except Exception:
            pass
        self._setup_done = True

    def _poll(self) -> None:
        newly_shown = False
        resize_needed = False
        try:
            while True:
                item = self._queue.get_nowait()
                cmd = item[0]
                if cmd == "show":
                    self._mode = "wave"
                    self._amp = 0.0
                    self._smoothed_amp = 0.0
                    self._visible = True
                    self._root.deiconify()
                    newly_shown = True
                    resize_needed = True
                elif cmd == "hide":
                    self._mode = "wave"
                    self._hint_text = ""
                    self._visible = False
                    self._root.withdraw()
                elif cmd == "message":
                    self._mode = "message"
                    self._message = item[1]
                    self._visible = True
                    self._root.deiconify()
                    newly_shown = True
                    resize_needed = True
                elif cmd == "loading":
                    self._mode = "loading"
                    self._hint_text = item[1] if len(item) > 1 else ""
                    self._visible = True
                    self._root.deiconify()
                    newly_shown = True
                    resize_needed = True
                elif cmd == "hint":
                    self._hint_text = item[1]
                    resize_needed = True
                elif cmd == "chunk":
                    _, amp, is_speech = item
                    self._amp = amp
                    self._is_speech = is_speech
        except queue.Empty:
            pass

        if newly_shown and not self._setup_done:
            self._setup_window()

        if resize_needed and self._visible:
            self._resize()

        if self._visible:
            self._draw()

        self._root.after(_FPS_MS, self._poll)

    def _resize(self) -> None:
        if self._mode == "message":
            font = tkfont.Font(family="Segoe UI", size=8)
            w = max(_BADGE, font.measure(self._message) + 28)
            h = _MESSAGE_H
        else:
            w = _BADGE
            h = _BADGE

        if self._hint_text:
            h += _HINT_H
            hint_font = tkfont.Font(family="Segoe UI", size=7)
            w = max(w, hint_font.measure(self._hint_text) + 16)

        if w == self._current_w and h == self._current_h:
            return

        self._current_w = w
        self._current_h = h
        self._canvas.config(width=w, height=h)
        self._place_window(w, h)

    def _place_window(self, w: int, h: int) -> None:
        x = self._sw - w - _MARGIN_X
        y = self._sh - h - _MARGIN_Y
        self._root.geometry(f"{w}x{h}+{x}+{y}")

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _draw(self) -> None:
        self._phase += 0.15
        self._spin_deg = (self._spin_deg + 360.0 / (_SPIN_SECONDS * 1000.0 / _FPS_MS)) % 360.0
        self._smoothed_amp = self._smoothed_amp * 0.72 + self._amp * 0.28

        c = self._canvas
        c.delete("all")
        w = self._current_w

        if self._mode == "message":
            self._draw_message(self._message, w)
        elif self._mode == "loading":
            self._draw_loading_spin()
        else:
            self._draw_recording_circle()

        if self._hint_text:
            c.create_text(
                w // 2,
                _BADGE + _HINT_H // 2,
                text=self._hint_text,
                fill=_HINT_COLOR,
                font=("Segoe UI", 7),
                anchor="center",
            )

    def _draw_loading_spin(self) -> None:
        """Rotate the logo clockwise. Since its green circle fills the canvas
        edge-to-edge and is perfectly round, rotating the whole raster reads as
        just the inner "s8" mark spinning — no need to separate it out."""
        if self._icon is None:
            self._canvas.create_oval(2, 2, _BADGE - 2, _BADGE - 2, fill=_BRAND_GREEN, outline="")
            return
        # Negative angle: Pillow rotates counter-clockwise for positive degrees.
        rotated = self._icon.rotate(-self._spin_deg, resample=Image.Resampling.BICUBIC)
        self._spin_photo = ImageTk.PhotoImage(rotated, master=self._root)
        self._canvas.create_image(0, 0, image=self._spin_photo, anchor="nw")

    def _draw_recording_circle(self) -> None:
        """Green badge with a dark dot pulsing to the live audio level —
        matches assets/flow-st8-icon-recording.svg, animated instead of static."""
        level = min(1.0, self._smoothed_amp * 18.0)
        if not self._is_speech:
            level = max(0.10, 0.18 + math.sin(self._phase * 2.2) * 0.05)

        self._canvas.create_oval(0, 0, _BADGE, _BADGE, fill=_BRAND_GREEN, outline="")

        radius = _DOT_MIN_R + (_DOT_MAX_R - _DOT_MIN_R) * level
        cx = cy = _BADGE / 2
        self._canvas.create_oval(
            cx - radius, cy - radius, cx + radius, cy + radius,
            fill=_BRAND_DARK, outline="",
        )

    def _draw_message(self, text: str, w: int) -> None:
        self._canvas.create_rectangle(
            0,
            0,
            w,
            _MESSAGE_H,
            fill="#1a1a2e",
            outline="",
        )
        self._canvas.create_text(
            w // 2,
            _MESSAGE_H // 2,
            text=text,
            fill=_TEXT_COLOR,
            font=("Segoe UI", 8),
            anchor="center",
        )
