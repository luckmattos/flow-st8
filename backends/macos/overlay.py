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
_FPS = 30.0
_MARGIN_X = 22
_MARGIN_Y = 76

# Hint callout: a dark chat-bubble tooltip anchored above the badge. Sized in
# points (not scaled by the backing factor — that happens at draw time), so
# _layout() and _render() agree on the same window geometry.
_CALLOUT_FONT_PT = 13
_CALLOUT_PAD_X = 12
_CALLOUT_GAP = 6    # space between the callout's bottom edge and the badge
_CALLOUT_H = 30

_TEXT_COLOR = (224, 224, 255, 255)
_MESSAGE_BG = (26, 26, 46, 235)
_CALLOUT_BG = (20, 20, 20, 235)
_CALLOUT_TEXT = (255, 255, 255, 255)

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
# Wide swing on purpose — a narrow range reads as barely pulsing even when
# the underlying level swing is large, since a few pixels of radius change is
# hard to perceive. Max stays short of _REC_CIRCLE_R so a ring of green is
# always visible, even at peak level.
_DOT_MIN_R = 2.5
_DOT_MAX_R = 12.0

# Pillow's ImageDraw has no anti-aliasing: ellipse() rasterizes with a hard,
# jagged edge at any resolution. Drawing 4x oversize and downsampling with a
# quality filter is what actually produces a smooth edge — the Retina fix
# alone (matching physical pixels) only stopped the OS from blurring an
# already-jagged bitmap further, it didn't smooth the jaggedness itself.
_SUPERSAMPLE = 4


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


def _backing_scale() -> float:
    """Retina factor of the main screen (2.0 on virtually every Mac sold since
    2012). Everything we draw is rendered at this many actual pixels per point
    — skip it and NSImageView silently upscales a 1x bitmap to fill a 2x view,
    which is exactly the blur/soft-edges a flat-fill circle makes obvious."""
    try:
        screen = AppKit.NSScreen.mainScreen()
        if screen is not None:
            return float(screen.backingScaleFactor())
    except Exception:
        pass
    return 1.0


