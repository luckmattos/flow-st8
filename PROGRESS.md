# Progresso - flow-st8

## Fase 1: Fundacao
- [x] config.py + config.toml padrao (criado em %APPDATA%/flow-st8/)
- [x] audio_feedback.py (winsound beeps: start/stop/done/error)
- [x] requirements.txt
- [x] main.py entry point com UTF-8 stdio

## Fase 2: Audio Pipeline
- [x] recorder.py - captura mic com sounddevice (16kHz mono float32, 512 samples/chunk)
- [x] vad.py - Silero VAD v6 wrapper (requer 512 samples exatos)
- [x] Teste: VAD funcional com audio dummy

## Fase 3: Transcricao
- [x] transcriber.py - Whisper wrapper com lazy loading
- [x] Filtro RMS para evitar alucinacoes em silencio (threshold 0.005)
- [x] Teste: modelo `base` carrega e filtra silencio corretamente

## Fase 4: Integracao Windows
- [x] hotkey.py - Win32 RegisterHotKey via ctypes + parser de hotkey string
- [x] injector.py - clipboard + SendInput Ctrl+V + restaurar clipboard

## Fase 5: Orquestracao
- [x] app.py - FlowSt8App orquestrador com ThreadPoolExecutor
- [x] tray.py - pystray com icones dinamicos (idle/recording/processing/error)
- [x] Todos os modulos importam sem erro

## Fase 6: Polish
- [ ] Teste end-to-end real com microfone (requer usuario rodar `python main.py`)
- [ ] Validar em: Notepad, VS Code, Chrome, terminal
- [ ] Verificar RAM idle < 300MB
- [ ] Ajustar thresholds se necessario (silence_threshold_ms, speech_threshold)

## Descobertas tecnicas
- Silero VAD v6 requer **exatamente 512 samples** a 16kHz (nao 30ms/480 samples)
- Whisper alucina em silencio mesmo com `no_speech_threshold=0.6` - solucao: checar RMS < 0.005 antes
- Console Windows cp1252 quebra em Unicode - resolvido com `sys.stdout.reconfigure(encoding='utf-8')`
- `pyperclip` ja vem com pywin32 via ctypes - sem dep extra
- **BUG CRITICO SendInput**: struct INPUT precisa ter 40 bytes em Win64, mas union so com
  KEYBDINPUT da 32 bytes. SendInput rejeita silenciosamente (retorna 0). Solucao: incluir
  MOUSEINPUT + HARDWAREINPUT na union para union ter 32 bytes e INPUT total = 40.
- `dwExtraInfo` deve ser `ULONG_PTR` (c_size_t), nao `POINTER(c_ulong)`

## Bloqueios
(nenhum)

## Notas de sessao
- 2026-04-12 (sessao 1): Plano criado. Todos os 10 modulos implementados e validados
  quanto a imports, API e comportamento com dummies. Pronto para teste end-to-end real.
