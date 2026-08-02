"""Floating status badge for recording, processing, and short messages."""

from __future__ import annotations

import ctypes
import math
import queue
import threading
import tkinter as tk
import tkinter.font as tkfont

import numpy as np
from PIL import Image, ImageDraw, ImageTk

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
_KEY_RGB = (0x00, 0x00, 0x02)  # same colour for Pillow compositing

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
# The outer green circle is deliberately smaller than the badge canvas (not
# edge-to-edge like the loading spinner) so it never clips against the panel.
_REC_CIRCLE_R = _BADGE / 4.0
# Wide swing on purpose — a narrow range reads as barely pulsing even when
# the underlying level swing is large, since a few pixels of radius change is
# hard to perceive. Max stays short of _REC_CIRCLE_R so a ring of green is
# always visible, even at peak level.
_DOT_MIN_R = 2.5
_DOT_MAX_R = 12.0

_SPIN_SECONDS = 2.0  # one full loading-spinner turn

# Tk's create_oval has no anti-aliasing: it rasterizes with a hard, jagged edge
# at any size. Same problem Pillow's ImageDraw has on macOS, and the same fix —
# draw oversize and downsample with a quality filter. Here it also means the
# badge is composited as one bitmap instead of stacked canvas items.
_SUPERSAMPLE = 4

# Attack/release for the level meter. A single symmetric factor (the old 0.72)
# made the dot feel stuck near centre: it lagged so far behind speech onsets
# that it never reached the top of its range before the syllable ended. Rising
# fast and falling slow is what reads as "tracking my voice" — the peak lands
# on the consonant, then eases back instead of flickering.
_AMP_ATTACK = 0.55
_AMP_RELEASE = 0.16

