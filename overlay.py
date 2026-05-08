"""Floating status badge for recording, processing, and short messages."""

from __future__ import annotations

import ctypes
import math
import queue
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path

import numpy as np
from PIL import Image, ImageTk

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
_BAR_ACTIVE = "#c7f902"
_BAR_DIM = "#6f8a18"
_ARTBOARD_RGB = (244, 243, 241)

_GWL_EXSTYLE = -20
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_LAYERED = 0x00080000
_LWA_COLORKEY = 0x00000001
_LWA_ALPHA = 0x00000002
_ALPHA_BYTE = int(0.94 * 255)


def _resource_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def _remove_artboard(image: Image.Image) -> Image.Image:
    """Turn the exported off-white artboard into transparency."""
    image = image.convert("RGBA")
    pixels = image.load()
    w, h = image.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a and abs(r - _ARTBOARD_RGB[0]) <= 3 and abs(g - _ARTBOARD_RGB[1]) <= 3 and abs(b - _ARTBOARD_RGB[2]) <= 3:
                pixels[x, y] = (r, g, b, 0)
    return image


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

    def show_loading(self) -> None:
        self._queue.put(("loading",))

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
        self._icon = self._load_icon(root)
        self._visible = False
        self._mode = "wave"  # "wave" | "message" | "loading"
        self._message = ""
        self._amp = 0.0
        self._smoothed_amp = 0.0
        self._is_speech = False
        self._phase = 0.0
        self._hint_text = ""
        self._current_w = _BADGE
        self._current_h = _BADGE
        self._setup_done = False

        self._place_window(_BADGE, _BADGE)
        self._ready.set()
        root.after(_FPS_MS, self._poll)
        root.mainloop()

    def _load_icon(self, root: tk.Tk) -> ImageTk.PhotoImage | None:
        try:
            image = _remove_artboard(Image.open(_resource_path("assets/icon-no-wave.png")))
            image = image.resize((_BADGE, _BADGE), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(image, master=root)
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
        self._smoothed_amp = self._smoothed_amp * 0.72 + self._amp * 0.28

        c = self._canvas
        c.delete("all")
        w = self._current_w

        if self._mode == "message":
            self._draw_message(self._message, w)
        elif self._mode == "loading":
            self._draw_badge()
            self._draw_processing_bars()
        else:
            self._draw_badge()
            self._draw_audio_bars()

        if self._hint_text:
            c.create_text(
                w // 2,
                _BADGE + _HINT_H // 2,
                text=self._hint_text,
                fill=_HINT_COLOR,
                font=("Segoe UI", 7),
                anchor="center",
            )

    def _draw_badge(self) -> None:
        if self._icon is not None:
            self._canvas.create_image(0, 0, image=self._icon, anchor="nw")
        else:
            self._canvas.create_oval(2, 2, _BADGE - 2, _BADGE - 2, fill="#2d3126", outline="")

    def _draw_audio_bars(self) -> None:
        # Coordinates mirror the three horizontal bars from icon.svg, scaled to badge size.
        level = min(1.0, self._smoothed_amp * 18.0)
        if not self._is_speech:
            level = max(0.10, 0.18 + math.sin(self._phase * 2.2) * 0.05)

        centers_y = [54.6, 58.7, 62.8]
        max_widths = [7.0, 11.0, 15.0]
        min_widths = [3.5, 5.0, 7.0]
        x_center = _BADGE / 2 + 0.5

        for i, y in enumerate(centers_y):
            wobble = 0.82 + 0.18 * math.sin(self._phase * 2.4 + i * 1.7)
            width = min_widths[i] + (max_widths[i] - min_widths[i]) * level * wobble
            thickness = 2.1 + 0.8 * level
            color = _BAR_ACTIVE if self._is_speech else _BAR_DIM
            self._canvas.create_line(
                x_center - width,
                y,
                x_center + width,
                y,
                fill=color,
                width=thickness,
                capstyle="round",
            )

    def _draw_processing_bars(self) -> None:
        centers_y = [54.6, 58.7, 62.8]
        widths = [5.0, 8.5, 12.0]
        x_center = _BADGE / 2 + 0.5
        for i, y in enumerate(centers_y):
            pulse = 0.45 + 0.55 * abs(math.sin(self._phase * 2.0 + i * 1.1))
            width = widths[i] * pulse
            self._canvas.create_line(
                x_center - width,
                y,
                x_center + width,
                y,
                fill=_BAR_ACTIVE,
                width=2.4,
                capstyle="round",
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
