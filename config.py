"""Configuration management for flow-st8."""

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(os.environ.get("APPDATA", "")) / "flow-st8"
CONFIG_PATH = APP_DIR / "config.toml"

DEFAULT_CONFIG_TOML = """\
[model]
# Opcoes: "tiny", "base", "small", "medium", "large-v3-turbo"
# large-v3-turbo: melhor qualidade, ~0.5s em GPU CUDA, ~10-20s em CPU
name = "large-v3-turbo"
language = "pt"
# Prompt inicial melhora qualidade pt-BR sem trocar modelo
initial_prompt = "Transcrição em português brasileiro."

[hotkey]
# Modos: "toggle" (press start/stop) ou "push_to_talk" (segura para gravar)
mode = "toggle"
# Formato: modificadores+tecla. Ex: "ctrl+win", "ctrl+alt+r"
key = "ctrl+win"

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
# Restaurar clipboard anterior apos colar
restore_clipboard = true

[feedback]
# Beeps sonoros para indicar estado
enabled = true

[startup]
autostart = true
"""


@dataclass
class ModelConfig:
    name: str = "large-v3-turbo"
    language: str = "pt"
    initial_prompt: str = "Transcrição em português brasileiro."


@dataclass
class HotkeyConfig:
    mode: str = "toggle"
    key: str = "ctrl+win"
    stop_key: str = "space"


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
    restore_clipboard: bool = True


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


def _serialize_config(config: Config) -> str:
    return f"""[model]
name = "{config.model.name}"
language = "{config.model.language}"
initial_prompt = "{config.model.initial_prompt}"

[hotkey]
mode = "{config.hotkey.mode}"
key = "{config.hotkey.key}"
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

    legacy_keys = {"ctrl+shift+space", "ctrl+win+space"}
    if data.get("hotkey", {}).get("key") in legacy_keys:
        data.setdefault("hotkey", {})["key"] = "ctrl+win"
        data["hotkey"]["mode"] = "toggle"
        dirty = True

    if data.get("model", {}).get("name") == "base":
        data.setdefault("model", {})["name"] = "large-v3-turbo"
        dirty = True

    if data.get("audio", {}).get("max_seconds", 0) < 210:
        data.setdefault("audio", {})["max_seconds"] = 210
        dirty = True

    if dirty:
        _save_config(_dict_to_config(data))

    return _dict_to_config(data)
