# Arquitetura - flow-st8

## Visão geral

**flow-st8** é um aplicativo Windows que captura áudio via hotkey global, transcreve localmente com Whisper (OpenAI), detecta silêncio com Silero VAD, e injeta o resultado no clipboard. Funciona 100% offline, sem nuvem, totalmente privado.

### Propósito

Permitir ditado de voz rápido e privado em qualquer campo de texto do Windows:
- Pressiona `Ctrl+Win` → grava
- Fala (pausas não importam, silêncio é descartado)
- Pressiona `Ctrl+Win` de novo → transcreve e cola

**Não é:**
- Um app de transcription em batch
- Uma ferramenta de análise de áudio
- Um assistente de IA genérico

**É:**
- Um input method — substitui digitação por voz
- Local-first — dados nunca saem do PC
- Real-time feedback — UI mínima, só tray icon

---

## Fluxo de dados

```
ENTRADA
  ↓
Microfone (sounddevice 16kHz 512 samples/32ms)
  ↓
Silero VAD (detecta fala vs silêncio)
  ├─ Silêncio → descarta chunk
  └─ Fala → buffer com padding pré/pós
  ↓
Whisper (OpenAI, CPU ou GPU CUDA)
  ├─ CUDA (RTX): fp16, ~0.4s por frase
  └─ CPU: fp32, ~8-45s por frase
  ↓
Pós-processamento (capitaliza, limpa espaços)
  ↓
Injeção (clipboard → Ctrl+V → restaura clipboard)
  ↓
SAÍDA (texto no campo ativo)
```

---

## Arquitetura de threads

```
┌─────────────────────────────────────────────────────┐
│ MAIN THREAD                                         │
│ └─ pystray.Icon.run() — message loop do tray       │
│    (bloqueia indefinidamente até .stop())          │
└─────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────┐
│ HOTKEY THREAD (HotkeyManager)                       │
│ └─ Win32 GetMessage() loop                          │
│    └─ WH_KEYBOARD_LL hook pra Ctrl+Win             │
│    └─ RegisterHotKey pra outros atalhos            │
│ Comunica: callback direto pro app                  │
└─────────────────────────────────────────────────────┘
        ↓
┌─────────────────────────────────────────────────────┐
│ WORKER THREAD (ThreadPoolExecutor)                  │
│ └─ _recording_pipeline()                           │
│    ├─ AudioRecorder.record_stream() [sync]         │
│    ├─ SileroVAD.is_speech() [sync]                 │
│    ├─ Transcriber.transcribe() [sync, CUDA/CPU]    │
│    └─ TextInjector.inject() [sync]                 │
│ Max workers: 2 (1 transcrição, 1 buffer)           │
└─────────────────────────────────────────────────────┘
```

**Por que separado:**
- Main thread não pode bloquear em I/O (tray fica travado)
- Hotkey thread deve ter latência mínima (GetMessage dedicada)
- Recording/transcription pode levar segundos (worker async)
- Queue.Queue para comunicação thread-safe

---

## Módulos

### `main.py`
**Entry point.** Inicializa logging UTF-8, carrega config, cria app, executa autostart, inicia tray.

**Responsabilidades:**
- Configurar ambiente (stdout UTF-8)
- Carregar config.toml
- Sincronizar autostart com winreg
- Instanciar `FlowSt8App` e `TrayIcon`
- Bloquear em `tray.run()` até close

### `config.py`
**Config management.** TOML ← → dataclasses, migração automática.

**Arquivo:** `%APPDATA%\flow-st8\config.toml`

**Responsabilidades:**
- Load/parse TOML via `tomllib` (stdlib)
- Auto-migrate old configs (whisprflow → flow-st8, base → large-v3-turbo, etc.)
- Dataclass validation
- Serialize back to TOML

**Estrutura:**
```
Config
├── ModelConfig (name, language, initial_prompt)
├── HotkeyConfig (key, mode)
├── AudioConfig (device_index, sample_rate, chunk_ms, max_seconds, gain)
├── VADConfig (enabled, silence_threshold_ms, speech_threshold)
├── InjectionConfig (method, restore_clipboard)
├── FeedbackConfig (enabled)
└── StartupConfig (autostart)
```

### `app.py` — `FlowSt8App`
**Orquestrador principal.** Conecta recorder, VAD, transcriber, injector.

**Responsabilidades:**
- State machine (idle ↔ recording ↔ processing)
- Audio collection com VAD filtering
- Pipeline de transcrição
- Thread-safe state lock
- Lifecycle (start/shutdown)

**Métodos principais:**
- `start()` — preload model, start hotkey thread
- `_handle_main_hotkey()` — toggle ou start recording
- `_collect_audio()` — record + VAD filtering
- `_recording_pipeline()` — full chain: record → transcribe → inject
- `shutdown()` — clean shutdown

