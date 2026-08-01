"""Bundled asset lookup, working both from source and from a frozen bundle."""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def resource_path(relative: str) -> Path:
    """Resolve a path relative to the project root (or the PyInstaller bundle)."""
    base = getattr(sys, "_MEIPASS", None)
    return (Path(base) if base else _REPO_ROOT) / relative
