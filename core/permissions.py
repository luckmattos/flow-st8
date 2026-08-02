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


def microphone_granted() -> bool | None:
    """True/False when known, None when it cannot be determined.

    Returns None rather than False on failure: the mic prompt also appears the
    first time sounddevice opens a stream, so an inconclusive check must not
    block startup.
    """
    if not IS_MACOS:
        return True
    try:
        import AVFoundation

        status = AVFoundation.AVCaptureDevice.authorizationStatusForMediaType_(
            AVFoundation.AVMediaTypeAudio
        )
        # 0 notDetermined, 1 restricted, 2 denied, 3 authorized
        if status == 3:
            return True
        if status in (1, 2):
            return False
        return None
    except Exception:
        log.debug("Microphone status unavailable.", exc_info=True)
        return None


def voiceover_running() -> bool:
    """True when VoiceOver is on.

    It claims Ctrl+Option as its own modifier — the exact combo flow-st8
    defaults to — and swallows everything built on it.
    """
    if not IS_MACOS:
        return False
    try:
        out = subprocess.run(
            ["pgrep", "-x", "VoiceOver"], capture_output=True, text=True
        )
        return out.returncode == 0
    except Exception:
        return False


def describe_missing(hold_key: str = "") -> str | None:
    """One-line summary of what is missing, or None when everything is set."""
    if not IS_MACOS:
        return None

    if not accessibility_granted():
        return (
            "flow-st8 precisa da permissão de Acessibilidade para ouvir o "
            "atalho global. Ajustes do Sistema → Privacidade e Segurança → "
            "Acessibilidade."
        )

    if microphone_granted() is False:
        return (
            "O acesso ao microfone está negado. Ajustes do Sistema → "
            "Privacidade e Segurança → Microfone."
        )

    if voiceover_running() and "alt" in hold_key:
        return (
            "O VoiceOver está ligado e usa Ctrl+Option como tecla dele, então "
            "vai engolir o atalho do flow-st8. Escolha outro atalho no menu."
        )

    return None
