"""OS permission checks.

Only macOS gates anything today: reading the keyboard globally requires the
Accessibility grant, and without it the event tap installs but never fires —
a silent failure, which is exactly what this module exists to avoid.

Every function is safe to call on any platform; non-macOS reports "granted".
"""

import logging
import subprocess
import sys

log = logging.getLogger(__name__)

IS_MACOS = sys.platform == "darwin"

_ACCESSIBILITY_PANE = (
    "x-apple.systempreferences:com.apple.preference.security"
    "?Privacy_Accessibility"
)


def accessibility_granted(prompt: bool = False) -> bool:
    """True when this process may observe the keyboard globally.

    prompt=True shows the system dialog offering to open System Settings. It
    only appears once per process per app identity, so call it deliberately.
    """
    if not IS_MACOS:
        return True
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))
    except Exception:
        log.exception("Accessibility check failed; assuming not granted.")
        return False


def open_accessibility_settings() -> None:
    """Open System Settings on the Accessibility pane."""
    if not IS_MACOS:
        return
    try:
        subprocess.run(["open", _ACCESSIBILITY_PANE], check=False)
    except Exception:
        log.exception("Could not open the Accessibility settings pane.")


def secure_input_active() -> bool:
    """True when a password field is focused.

    macOS then blocks every synthetic keyboard event, so injection cannot
    work — for us or for any other app. Worth reporting instead of looking
    broken.
    """
    if not IS_MACOS:
        return False
    try:
        from Quartz import IsSecureEventInputEnabled

        return bool(IsSecureEventInputEnabled())
    except Exception:
        return False


def describe_missing() -> str | None:
    """One-line summary of what is missing, or None when everything is set."""
    if not IS_MACOS:
        return None
    if not accessibility_granted():
        return (
            "flow-st8 precisa da permissão de Acessibilidade para ouvir o "
            "atalho global. Ajustes do Sistema → Privacidade e Segurança → "
            "Acessibilidade."
        )
    return None
