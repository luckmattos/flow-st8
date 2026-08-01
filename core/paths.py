"""Per-platform application directories."""

import os
import sys
from pathlib import Path

APP_NAME = "flow-st8"


def _app_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        root = Path(base) if base else Path.home() / "AppData" / "Roaming"
        return root / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_CONFIG_HOME")
    root = Path(base) if base else Path.home() / ".config"
    return root / APP_NAME


APP_DIR = _app_dir()
CONFIG_PATH = APP_DIR / "config.toml"
LOG_PATH = APP_DIR / f"{APP_NAME}.log"


def legacy_app_dir() -> Path | None:
    """Pre-rename %APPDATA%/whisprflow directory. Windows only; None elsewhere."""
    if sys.platform != "win32":
        return None
    base = os.environ.get("APPDATA")
    return Path(base) / "whisprflow" if base else None