### `hotkey.py` — `HotkeyManager`
**Hotkey global.** Win32 RegisterHotKey + WH_KEYBOARD_LL para modifier-only combos (Ctrl+Win).

**Por quê dois métodos:**
- `RegisterHotKey()` → para atalhos normais (ex: Ctrl+Alt+S)
- `WH_KEYBOARD_LL` hook → para Ctrl+Win (modifier-only, RegisterHotKey não suporta)

**Responsabilidades:**
- Parse hotkey strings (ex: "ctrl+win", "alt+shift+f12")
- Register hotkeys via Win32
- Detectar Ctrl+Win via hook global (teclado)
- Thread com GetMessage loop
- Callbacks thread-safe (lock)

**Estados internos:**
```
_ctrl_down, _win_down, _combo_fired → state do hook
_suppress_win_keyup → evita Start menu abrir
```

### `recorder.py` — `AudioRecorder`
**Captura de microfone.** sounddevice, 16kHz mono float32, chunks de 512 samples (32ms).

**Responsabilidades:**
- Iniciar stream de mic
- Yield chunks até stop_event
- Respeitar max_seconds (safety)
- Handle device selection (-1 = default)

**Generator pattern:**
```python
for chunk in recorder.record_stream():
    # chunk é np.ndarray float32 [512]
    # 1D mono, não 2D estéreo
```

### `vad.py` — `SileroVAD`
**Voice Activity Detection.** Silero VAD v6, detecção de fala vs silêncio.

**Responsabilidades:**
- Lazy load modelo ONNX (via `silero-vad` pip)
- Processar chunks de 512 samples exatos
- Retornar `P(fala)` 0.0-1.0
- Thread-safe (lock)

**Requisito técnico:**
- Entrada: exatamente 512 samples @ 16kHz
- Saída: float 0.0-1.0 (probabilidade de fala)
- Sem estado entre chunks (stateless)

### `transcriber.py` — `Transcriber`
**Transcrição Whisper.** Lazy load, auto-detect CUDA/CPU, fp16 em GPU.

**Responsabilidades:**
- Load modelo Whisper (`large-v3-turbo` padrão)
- Auto-detect `torch.cuda.is_available()`
- Transcribe com `language="pt"`, `initial_prompt`
- Filter RMS + segments confidence para evitar alucinações
- Thread-safe (lock)

**Configurações importantes:**
```python
fp16=True se CUDA else False
language="pt"  # forcado
no_speech_threshold=0.6
compression_ratio_threshold=2.4
task="transcribe"  # (não translate)
```

### `injector.py` — `TextInjector`
**Injeção de texto.** Clipboard + SendInput Ctrl+V.

**Responsabilidades:**
- Backup clipboard anterior
- Copiar texto pra clipboard
- Simular Ctrl+V via Win32 SendInput
- Restaurar clipboard original

**Por quê não só SendInput char-by-char:**
- Mais rápido (1 operação vs 100+ SendInput calls)
- Respeita encoding (unicode, emojis, etc.)
- Safer com apps que filtram input

### `audio_feedback.py`
**Beeps de feedback.** winsound (stdlib).

**Responsabilidades:**
- `beep_start()` — 440Hz 100ms
- `beep_stop()` — 440Hz 100ms
- `beep_done()` — 660Hz 80ms (sucesso)
- `beep_warning()` — 1200+1400Hz (aviso tempo)
- `beep_error()` — 220Hz 300ms (erro)

Cada beep roda em thread separada (não bloqueia).

### `tray.py` — `TrayIcon`
**UI: system tray icon.** pystray + Pillow.

**Responsabilidades:**
- Gerar ícone dinâmico (PIL)
- Menu com ações (gravar, autostart toggle, sair)
- Update estado (idle/recording/processing/error)
- Non-blocking (callbacks retornam rápido)

**Estados visuais:**
```
Cinza (80, 80, 80)   → idle
Vermelho (220, 50, 50) → recording
Azul (50, 150, 220)  → processing
Laranja (220, 120, 50) → error
```

### `autostart.py`
**Autostart via winreg.** HKCU\Software\Microsoft\Windows\CurrentVersion\Run

**Responsabilidades:**
- `is_enabled()` — check registry
- `enable()` — write registry (pythonw.exe main.py)
- `disable()` — delete registry
- `sync(desired)` — ensure registry matches config

**Comando registrado:**
```
"C:\...\pythonw.exe" "C:\...\main.py"
```
(pythonw = sem console window)

---

## Fluxo de inicialização

