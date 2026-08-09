"""Shared hotkey vocabulary.

Combos are written as "+"-joined key names. Every platform has one modifier that
plays the role Windows gives to the Win key; users may spell it "win", "super",
"cmd" or "meta" and it is normalized to OS_MOD, which each backend then maps to
its own virtual key code.
"""

import sys

# The OS-level modifier, spelled the way this platform's users expect to read it.
OS_MOD = "cmd" if sys.platform == "darwin" else "win"

_OS_MOD_ALIASES = {"win", "super", "cmd", "meta"}
_ALT_ALIASES = {"alt", "option", "opt"}
_CTRL_ALIASES = {"ctrl", "control"}

MODIFIERS = _CTRL_ALIASES | _ALT_ALIASES | _OS_MOD_ALIASES | {"shift"}

# Deliberately not "ctrl+<OS_MOD>" on macOS. Push-to-talk holds the combo for
# several seconds while the user speaks, and every destructive macOS shortcut
# carries Cmd — ctrl+cmd+q locks the screen. Ctrl+Option has no destructive
# system binding, so a stray keystroke mid-recording is harmless and the tap
# never has to suppress anything.
if sys.platform == "darwin":
    DEFAULT_HOLD = "ctrl+alt"  # displayed as ctrl+option / ⌃⌥
    DEFAULT_TOGGLE = "ctrl+alt+o"
else:
    DEFAULT_HOLD = f"ctrl+{OS_MOD}"
    DEFAULT_TOGGLE = f"ctrl+{OS_MOD}+o"


def _canonical(part: str) -> str:
    part = part.strip().lower()
    if part in _OS_MOD_ALIASES:
        return OS_MOD
    if part in _ALT_ALIASES:
        return "alt"
    if part in _CTRL_ALIASES:
        return "ctrl"
    return part


def normalize(combo: str) -> str:
    """Lowercase a combo and rewrite OS-modifier aliases, preserving order."""
    seen: list[str] = []
    for raw in combo.split("+"):
        part = _canonical(raw)
        if part and part not in seen:
            seen.append(part)
    return "+".join(seen)


def parts(combo: str) -> set[str]:
    """Canonical key names in a combo."""
    return {_canonical(p) for p in combo.split("+") if p.strip()}


def is_modifier_only(combo: str) -> bool:
    """True when the combo has no regular key — e.g. "ctrl+win"."""
    p = parts(combo)
    return bool(p) and p <= MODIFIERS


# How each platform writes a shortcut. Storage stays canonical either way, so
# the TOML is portable and only the label changes.
_SYMBOLS = {"ctrl": "⌃", "alt": "⌥", "cmd": "⌘", "shift": "⇧"}
_WINDOWS_LABELS = {"ctrl": "Ctrl", "alt": "Alt", "win": "Win", "shift": "Shift"}
_DARWIN_WORDS = {"ctrl": "Control", "alt": "Option", "cmd": "Command", "shift": "Shift"}


def display(combo: str) -> str:
    """Render a combo the way this platform's users expect to read it."""
    rendered = []
    for part in normalize(combo).split("+"):
        if not part:
            continue
        if sys.platform == "darwin":
            rendered.append(_SYMBOLS.get(part, part.upper()))
        else:
            rendered.append(_WINDOWS_LABELS.get(part, part.upper()))
    return "".join(rendered) if sys.platform == "darwin" else "+".join(rendered)


def display_words(combo: str) -> str:
    """Full key names joined with '+' — for prose (hints, tooltips), where the
    tight symbol form `display()` uses for menus reads as too cramped."""
    rendered = []
    for part in normalize(combo).split("+"):
        if not part:
            continue
        if sys.platform == "darwin":
            rendered.append(_DARWIN_WORDS.get(part, part.upper()))
        else:
            rendered.append(_WINDOWS_LABELS.get(part, part.upper()))
    return "+".join(rendered)
