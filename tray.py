"""System tray icon with state feedback."""

import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw

import autostart
from config import WHISPER_MODELS, save_config
from version import __version__

if TYPE_CHECKING:
    from app import FlowSt8App

log = logging.getLogger(__name__)

COLORS = {
    "idle": (80, 80, 80),
    "recording": (220, 50, 50),
    "processing": (50, 150, 220),
    "error": (220, 120, 50),
}

_ARTBOARD_RGB = (244, 243, 241)


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


def _make_icon(state: str) -> Image.Image:
    """Create the tray icon from the app logo plus a small state badge."""
    color = COLORS.get(state, COLORS["idle"])
    try:
        img = _remove_artboard(Image.open(_resource_path("assets/icon.png")))
        img = img.resize((64, 64), Image.Resampling.LANCZOS)
    except Exception:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([44, 44, 62, 62], fill=(*color, 255), outline=(45, 49, 38, 255), width=2)
    return img


class TrayIcon:
    def __init__(self, app: "FlowSt8App"):
        self._app = app
        self._icon = pystray.Icon(
            "flow-st8",
            icon=_make_icon("idle"),
            title="flow-st8 — Idle",
            menu=self._build_menu(),
        )

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem("flow-st8", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Record / Stop",
                lambda: self._app.on_hotkey(),
            ),
            pystray.MenuItem(
                "Model",
                pystray.Menu(
                    *[
                        pystray.MenuItem(
                            label,
                            self._make_model_callback(name),
                            checked=self._make_model_checked(name),
                            radio=True,
                        )
                        for name, label in WHISPER_MODELS
                    ],
                    pystray.Menu.SEPARATOR,
                    pystray.MenuItem(
                        "Loading model...",
                        None,
                        enabled=False,
                        visible=lambda _: self._app.is_model_loading,
                    ),
                ),
            ),
            pystray.MenuItem(
                "Hotkeys",
                pystray.Menu(
                    pystray.MenuItem("Click an item below to remap", None, enabled=False),
                    pystray.MenuItem(
                        lambda _: f"Hold (press and hold): {self._app.config.hotkey.hold_key}",
                        lambda _: self._app.start_hotkey_capture("hold"),
                    ),
                    pystray.MenuItem(
                        lambda _: f"Toggle (hold + extra key): {self._app.config.hotkey.toggle_key}",
                        lambda _: self._app.start_hotkey_capture("toggle"),
                    ),
                ),
            ),
            pystray.MenuItem(
                lambda _: f"Version: {__version__}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start with Windows",
                self._toggle_autostart,
                checked=lambda _: autostart.is_enabled(),
            ),
            pystray.MenuItem("Quit", self._quit),
        )

    def _make_model_callback(self, name: str):
        return lambda _: self._app.switch_model(name)

    def _make_model_checked(self, name: str):
        return lambda _: self._app.config.model.name == name

    def notify(self, message: str, title: str = "flow-st8") -> None:
        """Show a system balloon notification."""
        self._icon.notify(message, title)

    def set_title(self, title: str) -> None:
        self._icon.title = title

    def set_state(self, state: str) -> None:
        """Update icon and tooltip. Safe to call from any thread."""
        self._icon.icon = _make_icon(state)
        titles = {
            "idle": "flow-st8 — Idle",
            "recording": "flow-st8 — Recording...",
            "processing": "flow-st8 — Transcribing...",
            "error": "flow-st8 — Error",
        }
        self._icon.title = titles.get(state, f"flow-st8 — {state}")

    def run(self) -> None:
        """Block on the tray message loop. Must be called from main thread."""
        self._icon.run()

    def _toggle_autostart(self) -> None:
        if autostart.is_enabled():
            if autostart.disable():
                self._app.config.startup.autostart = False
                save_config(self._app.config)
                log.info("Autostart disabled from tray and persisted to config.")
        else:
            if autostart.enable():
                self._app.config.startup.autostart = True
                save_config(self._app.config)
                log.info("Autostart enabled from tray and persisted to config.")

    def _quit(self) -> None:
        self._app.shutdown()
        self._icon.stop()