```
python main.py
  ↓
_setup_utf8_stdio() — força UTF-8 em stdout/stderr
  ↓
load_config() — load/migrate TOML
  ↓
autostart.sync(config.startup.autostart) — escreve/deleta registry
  ↓
FlowSt8App(config)
  ├─ Transcriber(config.model) — lazy load
  ├─ AudioRecorder(config.audio)
  ├─ SileroVAD() — lazy load
  ├─ TextInjector(config.injection)
  ├─ HotkeyManager(hotkey bindings)
  └─ TrayIcon(self)
  ↓
app.start()
  ├─ transcriber.preload() — aquece modelo (thread)
  └─ hotkey.start() — inicia hotkey thread
  ↓
tray.run() — BLOQUEIA até .stop()
  (main thread agora apenas message loop do pystray)
  ↓
user presses Ctrl+Win → callback
  ↓
app.shutdown() + exit
```

---

## Decisões de design

### Por que Python (não C#, Rust, etc.)?

| Critério | Python | C# | Rust |
|---|---|---|---|
| Prototipagem | ⭐⭐⭐ | ⭐⭐ | ⭐ |
| Dependências STT | Whisper (oficialmente pip) | wrapper | wrapper |
| GUI tray | pystray/PIL | Windows Forms | egui (immaturo) |
| Audio | sounddevice (maduro) | NAudio (bom) | cpal (novo) |
| Windows interop | ctypes (stdlib) | P/Invoke (nativo) | FFI (complexo) |
| Manutenibilidade | Alta (código claro) | Média | Baixa |
| **Escolha** | ✅ | ❌ | ❌ |

Python permite prototipar rápido, usar Whisper oficialmente, e manter código legível.

### Por que não async/await?

Recording/transcrição são **CPU-bound** (Whisper roda em CPU/GPU), não I/O-bound. `asyncio` não muda nada — precisa multiprocessing ou threading. Threading com lock simples é mais direto.

### Por quê Silero VAD?

- Local (não cloud)
- Modelo pequeno (40MB)
- Aceita chunks de 512 samples (fit com sounddevice)
- Rápido (~1ms por chunk, CPU)

Alternativas: `pyannote`, `WebRTC VAD` — ambas maiores/lentas.

### Por que Ctrl+Win (não Ctrl+Shift+Space)?

Ctrl+Shift altera layout de teclado em Windows (pt-BR ↔ en-US). Win+Space idem. Ctrl+Win é inócuo — nenhuma função padrão.

Implementação: WH_KEYBOARD_LL hook (modifier-only RegisterHotKey não funciona).

### Por que clipboard (não SendInput direto)?

1. **Unicode**: clipboard preserva 100% — SendInput char-by-char quebra com emojis/acentos
2. **Velocidade**: 1 operação vs 100+ SendInput calls
3. **Compatibilidade**: apps que filtram keyboard input não bloqueiam clipboard

Trade-off: app pode ter clipboard modificado entre start/end (rare em prática).

---

## Performance notes

### Whisper
- `large-v3-turbo`: 1.5GB VRAM (GPU)
- Load time: ~5s (primeira vez), ~1s (cached)
- Inference: 0.4-1.2s por frase curta (GPU RTX 4060)

### Silero VAD
- ONNX runtime: <1MB
- Processamento: ~0.5ms por chunk (CPU)
- Zero latency percepção

### Win32 Hotkey
- RegisterHotKey latency: <1ms
- WH_KEYBOARD_LL latency: <5ms

### Clipboard
- Cópia: <1ms
- Paste (SendInput Ctrl+V): app-dependent, típico <100ms

---

## Extensibilidade

### Adicionar novo modelo STT
Editar `transcriber.py`, mudar nome:
```python
self._model = whisper.load_model("medium", device=self._device)
```

### Adicionar auto-save
Em `app.py` `_recording_pipeline()`, após sucesso:
```python
with open("transcribed.txt", "a") as f:
    f.write(f"{time.now()}: {text}\n")
```

### Suporte a outro idioma
Em `config.toml`:
```toml
language = "en"  # "pt" → "en"
initial_prompt = "Transcription in English."
```

### Mudar hotkey
Em `config.toml`:
```toml
key = "ctrl+alt+v"  # Ctrl+Win → Ctrl+Alt+V
```

---

## Debugging

### Ativar verbose logging
Em `main.py`:
```python
logging.basicConfig(level=logging.DEBUG)  # INFO → DEBUG
```

### Verificar registro autostart
```
Win+R → regedit → HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
```
Procure chave `flow-st8`.

### Verificar GPU
```bash
python -c "import torch; print(torch.cuda.is_available())"
```

### Verificar Whisper model
```bash
python -c "import whisper; m = whisper.load_model('large-v3-turbo')"
```

---

## Roadmap

- [ ] Auto-updater (GitHub releases)
- [ ] Histórico de transcrições (UI ou arquivo)
- [ ] Contexto por app ativo (prompt customizado por app)
- [ ] Suporte a outro idioma (auto-detect)
- [ ] Atalho pra editar último resultado
- [ ] API HTTP local (pra integrar com outras apps)