def _pil_to_nsimage(image: Image.Image, point_size: tuple[float, float]) -> AppKit.NSImage:
    """`image` is full-resolution pixels; `point_size` is the logical size the
    view should occupy. Keeping them separate is what makes this a proper
    Retina NSImage instead of a bitmap the view has to stretch."""
    data = image.tobytes("raw", "RGBA")
    rep = AppKit.NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, image.width, image.height, 8, 4, True, False,
        AppKit.NSDeviceRGBColorSpace, image.width * 4, 32,
    )
    rep.bitmapData()[:] = data
    ns = AppKit.NSImage.alloc().initWithSize_(AppKit.NSMakeSize(*point_size))
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
        self._size = (_BADGE, _BADGE)
        self._scale = 1.0  # replaced with the real backing scale in _ensure_panel

        self._icon = None
        self._font_msg = None
        self._font_hint = None

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

        self._scale = _backing_scale()
        self._font_msg = _load_font(round(12 * self._scale))
        self._font_hint = _load_font(round(_CALLOUT_FONT_PT * self._scale))

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
            # badge composites it fresh onto each frame, next to whatever
            # hint callout is showing. Resized straight to physical-pixel
            # size (68pt * scale) so there is one clean LANCZOS resize from
            # the 100px source instead of stacking a second, lower-quality
            # resize when AppKit fits it to the view.
            px = round(_BADGE * self._scale)
            self._icon = Image.open(resource_path(_LOGO)).convert("RGBA").resize(
                (px, px), Image.Resampling.LANCZOS
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
            # Height is always _BADGE, hint or not — the badge's on-screen
            # position (and the window's y) never changes. Only width grows,
            # to the left, to fit the callout beside the badge.
            width, height = _BADGE, _BADGE
            if self._hint_text:
                # Measured at its true point size, not the physical-pixel size
                # _font_hint was loaded at — this stays in the same unscaled
                # unit as `width`, which drives point-space window geometry
                # below. A small safety margin absorbs the sub-pixel rounding
                # difference between this measurement pass and the much
                # larger supersampled font instance actually drawn with.
                try:
                    measure_font = self._font_hint.font_variant(size=_CALLOUT_FONT_PT)
                except Exception:
                    measure_font = self._font_hint  # bitmap fallback: not resizable
                callout_w = (
                    int(measure_font.getlength(self._hint_text) * 1.08)
                    + _CALLOUT_PAD_X * 2
                )
                width = _BADGE + _CALLOUT_GAP + callout_w

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
        width, height = self._size  # points — drive window geometry, unscaled
        scale = self._scale
        self._phase += 0.15
        with self._lock:
            amp, is_speech = self._amp, self._is_speech
        self._smoothed_amp = self._smoothed_amp * 0.72 + amp * 0.28

        # Physical-pixel canvas (points * scale) so nothing needs OS stretching.
        pw, ph = round(width * scale), round(height * scale)

        # ImageDraw has no anti-aliasing — ellipse()/rounded_rectangle()
        # rasterize with a hard, jagged edge at any resolution. Drawing
        # oversize and downsampling with LANCZOS is what actually smooths the
        # recording dot, the message bubble and the hint callout.
        ss = _SUPERSAMPLE

        if self._mode == "message":
            big = Image.new("RGBA", (pw * ss, ph * ss), (0, 0, 0, 0))
            draw = ImageDraw.Draw(big)
            msg_h = _MESSAGE_H * scale * ss
            draw.rounded_rectangle(
                [0, 0, pw * ss - 1, msg_h - 1], radius=8 * scale * ss, fill=_MESSAGE_BG
            )
            try:
                msg_font = self._font_msg.font_variant(size=round(12 * scale * ss))
            except Exception:
                msg_font = self._font_msg  # bitmap fallback font: not resizable
            draw.text(
                (pw * ss // 2, msg_h // 2), self._message,
                fill=_TEXT_COLOR, font=msg_font, anchor="mm",
            )
            frame = big.resize((pw, ph), Image.Resampling.LANCZOS)
            self._view.setImage_(_pil_to_nsimage(frame, (width, height)))
            return

        # wave / loading: the badge always occupies the right _BADGE-wide
        # column of the canvas, full height. A hint callout, when present,
        # fills the space to its left. Growing the window for the callout
        # only ever adds width on the left — the window's right edge and its
        # height both stay fixed across resizes — so the badge's own
        # on-screen position never moves, hint or not.
        badge_px = round(_BADGE * scale)
        big = Image.new("RGBA", (pw * ss, ph * ss), (0, 0, 0, 0))
        draw = ImageDraw.Draw(big)

        badge_cx = (pw - badge_px / 2) * ss
        badge_cy = (ph * ss) / 2

        if self._mode != "loading":
            self._draw_recording_circle(draw, is_speech, scale * ss, badge_cx, badge_cy)

        if self._hint_text:
            gap_ss = _CALLOUT_GAP * scale * ss
            avail_w = pw * ss - badge_px * ss - gap_ss
            self._draw_callout(draw, self._hint_text, avail_w, ph * ss, scale * ss)

        frame = big.resize((pw, ph), Image.Resampling.LANCZOS)

        if self._mode == "loading":
            # The logo source is already smooth (PNG -> one LANCZOS resize in
            # _ensure_panel); pasting it after the downsample avoids a second,
            # redundant resize pass for no visible gain. Static — no rotation.
            if self._icon is not None:
                frame.paste(self._icon, (pw - badge_px, ph - badge_px), self._icon)
            else:
                d = ImageDraw.Draw(frame)
                inset = round(2 * scale)
                d.ellipse(
                    [pw - badge_px + inset, ph - badge_px + inset, pw - inset, ph - inset],
                    fill=_BRAND_GREEN,
                )

        self._view.setImage_(_pil_to_nsimage(frame, (width, height)))

    def _draw_recording_circle(
        self,
        draw: ImageDraw.ImageDraw,
        is_speech: bool,
        scale: float,
        cx: float,
        cy: float,
    ) -> None:
        """Green badge with a dark dot pulsing to the live audio level —
        matches assets/flow-st8-icon-recording.svg, animated instead of static."""
        # Real speech through a built-in mic runs quieter than the synthetic
        # tones this was first tuned against — 24x instead of 18x reaches full
        # size at normal speaking volume, not just when talking loudly.
        level = min(1.0, self._smoothed_amp * 24.0)
        if not is_speech:
            level = max(0.10, 0.18 + math.sin(self._phase * 2.2) * 0.05)

        r = _REC_CIRCLE_R * scale
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=_BRAND_GREEN)

        radius = (_DOT_MIN_R + (_DOT_MAX_R - _DOT_MIN_R) * level) * scale
        draw.ellipse(
            [cx - radius, cy - radius, cx + radius, cy + radius], fill=_BRAND_DARK
        )

    def _draw_callout(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        avail_w: float,
        canvas_h: float,
        scale: float,
    ) -> None:
        """Dark chat-bubble tooltip filling the space to the left of the
        badge, vertically centered against it. `avail_w` is exactly that
        space — `_layout()` already sized the window to fit the text — so the
        bubble spans the full width rather than re-measuring and risking a
        second, slightly different result that clips against its own edge.
        `scale` already includes the supersample factor."""
        try:
            font = self._font_hint.font_variant(size=round(_CALLOUT_FONT_PT * scale))
        except Exception:
            font = self._font_hint  # bitmap fallback font: not resizable

        bubble_h = _CALLOUT_H * scale
        y0 = (canvas_h - bubble_h) / 2
        y1 = y0 + bubble_h
        draw.rounded_rectangle([0, y0, avail_w, y1], radius=8 * scale, fill=_CALLOUT_BG)
        draw.text(
            (avail_w / 2, (y0 + y1) / 2), text,
            fill=_CALLOUT_TEXT, font=font, anchor="mm",
        )
