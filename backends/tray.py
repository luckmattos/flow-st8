"""System tray / menu bar icon.

The one shell component that is genuinely shared: pystray already abstracts
Win32 Shell_NotifyIcon and AppKit NSStatusItem, so there is nothing left for a
per-platform implementation to do. Only three things differ, and they are
handled inline: the autostart label, radio-button support, and the fact that
the Darwin backend renders `title` as a tooltip.
"""

import logging
import sys
from typing import TYPE_CHECKING

import pystray
from PIL import Image, ImageDraw

from core.config import WHISPER_MODELS, save_config
from core.resources import resource_path
from version import __version__

if TYPE_CHECKING:
    from core.app import FlowSt8App

log = logging.getLogger(__name__)

COLORS = {
    "idle": (80, 80, 80),
    "recording": (220, 50, 50),
    "processing": (50, 150, 220),
    "error": (220, 120, 50),
}

_LOGO = "assets/flow-st8-icon.png"
# macOS menu-bar extras are almost all monochrome silhouettes on a translucent
# bar; the full-colour brand circle was the one icon that didn't match. This
# is just the inner mark, white, no background circle. Windows keeps the
# colourful logo — its tray sits on an opaque taskbar, not a shared menu bar.
_LOGO_MONO = "assets/flow-st8-icon-mono.png"
# The mono mark is inscribed edge-to-edge in its source canvas, so drawn at
# full bleed it reads visibly taller than the neighbouring menu-bar glyphs,
# which all carry their own built-in padding. Shrinking it onto the same
# canvas size gives it that same breathing room.
_MONO_MARK_SCALE = 0.72

_AUTOSTART_LABEL = (
    "Start with Windows" if sys.platform == "win32" else "Iniciar com o sistema"
)

# pystray's Darwin backend sets HAS_MENU_RADIO = False: radio items render like
# any other entry, so the active model would have no visual marker at all.
_HAS_RADIO = getattr(pystray.Icon, "HAS_MENU_RADIO", True)


def _autostart():
    """Imported late: backends/__init__ imports this module."""
    from backends import autostart

    return autostart


def _make_icon(state: str) -> Image.Image:
    """Create the tray icon from the app logo plus a small state badge."""
    color = COLORS.get(state, COLORS["idle"])
    is_mac = sys.platform == "darwin"
    logo = _LOGO_MONO if is_mac else _LOGO
    try:
        src = Image.open(resource_path(logo)).convert("RGBA")
        if is_mac:
            inner = round(64 * _MONO_MARK_SCALE)
            mark = src.resize((inner, inner), Image.Resampling.LANCZOS)
            img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            offset = (64 - inner) // 2
            img.paste(mark, (offset, offset), mark)
        else:
            img = src.resize((64, 64), Image.Resampling.LANCZOS)
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

    @property
    def icon(self) -> pystray.Icon:
        """The underlying pystray icon — the macOS overlay rides its NSApp."""
        return self._icon

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
                            self._model_label(name, label),
                            self._make_model_callback(name),
                            checked=self._make_model_checked(name),
                            radio=_HAS_RADIO,
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
                        lambda _: f"Hold (press and hold): {self._display(self._app.config.hotkey.hold_key)}",
                        lambda _: self._app.start_hotkey_capture("hold"),
                    ),
                    pystray.MenuItem(
                        lambda _: f"Toggle (hold + extra key): {self._display(self._app.config.hotkey.toggle_key)}",
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
                _AUTOSTART_LABEL,
                self._toggle_autostart,
                checked=lambda _: _autostart().is_enabled(),
            ),
            pystray.MenuItem("Quit", self._quit),
        )

    @staticmethod
    def _display(combo: str) -> str:
        from core.keys import display

        return display(combo)

    def _model_label(self, name: str, label: str):
        if _HAS_RADIO:
            return label
        # No radio support: mark the active model in the text itself.
        return lambda _: ("● " if self._app.config.model.name == name else "   ") + label

    def _make_model_callback(self, name: str):
        return lambda _: self._app.switch_model(name)

    def _make_model_checked(self, name: str):
        return lambda _: self._app.config.model.name == name

    def notify(self, message: str, title: str = "flow-st8") -> None:
        """Show a system notification (osascript on macOS, balloon on Windows)."""
        try:
            self._icon.notify(message, title)
        except Exception:
            log.warning("Notification failed: %s", message)

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
        self._icon.run(setup=self._on_ready)

    def _on_ready(self, icon: pystray.Icon) -> None:
        icon.visible = True
        self._app.on_tray_ready()

    def _toggle_autostart(self) -> None:
        autostart = _autostart()
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
        if sys.platform == "darwin":
            try:
                _autostart().deactivate_session()
            except Exception:
                log.debug("Could not deactivate the LaunchAgent for this session.", exc_info=True)
        self._icon.stop()
