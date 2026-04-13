# flow-st8

![flow-st8](banner.svg)

Local voice-to-text for Windows. Press `Ctrl+Win`, talk, press again — your words are transcribed by Whisper and pasted wherever your cursor is. No cloud, no subscription, no audio leaving your machine.

No cloud. No subscription. No screenshots sent to anyone's server.

---

## Requirements

- Windows 10/11
- Python 3.11+
- Microphone
- NVIDIA GPU recommended (RTX 20xx/30xx/40xx) — also works on CPU, slower

---

## Install

```bash
git clone https://github.com/luckmattos/flow-st8.git
cd flow-st8

python install.py
```

`install.py` detects your hardware and installs the right PyTorch version automatically:
- NVIDIA GPU found → installs CUDA build (~2.7GB, transcription <1s)
- No GPU → installs CPU build (lighter, slower transcription)

On first run, Whisper downloads the model (~1.5GB, one time only).

---

## Run

Double-click `flow-st8.vbs` — no terminal, no console window.

Or from terminal:
```bash
python main.py
```

A mic icon appears in the system tray. You're ready.

---

## How to use

1. Press `Ctrl+Win` — icon turns red, recording starts
2. Talk — pause freely, silence is filtered out automatically
3. Press `Ctrl+Win` again — icon turns blue, transcribing
4. Text is pasted wherever your cursor is

**Tray menu:** right-click the icon to record, toggle autostart, or quit.

---

## Choosing a model

Edit `%APPDATA%\flow-st8\config.toml` and change `name` under `[model]`.

| Model | Size | With NVIDIA GPU | CPU only | Quality |
|---|---|---|---|---|
| `tiny` | 39 MB | ~0.1s | 1-2s | Low, hallucinates |
| `base` | 138 MB | ~0.3s | 3-5s | Decent |
| `small` | 460 MB | ~0.7s | 8-12s | Good — best for CPU |
| `medium` | 1.5 GB | ~1.5s | 25-35s | Very good |
| `large-v3-turbo` | 1.5 GB | ~0.4-1.2s ⭐ | 20-45s | Excellent (default) |

> **No GPU?** Stick with `base` or `small`. Running `large-v3-turbo` on CPU means waiting 20-45 seconds per sentence — not practical.

**Benchmarks on RTX 4060 Laptop 8GB with `large-v3-turbo`:**

| Speech duration | GPU latency | CPU latency |
|---|---|---|
| 5s | ~0.4s | ~8s |
| 15s | ~1.2s | ~25s |
| 30s | ~2.5s | ~45s |

---

## Configuration

Config file: `%APPDATA%\flow-st8\config.toml` (auto-created on first run)

```toml
[model]
name = "large-v3-turbo"   # tiny | base | small | medium | large-v3-turbo
language = "pt"
initial_prompt = "Transcription in Brazilian Portuguese."

[hotkey]
mode = "toggle"           # toggle = press to start, press to stop
key = "ctrl+win"

[audio]
device_index = -1         # -1 = system default mic
max_seconds = 210         # 3m30s max per recording
gain = 1.8

[vad]
enabled = true
speech_threshold = 0.5

[startup]
autostart = true          # start with Windows
```

---

## Privacy

Commercial voice dictation apps send your audio — and often screenshots of your screen — to their servers every time you speak.

flow-st8 does not:
- Send audio anywhere
- Capture screenshots
- Require internet
- Store anything outside your machine

Everything runs locally. Audio is processed and discarded.

---

## Stack

| Layer | Technology |
|---|---|
| Speech-to-text | [OpenAI Whisper](https://github.com/openai/whisper) + PyTorch |
| Voice detection | [Silero VAD v6](https://github.com/snakers4/silero-vad) |
| Global hotkey | Win32 `WH_KEYBOARD_LL` hook via `ctypes` |
| Audio capture | [sounddevice](https://python-sounddevice.readthedocs.io/) |
| Text injection | pyperclip + Win32 `SendInput` |
| Tray icon | [pystray](https://github.com/moses-palmer/pystray) + Pillow |
| Config | TOML via stdlib `tomllib` |
| Autostart | `winreg` → `HKCU\...\Run` |

For architecture details see [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Roadmap

- [ ] Packaged `.exe` installer
- [ ] Auto-updater
- [ ] Language auto-detect
- [ ] Transcription history
- [ ] Per-app custom prompts

---

**Keywords:** speech-to-text, voice-dictation, whisper, local, offline, privacy, windows, cuda, python, real-time, hotkey

---

## Author

[luckmattos](https://github.com/luckmattos) — built with [Claude Code](https://claude.com/claude-code) as pair programmer. MIT license.
