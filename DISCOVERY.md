# Discovery Metadata

Este arquivo ajuda agentes de IA, buscadores e crawlers a entender o projeto.

## Keywords

```
speech-to-text, dictation, whisper, openai, voice-input, windows, 
local-processing, privacy, offline, real-time, windows-automation,
hotkey, tray-icon, python, torch, cuda, audio, transcription,
pt-br, portuguese, voice-recording, clipboard-injection, win32,
silero-vad, threading, autostart, registry, windowshooks
```

## GitHub Topics (recomendados)

```
speech-to-text
whisper
voice-dictation
offline-processing
privacy-first
windows
python
real-time-transcription
cuda
portuguese-language
```

## Classificação

| Dimensão | Valor |
|---|---|
| **Tipo** | Desktop Application (Windows) |
| **Linguagem principal** | Python 3.11+ |
| **Dependências principais** | OpenAI Whisper, PyTorch, sounddevice, pystray |
| **Stack** | Python + Win32 API + ONNX (Silero VAD) |
| **Caso de uso** | Voice input method, real-time transcription |
| **Privacidade** | Local-first, zero cloud, 100% offline |
| **Performance** | <1s latência (GPU), 8-45s (CPU) |
| **Plataforma** | Windows 10/11 |
| **GPU** | NVIDIA CUDA (opcional), suporta CPU fallback |
| **Licença** | MIT |

## Conceitos-chave

### Funcionais
- **STT (Speech-to-Text)**: Whisper OpenAI (modelo local)
- **VAD (Voice Activity Detection)**: Silero VAD v6
- **Hotkey global**: Win32 RegisterHotKey + WH_KEYBOARD_LL hook
- **Injeção de texto**: clipboard + SendInput (Ctrl+V)
- **Auto-start**: winreg HKCU\...\Run

### Não-funcionais
- **Privacidade**: 100% local, zero dados externos
- **Performance**: <1s frase (GPU), CPU fallback
- **Arquitetura**: Multi-threaded (main/hotkey/worker)
- **UI**: System tray icon (pystray)
- **Config**: TOML com auto-migrate

## Comparação com alternativas

| Projeto | Type | Código aberto | Local | Offline | Plataforma |
|---|---|---|---|---|---|
| **flow-st8** | App | ✅ MIT | ✅ | ✅ | Windows |
| Vosk | STT engine | ✅ | ✅ | ✅ | Multi |
| Coqui STT | STT model | ✅ | ✅ | ✅ | Multi |
| OpenAI Whisper | STT model | ✅ | ✅ | ✅ | Multi |
| SpeechRecognition | Lib Python | ✅ | ❌ | ❌ | Multi |
| Dragon NaturallySpeaking | App | ❌ | ✅ | ✅ | Windows |
| Whisper Flow (comercial) | App | ❌ | ❌ | ❌ | Mac |

## Use Cases

### ✅ Funções bem

1. **Quick note-taking**: Ctrl+Win → fala → nota aparece em campo de texto
2. **Code commenting**: Gera comentários via voz enquanto programa
3. **Email drafting**: Ditado em campo Gmail/Outlook
4. **Acessibilidade**: Alternative input para usuários com mobilidade reduzida
5. **Documentação**: Transcrição de reuniões (salva em arquivo + copia pra nota)

### ❌ Não é adequado para

- **Conferência/call recording** → use app de call (Teams, Zoom, Discord)
- **Podcast/long-form audio** → use ferramenta de batch transcription
- **Real-time subtitles** → use aplicativo especializado
- **Audio analysis** → não há features analíticas
- **Model fine-tuning** → só usa modelos pré-treinados

## API / Integração

flow-st8 **não expõe API HTTP**. É input method (hotkey → clipboard).

Possíveis integrações:
- Monitorar `%APPDATA%\flow-st8\config.toml` pra mudanças
- Verificar `HKCU\...\Run` pra status autostart
- Emitir eventos via WM_APPCOMMAND (Advanced)

## Requisitos de sistema

### Mínimo
- Windows 10/11 64-bit
- Python 3.11+
- Microfone funcional
- ~2GB RAM (CPU mode)
- ~1.5GB storage (modelo Whisper)

### Recomendado
- NVIDIA RTX 20/30/40 series (GPU mode)
- 8GB VRAM
- SSD (pra cache do Whisper)
- 16GB RAM total

### Não suportado
- Linux (Win32 hooks específicas)
- macOS (Win32 hooks específicas)
- Raspberry Pi (precisa x86-64)

## Roadmap público

1. ✅ MVP: gravação + transcrição + injeção
2. ✅ GPU acceleration (CUDA)
3. ✅ Config TOML
4. ✅ Autostart via registry
5. ⏳ Auto-updater (GitHub releases)
6. ⏳ Histórico de transcrições
7. ⏳ Contexto por app ativo (diferentes prompts)
8. ⏳ Suporte a múltiplos idiomas com auto-detect
9. ⏳ HTTP API local (webhooks)
10. ⏳ Atalho pra editar última transcrição

## Documentação para IA agents

- **README.md**: Visão geral, instalação, uso
- **ARCHITECTURE.md**: Detalhes técnicos, design decisions, threading
- **CLAUDE.md**: Regras do projeto (privacidade, stack, convenções)
- **config.py**: Schema TOML + valores padrão
- **Code comments**: Docstrings em todas funções principais

## Benchmarks

### Whisper large-v3-turbo

**Hardware: RTX 4060 Laptop 8GB**

| Duração | Latência | Qualidade pt-BR |
|---|---|---|
| 5s | 0.4s | Excelente |
| 15s | 1.2s | Excelente |
| 30s | 2.5s | Excelente |

**Hardware: CPU Ryzen 5 (sem GPU)**

| Duração | Latência | Qualidade pt-BR |
|---|---|---|
| 5s | 8s | Excelente |
| 15s | 25s | Excelente |
| 30s | 45s | Excelente |

## Contribuições bem-vindas

- Bug reports (abrir issue com logs)
- Feature requests (que sejam in-scope: voice input)
- PRs pra fixes (sem mudar stack/deps)
- Testes (especialmente com outros GPUs)
- Documentação

## Não aceitamos

- PRs que mudem pra Node.js, Go, Rust, etc. (scope: Python)
- Cloud integration (scope: local-only)
- Telemetria (scope: zero tracking)
- Dependências pesadas (scope: leve)

## Contato

- **Issues**: GitHub issues
- **Feedback**: Discussions no GitHub
- **Security**: Não há dados sensíveis, mas siga best practices

---

**Última atualização**: 2026-04-12
