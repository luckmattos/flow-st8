"""Floating status badge as a non-activating NSPanel.

The Windows overlay is Tk with a colour-keyed layered window; that approach
cannot be ported, because Tk and AppKit both demand the main thread and pystray
already owns it there. The Fase 1 spike confirmed an NSPanel created inside
pystray's NSApplication coexists fine and never takes focus — which is the
property that matters, since stealing focus would send the injected text to the
wrong window.

Frames are rendered with Pillow and handed to an NSImageView. Drawing 68x68 in
Python at 30fps is cheap, and it reuses the artwork pipeline the tray already
depends on, instead of a second one in Core Graphics.
"""

from __future__ import annotations

import logging
import math
import queue
import threading

import AppKit
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PyObjCTools import AppHelper

from core.resources import resource_path

log = logging.getLogger(__name__)

_BADGE = 68
_MESSAGE_H = 30
_HINT_H = 14
_FPS = 30.0
_MARGIN_X = 22
_MARGIN_Y = 76

_TEXT_COLOR = (224, 224, 255, 255)
_HINT_COLOR = (122, 138, 170, 255)
_MESSAGE_BG = (26, 26, 46, 235)

# Exact fills from assets/flow-st8-icon.svg, so the badge we draw matches the
# logo pixel-for-pixel instead of approximating the brand green.
_BRAND_GREEN = (183, 247, 0, 255)
_BRAND_DARK = (45, 51, 37, 255)

_LOGO = "assets/flow-st8-icon.png"

# Pulsing recording dot, mirroring assets/flow-st8-icon-recording.svg (a fixed
# r=13 circle in a 100px canvas) but animated: radius tracks live audio level
# instead of staying static. The outer green circle is deliberately smaller
# than the badge canvas (not edge-to-edge like the loading spinner) so it
# never clips against the panel bounds.
_REC_CIRCLE_R = _BADGE / 4.0
_DOT_MIN_R = 3.5
_DOT_MAX_R = 7.5

_SPIN_SECONDS = 2.0  # one full loading-spinner turn


def _load_font(size: int):
    for path in (
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _pil_to_nsimage(image: Image.Image) -> AppKit.NSImage:
    data = image.tobytes("raw", "RGBA")
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, image.width, image.height, 8, 4, True, False,
        AppKit.NSDeviceRGBColorSpace, image.width * 4, 32,
    )
    rep.bitmapData()[:] = data
    ns = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(image.width, image.height))
    ns.addRepresentation_(rep)
    return ns


