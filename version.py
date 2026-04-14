"""Project version helpers."""

from pathlib import Path

VERSION_PATH = Path(__file__).with_name("VERSION")


def get_version() -> str:
    """Return the current application version."""
    return VERSION_PATH.read_text(encoding="utf-8").strip()


__version__ = get_version()