# Level meter calibration, in dBFS on the chunk peak.
#
# The previous linear `amp * 24` is why normal speech sat near the centre and
# only shouting reached the rim: loudness is logarithmic, so a linear map
# spends most of its range on the last few dB.
#
# The range below is measured, not assumed. Conversational speech on a desktop
# USB mic peaks around -33 dBFS with syllable peaks reaching about -28 — far
# quieter than the -14 dBFS a "full scale" guess suggests, which is precisely
# how you end up having to shout to move the dot. The ceiling sits just above
# normal speaking peaks so ordinary talking uses the top of the travel, and
# the floor sits well above a quiet room's noise (measured near -80 dBFS) so
# breathing and fan noise do not drive the animation.
_DB_FLOOR = -55.0  # below this the dot rests at minimum
_DB_CEIL = -26.0   # at or above this it reaches the rim
_DB_EPS = 1e-7     # keeps log10 finite on digital silence

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
        # Guards the live audio level only; the queue still carries commands.
        self._amp_lock = threading.Lock()
        self._amp = 0.0
        self._is_speech = False
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
        # Deliberately NOT queued. Audio chunks arrive every ~32ms and the draw
        # loop runs every 30ms, so routing level updates through the command
        # queue made them compete with it: _poll drained every pending chunk per
        # frame and kept only the last, and once the queue hit maxsize the
        # put_nowait dropped newer levels on the floor. Both effects showed up
        # as the dot stuttering and lagging behind the voice. A single
        # lock-protected slot always holds the newest level instead.
        #
        # Peak, not mean: speech is short bursts separated by short gaps, and
        # averaging a 32ms window flattens exactly the transients that make it
        # feel responsive. Peak tracks the syllable; the release curve in _draw
        # is what keeps it from flickering.
        peak = float(np.abs(chunk).max())
        with self._amp_lock:
            self._amp = peak
            self._is_speech = is_speech

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
        self._frame_photo: ImageTk.PhotoImage | None = None  # kept alive against Tk's GC
        self._visible = False
        self._mode = "wave"  # "wave" | "message" | "loading"
        self._message = ""
        self._level = 0.0  # smoothed 0..1 loudness position
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
        spinner rotates it fresh from this source every frame.

        Held at _SUPERSAMPLE size rather than the final 68px: rotating a
        badge-sized raster resamples an already-downscaled image once per
        frame, which visibly chews up the edge. Rotating large and downsampling
        after keeps every frame as sharp as the first."""
        try:
            image = Image.open(resource_path(_LOGO)).convert("RGBA")
            px = _BADGE * _SUPERSAMPLE
            return image.resize((px, px), Image.Resampling.LANCZOS)
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
                    with self._amp_lock:
                        self._amp = 0.0
                    self._level = 0.0
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

        with self._amp_lock:
            amp, is_speech = self._amp, self._is_speech

        # Convert to a 0..1 loudness position BEFORE smoothing. Smoothing raw
        # amplitude and converting after would average in the linear domain and
        # reintroduce the compression this is meant to undo.
        db = 20.0 * math.log10(max(amp, _DB_EPS))
        target = (db - _DB_FLOOR) / (_DB_CEIL - _DB_FLOOR)
        target = min(1.0, max(0.0, target))

        # Rise fast, fall slow — see _AMP_ATTACK.
        factor = _AMP_ATTACK if target > self._level else _AMP_RELEASE
        self._level += (target - self._level) * factor

        c = self._canvas
        c.delete("all")
        w = self._current_w

        if self._mode == "message":
            self._draw_message(self._message, w)
        elif self._mode == "loading":
            self._draw_loading_spin()
        else:
            self._draw_recording_circle(is_speech)

        if self._hint_text:
            c.create_text(
                w // 2,
                _BADGE + _HINT_H // 2,
                text=self._hint_text,
                fill=_HINT_COLOR,
                font=("Segoe UI", 7),
                anchor="center",
            )

    def _render_photo(self, frame: Image.Image) -> None:
        """Composite an RGBA frame onto the key colour and blit it.

        The window is colour-keyed, not per-pixel alpha: Win32 makes _KEY_COLOR
        transparent by exact match, so a partially transparent pixel is not
        something it can express. Flattening onto that colour ourselves keeps
        the anti-aliased edges — they blend against the key colour and survive
        as real pixels, while only the fully transparent background matches the
        key exactly and drops out."""
        flat = Image.new("RGBA", frame.size, _KEY_RGB + (255,))
        flat.alpha_composite(frame)
        self._frame_photo = ImageTk.PhotoImage(flat.convert("RGB"), master=self._root)
        self._canvas.create_image(0, 0, image=self._frame_photo, anchor="nw")

    def _draw_loading_spin(self) -> None:
        """Rotate the logo clockwise. Since its green circle fills the canvas
        edge-to-edge and is perfectly round, rotating the whole raster reads as
        just the inner "s8" mark spinning — no need to separate it out."""
        if self._icon is None:
            ss = _SUPERSAMPLE
            big = Image.new("RGBA", (_BADGE * ss, _BADGE * ss), (0, 0, 0, 0))
            inset = 2 * ss
            ImageDraw.Draw(big).ellipse(
                [inset, inset, _BADGE * ss - inset, _BADGE * ss - inset],
                fill=_BRAND_GREEN,
            )
            self._render_photo(big.resize((_BADGE, _BADGE), Image.Resampling.LANCZOS))
            return
        # Negative angle: Pillow rotates counter-clockwise for positive degrees.
        rotated = self._icon.rotate(-self._spin_deg, resample=Image.Resampling.BICUBIC)
        self._render_photo(rotated.resize((_BADGE, _BADGE), Image.Resampling.LANCZOS))

    def _draw_recording_circle(self, is_speech: bool) -> None:
        """Green badge with a dark dot pulsing to the live audio level —
        matches assets/flow-st8-icon-recording.svg, animated instead of static.

        Rendered through Pillow at _SUPERSAMPLE scale and downsampled rather
        than drawn with create_oval, which produces a visibly stair-stepped
        edge — the same reason the macOS backend supersamples."""
        # Already a smoothed 0..1 loudness position — see the dBFS mapping in
        # _draw. No further scaling here.
        level = self._level
        if not is_speech:
            level = max(0.10, 0.18 + math.sin(self._phase * 2.2) * 0.05)

        ss = _SUPERSAMPLE
        big = Image.new("RGBA", (_BADGE * ss, _BADGE * ss), (0, 0, 0, 0))
        draw = ImageDraw.Draw(big)

        cx = cy = _BADGE * ss / 2
        r = _REC_CIRCLE_R * ss
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_BRAND_GREEN)

        radius = (_DOT_MIN_R + (_DOT_MAX_R - _DOT_MIN_R) * level) * ss
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius], fill=_BRAND_DARK
        )

        frame = big.resize((_BADGE, _BADGE), Image.Resampling.LANCZOS)
        self._render_photo(frame)

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
