"""Windows autostart management via HKCU\\...\\Run registry key."""

import logging
import sys
import winreg
from pathlib import Path

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "flow-st8"


def _build_command() -> str:
    """Build the command line that launches this app without a console window."""
    main_py = Path(__file__).resolve().parent / "main.py"

    # Use pythonw.exe (no console window) instead of python.exe.
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw

    return f'"{exe}" "{main_py}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable() -> bool:
    try:
        cmd = _build_command()
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, cmd)
        log.info("Autostart enabled: %s", cmd)
        return True
    except OSError:
        log.exception("Failed to enable autostart")
        return False


def disable() -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as k:
            winreg.DeleteValue(k, APP_NAME)
        log.info("Autostart disabled.")
        return True
    except FileNotFoundError:
        return True
    except OSError:
        log.exception("Failed to disable autostart")
        return False


def sync(desired: bool) -> None:
    """Ensure registry matches the desired state."""
    current = is_enabled()
    if desired and not current:
        enable()
    elif not desired and current:
        disable()
