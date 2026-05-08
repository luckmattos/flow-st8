# flow-st8

![flow-st8](assets/banner.svg)

Local voice-to-text for Windows. Hold `Ctrl+Win` to record, release to transcribe, and flow-st8 pastes your words wherever your cursor is. No cloud, no subscription, no audio leaving your machine.

---

## Highlights

- Local Whisper transcription with GPU acceleration when available
- Push-to-talk and hands-free toggle hotkeys
- Live recording badge with audio-reactive bars
- System tray menu for model switching, hotkey remapping, autostart, and quit
- Packaged Windows installer and app executable
- Privacy-first: audio is processed locally and discarded

---

## Install

Download and run the latest `flow-st8-setup.exe` from GitHub Releases.

The setup wizard detects your hardware, installs dependencies, writes config, creates a desktop shortcut, and can enable autostart.

For development:

```bash
git clone https://github.com/luckmattos/flow-st8.git
cd flow-st8
python install.py
```

---

## Run

Installed users can launch flow-st8 from the desktop shortcut or startup entry.

Development users can run:

```bash
python main.py
```

The app lives in the system tray while it listens for hotkeys.

---

## How To Use

| Hotkey | Behavior |
|---|---|
| Hold `Ctrl+Win` | Push-to-talk: hold to record, release to transcribe |
| Press `Ctrl+Win+O` | Toggle: press to start, press again to stop |

1. Hold `Ctrl+Win`; the floating badge appears and reacts to your voice.
2. Talk normally; silence is filtered with VAD.
3. Release `Ctrl+Win`; flow-st8 transcribes and pastes the text.

Tip: press `Ctrl+Win+O` mid-hold to lock recording in hands-free mode.

---

## App vs Installer

| File | Purpose |
|---|---|
| `flow-st8.exe` | The actual background app: hotkeys, recording, transcription, overlay, tray |
| `flow-st8-setup.exe` | The setup wizard: installs/updates files, dependencies, config, shortcuts |

The installer is not the daily app. After setup, run `flow-st8.exe` or the shortcut created by the installer.

---

## Configuration

Config file:

```text
%APPDATA%\flow-st8\config.toml
```

Example:

```toml
[model]
name = "large-v3-turbo"
language = "auto"
initial_prompt = ""

[hotkey]
hold_key = "ctrl+win"
toggle_key = "ctrl+win+o"

[audio]
device_index = -1
sample_rate = 16000
channels = 1
chunk_ms = 32
max_seconds = 210
gain = 1.8

[vad]
enabled = true
speech_threshold = 0.5

[startup]
autostart = true
```

---

## Models

| Model | Size | GPU | CPU | Quality |
|---|---:|---:|---:|---|
| `tiny` | 39 MB | ~0.1s | 1-2s | Low |
| `base` | 138 MB | ~0.3s | 3-5s | Decent |
| `small` | 460 MB | ~0.7s | 8-12s | Good |
| `medium` | 1.5 GB | ~1.5s | 25-35s | Very good |
| `large-v3-turbo` | 1.5 GB | ~0.4-1.2s | 20-45s | Excellent |

No GPU? Use `base` or `small` for a practical experience.

---

## Privacy

flow-st8 does not:

- Send audio anywhere
- Capture screenshots
- Require internet after models are downloaded
- Store your recordings

Everything runs locally.

---

## Stack

| Layer | Technology |
|---|---|
| Speech-to-text | OpenAI Whisper + PyTorch |
| Voice detection | Silero VAD |
| Global hotkey | Win32 low-level keyboard hook via `ctypes` |
| Audio capture | `sounddevice` |
| Text injection | Clipboard + Win32 `SendInput` |
| UI | Tkinter overlay + pystray |
| Packaging | PyInstaller |

---

## Roadmap

- [x] Packaged Windows app
- [x] Setup wizard
- [x] Live audio overlay
- [ ] Auto-updater
- [ ] Transcription history
- [ ] Per-app custom prompts

---

## Author

[luckmattos](https://github.com/luckmattos). MIT license.