class WaveOverlay:
    """Same public surface as the Windows overlay; all calls are thread-safe."""

    def __init__(self) -> None:
        self._queue: queue.Queue = queue.Queue(maxsize=128)
        self._lock = threading.Lock()

        self._panel = None
        self._view = None
        self._timer = None

        self._visible = False
        self._mode = "wave"        # "wave" | "message" | "loading"
        self._message = ""
        self._hint_text = ""
        self._amp = 0.0
        self._smoothed_amp = 0.0
        self._is_speech = False
        self._phase = 0.0
        self._spin_deg = 0.0
        self._size = (_BADGE, _BADGE)

        self._icon = None
        self._font_msg = _load_font(12)
        self._font_hint = _load_font(10)

    # ------------------------------------------------------------------
    # Public API (thread-safe)
    # ------------------------------------------------------------------

    def show(self) -> None:
        self._push(("show",))

    def hide(self) -> None:
        self._push(("hide",))

    def show_message(self, text: str) -> None:
        self._push(("message", text))

    def show_loading(self, hint: str = "Carregando modelo…") -> None:
        self._push(("loading", hint))

    def show_hint(self, text: str) -> None:
        self._push(("hint", text))

    def hide_hint(self) -> None:
        self._push(("hint", ""))

    def push_chunk(self, chunk: np.ndarray, is_speech: bool) -> None:
        amp = float(np.abs(chunk).mean())
        with self._lock:
            self._amp = amp
            self._is_speech = is_speech

    def _push(self, item: tuple) -> None:
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            return
        AppHelper.callAfter(self._drain)

    # ------------------------------------------------------------------
    # Main thread
    # ------------------------------------------------------------------

    def _ensure_panel(self) -> None:
        if self._panel is not None:
            return

        rect = AppKit.NSMakeRect(0, 0, _BADGE, _BADGE)
        panel = AppKit.NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            AppKit.NSWindowStyleMaskBorderless
            | AppKit.NSWindowStyleMaskNonactivatingPanel,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(AppKit.NSStatusWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(AppKit.NSColor.clearColor())
        panel.setIgnoresMouseEvents_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorTransient
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )

        view = AppKit.NSImageView.alloc().initWithFrame_(rect)
        view.setImageScaling_(AppKit.NSImageScaleNone)
        panel.setContentView_(view)

        self._panel = panel
        self._view = view
        try:
            # Kept as a PIL Image, not baked into an NSImage: the loading
            # spinner rotates it fresh from this source every frame.
            self._icon = Image.open(resource_path(_LOGO)).convert("RGBA").resize(
                (_BADGE, _BADGE), Image.Resampling.LANCZOS
            )
        except Exception:
            log.debug("Overlay icon unavailable.", exc_info=True)

    def _drain(self) -> None:
        self._ensure_panel()
        try:
            while True:
                item = self._queue.get_nowait()
                cmd = item[0]
                if cmd == "show":
                    self._mode = "wave"
                    with self._lock:
                        self._amp = 0.0
                    self._smoothed_amp = 0.0
                    self._set_visible(True)
                elif cmd == "hide":
                    self._mode = "wave"
                    self._hint_text = ""
                    self._set_visible(False)
                elif cmd == "message":
                    self._mode = "message"
                    self._message = item[1]
                    self._set_visible(True)
                elif cmd == "loading":
                    self._mode = "loading"
                    self._hint_text = item[1] if len(item) > 1 else ""
                    self._set_visible(True)
                elif cmd == "hint":
                    self._hint_text = item[1]
        except queue.Empty:
            pass

        if self._visible:
            self._layout()
            self._render()

    def _set_visible(self, visible: bool) -> None:
        self._visible = visible
        if visible:
            self._layout()
            self._render()
            # orderFrontRegardless shows without activating the app.
            self._panel.orderFrontRegardless()
            self._start_timer()
        else:
            self._stop_timer()
            self._panel.orderOut_(None)

    def _start_timer(self) -> None:
        if self._timer is not None:
            return
        self._timer = AppKit.NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            1.0 / _FPS, True, lambda _timer: self._tick()
        )

    def _stop_timer(self) -> None:
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None

    def _tick(self) -> None:
        if not self._visible:
            return
        self._render()

    def _layout(self) -> None:
        if self._mode == "message":
            width = max(_BADGE, int(self._font_msg.getlength(self._message)) + 28)
            height = _MESSAGE_H
        else:
            width, height = _BADGE, _BADGE

        if self._hint_text:
            height += _HINT_H
            width = max(width, int(self._font_hint.getlength(self._hint_text)) + 16)

        if (width, height) == self._size:
            return
        self._size = (width, height)

        screen = AppKit.NSScreen.mainScreen().visibleFrame()
        x = screen.origin.x + screen.size.width - width - _MARGIN_X
        y = screen.origin.y + _MARGIN_Y
        self._panel.setFrame_display_(
            AppKit.NSMakeRect(x, y, width, height), True
        )
        self._view.setFrame_(AppKit.NSMakeRect(0, 0, width, height))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def _render(self) -> None:
        width, height = self._size
        self._phase += 0.15
        self._spin_deg = (self._spin_deg + 360.0 / (_SPIN_SECONDS * _FPS)) % 360.0
        with self._lock:
            amp, is_speech = self._amp, self._is_speech
        self._smoothed_amp = self._smoothed_amp * 0.72 + amp * 0.28

        frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(frame)

        if self._mode == "message":
            draw.rounded_rectangle(
                [0, 0, width - 1, _MESSAGE_H - 1], radius=8, fill=_MESSAGE_BG
            )
            draw.text(
                (width // 2, _MESSAGE_H // 2), self._message,
                fill=_TEXT_COLOR, font=self._font_msg, anchor="mm",
            )
        elif self._mode == "loading":
            self._draw_loading_spin(frame)
        else:
            self._draw_recording_circle(draw, is_speech)

        if self._hint_text:
            draw.text(
                (width // 2, _BADGE + _HINT_H // 2), self._hint_text,
                fill=_HINT_COLOR, font=self._font_hint, anchor="mm",
            )

        self._view.setImage_(_pil_to_nsimage(frame))

    def _draw_loading_spin(self, frame: Image.Image) -> None:
        """Rotate the logo clockwise. Since its green circle fills the canvas
        edge-to-edge and is perfectly round, rotating the whole raster reads as
        just the inner "s8" mark spinning — no need to separate it out."""
        if self._icon is None:
            ImageDraw.Draw(frame).ellipse(
                [2, 2, _BADGE - 2, _BADGE - 2], fill=_BRAND_GREEN
            )
            return
        # Negative angle: Pillow rotates counter-clockwise for positive degrees.
        rotated = self._icon.rotate(-self._spin_deg, resample=Image.Resampling.BICUBIC)
        frame.paste(rotated, (0, 0), rotated)

    def _draw_recording_circle(self, draw: ImageDraw.ImageDraw, is_speech: bool) -> None:
        """Green badge with a dark dot pulsing to the live audio level —
        matches assets/flow-st8-icon-recording.svg, animated instead of static."""
        level = min(1.0, self._smoothed_amp * 18.0)
        if not is_speech:
            level = max(0.10, 0.18 + math.sin(self._phase * 2.2) * 0.05)

        cx = cy = _BADGE / 2
        r = _REC_CIRCLE_R
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_BRAND_GREEN)

        radius = _DOT_MIN_R + (_DOT_MAX_R - _DOT_MIN_R) * level
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius], fill=_BRAND_DARK
        )
