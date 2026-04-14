"""System tray icon with state feedback."""

import logging
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw

import autostart
from config import save_config
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


def _make_icon(state: str) -> Image.Image:
    """Generate a 64x64 tray icon with mic symbol."""
    color = COLORS.get(state, COLORS["idle"])
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Circle background
    draw.ellipse([4, 4, 60, 60], fill=(*color, 255))
    # Mic body
    draw.rounded_rectangle([26, 14, 38, 36], radius=4, fill=(255, 255, 255, 200))
    # Mic arc
    draw.arc([20, 26, 44, 46], 0, 180, fill=(255, 255, 255, 200), width=3)
    # Mic stand
    draw.line([32, 46, 32, 54], fill=(255, 255, 255, 200), width=2)
    draw.line([26, 54, 38, 54], fill=(255, 255, 255, 200), width=2)
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
                "Gravar / Parar",
                lambda: self._app.on_hotkey(),
            ),
            pystray.MenuItem(
                lambda _: f"Modelo: {self._app.config.model.name}",
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda _: f"Hotkey: {self._app.config.hotkey.key}",
                None,
                enabled=False,
            ),
            pystray.MenuItem(
                lambda _: f"Versao: {__version__}",
                None,
                enabled=False,
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Iniciar com Windows",
                self._toggle_autostart,
                checked=lambda _: autostart.is_enabled(),
            ),
            pystray.MenuItem("Sair", self._quit),
        )

    def set_state(self, state: str) -> None:
        """Update icon and tooltip. Safe to call from any thread."""
        self._icon.icon = _make_icon(state)
        titles = {
            "idle": "flow-st8 — Idle",
            "recording": "flow-st8 — Gravando...",
            "processing": "flow-st8 — Transcrevendo...",
            "error": "flow-st8 — Erro",
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
