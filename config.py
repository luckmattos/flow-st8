"""Configuration management for flow-st8."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", "")) / "flow-st8"
CONFIG_PATH = APP_DIR / "config.toml"

WHISPER_MODELS: list[tuple[str, str]] = [
    ("tiny",           "tiny           — rápido, qualidade baixa"),
    ("base",           "base           — equilibrado, CPU ok"),
    ("small",          "small          — boa qualidade, CPU ok"),
    ("medium",         "medium         — ótima qualidade ★ GPU"),
    ("large-v3-turbo", "large-v3-turbo — melhor qualidade ★ GPU"),
]

_HOTKEY_MODIFIERS = {"ctrl", "control", "win", "super", "shift", "alt"}

DEFAULT_CONFIG_TOML = """\
[model]
# Opcoes: "tiny", "base", "small", "medium", "large-v3-turbo"
# large-v3-turbo: melhor qualidade, ~0.5s em GPU CUDA, ~10-20s em CPU
name = "large-v3-turbo"
# "auto" detecta o idioma automaticamente; ou force "pt", "en", etc.
language = "auto"
# Prompt inicial so e usado quando language != "auto"
initial_prompt = ""

[hotkey]
# Modos: "toggle" (press start/stop) ou "push_to_talk" (segura para gravar)
mode = "toggle"
# hold_key: segurar para gravar (push-to-talk)
hold_key = "ctrl+win"
# toggle_key: pressionar para iniciar/parar
toggle_key = "ctrl+win+o"

[audio]
# -1 = microfone padrao do sistema
device_index = -1
sample_rate = 16000
channels = 1
# Silero VAD v6 requer exatamente 512 samples = 32ms a 16kHz
chunk_ms = 32
# Tempo maximo de gravacao em segundos (seguranca)
max_seconds = 210
# Ganho aplicado internamente antes da transcricao
gain = 1.8

[vad]
enabled = true
# Tempo de silencio (ms) apos fala para parar automaticamente
silence_threshold_ms = 1200
# Probabilidade minima para considerar como fala (0.0-1.0)
speech_threshold = 0.5

[injection]
# Metodo: "clipboard" (Ctrl+V) ou "sendinput" (char por char)
method = "clipboard"
# Keep transcribed text as the most recent clipboard item
restore_clipboard = false

[feedback]
# Beeps sonoros para indicar estado
enabled = true

[startup]
autostart = true
"""


@dataclass
class ModelConfig:
    name: str = "large-v3-turbo"
    language: str = "auto"
    initial_prompt: str = ""


@dataclass
class HotkeyConfig:
    mode: str = "toggle"
    hold_key: str = "ctrl+win"
    toggle_key: str = "ctrl+win+o"
    stop_key: str = "space"

    @property
    def key(self) -> str:
        """Compat: returns hold_key (used in legacy log messages)."""
        return self.hold_key


@dataclass
class AudioConfig:
    device_index: int = -1
    sample_rate: int = 16000
    channels: int = 1
    chunk_ms: int = 32
    max_seconds: int = 210
    gain: float = 1.8

    @property
    def chunk_frames(self) -> int:
        """Silero VAD v6 requires exactly 512 samples at 16kHz."""
        return 512


@dataclass
class VADConfig:
    enabled: bool = True
    silence_threshold_ms: int = 1200
    speech_threshold: float = 0.5


@dataclass
class InjectionConfig:
    method: str = "clipboard"
    restore_clipboard: bool = False


@dataclass
class FeedbackConfig:
    enabled: bool = True


@dataclass
class StartupConfig:
    autostart: bool = True


@dataclass
class Config:
    model: ModelConfig = field(default_factory=ModelConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    injection: InjectionConfig = field(default_factory=InjectionConfig)
    feedback: FeedbackConfig = field(default_factory=FeedbackConfig)
    startup: StartupConfig = field(default_factory=StartupConfig)


def _dict_to_config(data: dict) -> Config:
    return Config(
        model=ModelConfig(**data.get("model", {})),
        hotkey=HotkeyConfig(**data.get("hotkey", {})),
        audio=AudioConfig(**data.get("audio", {})),
        vad=VADConfig(**data.get("vad", {})),
        injection=InjectionConfig(**data.get("injection", {})),
        feedback=FeedbackConfig(**data.get("feedback", {})),
        startup=StartupConfig(**data.get("startup", {})),
    )


def _hotkey_parts(hotkey: str) -> set[str]:
    return {part.strip().lower() for part in hotkey.split("+") if part.strip()}


def _is_modifier_only_hotkey(hotkey: str) -> bool:
    parts = _hotkey_parts(hotkey)
    return bool(parts) and parts <= _HOTKEY_MODIFIERS


def _serialize_config(config: Config) -> str:
    return f"""[model]
