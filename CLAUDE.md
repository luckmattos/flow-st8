# flow-st8

## O que e
Transcritor de voz local e leve. Windows funcional; port macOS em andamento (ver PROGRESS.md). Hotkey global -> grava voz -> transcreve localmente com Whisper -> cola no campo de texto ativo. Sem cloud, sem UI alem de tray icon.

## Stack
- Python 3.x
- openai-whisper (STT local)
- Silero VAD (deteccao de fala/silencio, auto-stop)
- Win32 RegisterHotKey via ctypes (hotkey global)
- pyperclip + SendInput (injecao de texto)
- pystray + Pillow (tray icon)
- sounddevice (captura mic + beeps de feedback)
- tomllib stdlib (config)

## Arquitetura
Nucleo portavel (`core/`) + shell de SO (`backends/`). O shell nao compartilha
codigo entre plataformas: cada backend e escrito do zero contra os protocolos.

```
main.py                    -> entry point, bootstrap

core/                      -> portavel, sem codigo de SO
  app.py                   -> orquestrador, conecta modulos
  config.py                -> config TOML
  paths.py                 -> %APPDATA% (Win) vs ~/Library/Application Support (mac)
  keys.py                  -> vocabulario de atalhos; OS_MOD = win|cmd
  resources.py             -> assets, funciona tambem no bundle PyInstaller
  recorder.py              -> captura microfone (sounddevice, 16kHz mono float32)
  vad.py                   -> Silero VAD wrapper (auto-stop apos 1.2s silencio)
  transcriber.py           -> Whisper wrapper (lazy load, thread-safe)
  audio_feedback.py        -> beeps gerados via sounddevice

backends/
  base.py                  -> protocolos (Hotkey/Injector/Overlay/Tray/Autostart)
  __init__.py              -> escolhe o shell por sys.platform; stubs fora do Windows
  windows/                 -> Win32 via ctypes
    hotkey.py injector.py overlay.py tray.py autostart.py
```

`import backends` nunca falha: plataforma sem shell recebe stubs que so
levantam erro no uso. E isso que mantem `core/` importavel no CI e no mac.

## Threading
- Main Thread: pystray.Icon.run() (bloqueia)
- Hotkey Thread: Win32 GetMessage loop
- Worker Thread: ThreadPoolExecutor (gravar + VAD + transcrever)
- Comunicacao: queue.Queue

## Decisoes tecnicas
- Modelo padrao: `large-v3-turbo` (1.5GB, melhor pt-BR). Opcoes: tiny/base/small/medium
- `initial_prompt="Transcricao em portugues brasileiro."` para bias pt-BR
- `language="pt"` forcado (sem auto-detect)
- Device auto-detect: CUDA+fp16 se disponivel, senao CPU+fp32
- Clipboard e restaurado apos paste
- Hotkey `ctrl+win` via WH_KEYBOARD_LL (modifier-only combo, RegisterHotKey nao suporta)
- MOD_NOREPEAT no RegisterHotKey para outros atalhos (evita repeticao)

## Convencoes
- Config em TOML, lido com tomllib (stdlib)
- Sem dependencias externas para funcionalidades que o stdlib cobre
- Icone tray gerado com Pillow inline (sem arquivos .ico)
- Autostart via winreg (HKCU\...\Run)

## Como rodar
```bash
pip install -r requirements.txt
python main.py
```

## Status atual
Ver PROGRESS.md para acompanhamento detalhado.