name = "{config.model.name}"
language = "{config.model.language}"
initial_prompt = "{config.model.initial_prompt}"

[hotkey]
mode = "{config.hotkey.mode}"
hold_key = "{config.hotkey.hold_key}"
toggle_key = "{config.hotkey.toggle_key}"
stop_key = "{config.hotkey.stop_key}"

[audio]
# -1 = microfone padrao do sistema
device_index = {config.audio.device_index}
sample_rate = {config.audio.sample_rate}
channels = {config.audio.channels}
# Silero VAD v6 requer exatamente 512 samples = 32ms a 16kHz
chunk_ms = {config.audio.chunk_ms}
# Tempo maximo de gravacao em segundos (seguranca)
max_seconds = {config.audio.max_seconds}
# Ganho aplicado internamente antes da transcricao
gain = {config.audio.gain}

[vad]
enabled = {str(config.vad.enabled).lower()}
# Tempo de silencio (ms) apos fala para parar automaticamente
silence_threshold_ms = {config.vad.silence_threshold_ms}
# Probabilidade minima para considerar como fala (0.0-1.0)
speech_threshold = {config.vad.speech_threshold}

[injection]
# Metodo: "clipboard" (Ctrl+V) ou "sendinput" (char por char)
method = "{config.injection.method}"
# Restaurar clipboard anterior apos colar
restore_clipboard = {str(config.injection.restore_clipboard).lower()}

[feedback]
# Beeps sonoros para indicar estado
enabled = {str(config.feedback.enabled).lower()}

[startup]
autostart = {str(config.startup.autostart).lower()}
"""


def _save_config(config: Config) -> None:
    CONFIG_PATH.write_text(_serialize_config(config), encoding="utf-8")


def save_config(config: Config) -> None:
    """Persist the current config to disk."""
    APP_DIR.mkdir(parents=True, exist_ok=True)
    _save_config(config)


def _migrate_legacy_dir() -> None:
    """Move old %APPDATA%/whisprflow -> %APPDATA%/flow-st8 (one-shot)."""
    legacy_dir = Path(os.environ.get("APPDATA", "")) / "whisprflow"
    if legacy_dir.exists() and not APP_DIR.exists():
        legacy_dir.rename(APP_DIR)


def load_config() -> Config:
    """Load config from TOML file, creating default if it doesn't exist."""
    _migrate_legacy_dir()
    APP_DIR.mkdir(parents=True, exist_ok=True)

    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(DEFAULT_CONFIG_TOML, encoding="utf-8")

    with open(CONFIG_PATH, "rb") as f:
        data = tomllib.load(f)

    dirty = False

    hotkey_data = data.setdefault("hotkey", {})
    # Migrate old "key" field → "hold_key"
    if "key" in hotkey_data and "hold_key" not in hotkey_data:
        old_key = hotkey_data.pop("key")
        legacy_keys = {"ctrl+shift+space", "ctrl+win+space"}
        hotkey_data["hold_key"] = "ctrl+win" if old_key in legacy_keys else old_key
        dirty = True
    if "toggle_key" not in hotkey_data:
        hotkey_data["toggle_key"] = "ctrl+win+o"
        dirty = True
    if not _is_modifier_only_hotkey(str(hotkey_data.get("hold_key", ""))):
        old_hold_key = str(hotkey_data.get("hold_key", "")).strip().lower()
        hotkey_data["hold_key"] = "ctrl+win"
        if old_hold_key and "+" not in old_hold_key:
            hotkey_data["toggle_key"] = f"ctrl+win+{old_hold_key}"
        dirty = True

    if data.get("model", {}).get("name") == "base":
        data.setdefault("model", {})["name"] = "large-v3-turbo"
        dirty = True

    if data.get("audio", {}).get("max_seconds", 0) < 210:
        data.setdefault("audio", {})["max_seconds"] = 210
        dirty = True

    # Flip restore_clipboard to false — transcribed text should stay as latest clipboard item
    if data.get("injection", {}).get("restore_clipboard", False):
        data.setdefault("injection", {})["restore_clipboard"] = False
        dirty = True

    if dirty:
        _save_config(_dict_to_config(data))

    return _dict_to_config(data)
