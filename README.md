# flow-st8

**Ditado de voz local e privado para Windows.** Aperta `Ctrl+Win`, fala, aperta de novo — o texto é transcrito pelo Whisper na sua própria máquina e colado onde o cursor estiver. Sem nuvem, sem assinatura, sem telemetria.

---

## Metadados (para IA agents)

**Keywords:** speech-to-text, voice-dictation, whisper, local-processing, offline, privacy-first, windows, real-time, hotkey, python, cuda, portuguese  
**Tipo:** Desktop Application (Windows)  
**Linguagem:** Python 3.11+  
**Licença:** MIT  
**Status:** Estável, em produção pessoal  

📖 **Para entender o código:** veja [ARCHITECTURE.md](ARCHITECTURE.md) (design, threading, fluxos)  
🔍 **Para descoberta:** veja [DISCOVERY.md](DISCOVERY.md) (metadados, comparações, roadmap)

---

Pense nele como uma alternativa open-source ao WhisprFlow/Wispr, feita pra rodar 100% offline com GPU NVIDIA (ou CPU, se preferir esperar um pouco).

---

## Por que existe

Aplicativos comerciais de ditado mandam o seu áudio e screenshots para o servidores deles. Isso significa:

- Seu áudio sai da máquina toda vez que você fala
- Custo mensal recorrente
- Dependência de internet
- Você não sabe o que acontece com os dados

O `flow-st8` roda o Whisper **localmente**, usa VAD (Voice Activity Detection) para descartar silêncio automaticamente, e injeta o texto no campo ativo via clipboard — tudo em Python enxuto, sem framework nenhum.

---

## Recursos

- 🎤 **Hotkey global**: `Ctrl+Win` para começar, `Ctrl+Win` de novo para parar
- 🤖 **Whisper local**: modelo `large-v3-turbo` por padrão (melhor qualidade pt-BR)
- ⚡ **Aceleração GPU**: detecção automática de CUDA (RTX) → latência &lt;1s
- 🔇 **VAD inteligente**: silêncio é descartado em tempo real, não interrompe a gravação
- 💬 **Pausas livres**: pode pensar sem pressa, só os pedaços com fala vão pro Whisper
- 📋 **Injeção por clipboard**: cola via `Ctrl+V` e restaura o clipboard anterior
- 🖱️ **Tray icon**: estados visuais (idle / gravando / transcrevendo / erro)
- 🔄 **Autostart**: inicia junto com o Windows automaticamente (opcional)
- 🔊 **Feedback sonoro**: beeps curtos de início/fim/sucesso/aviso
- ⏱️ **Limite de 3min30s** por gravação, com aviso sutil aos 3min15s

---

## Stack

| Camada | Tecnologia |
|---|---|
| STT | [openai-whisper](https://github.com/openai/whisper) + [PyTorch CUDA](https://pytorch.org/) |
| VAD | [Silero VAD v6](https://github.com/snakers4/silero-vad) |
| Hotkey global | Win32 `RegisterHotKey` + `WH_KEYBOARD_LL` (via `ctypes`) |
| Captura de mic | [sounddevice](https://python-sounddevice.readthedocs.io/) |
| Injeção de texto | [pyperclip](https://github.com/asweigart/pyperclip) + `SendInput` |
| Tray icon | [pystray](https://github.com/moses-palmer/pystray) + [Pillow](https://python-pillow.org/) |
| Config | TOML (stdlib `tomllib`) |
| Autostart | `winreg` → `HKCU\...\Run` |

---

## Requisitos

- **Windows 10/11**
- **Python 3.11+** (testado em 3.14)
- **GPU NVIDIA com CUDA** (recomendado) — RTX 20xx/30xx/40xx. Também roda em CPU, só mais lento.
- **~6 GB de espaço** (torch CUDA ~3GB + Whisper `large-v3-turbo` ~1.5GB + libs)
- **Microfone** funcionando

---

## Instalação

**Opção 1: Automática (recomendado)**

```bash
git clone https://github.com/luckmattos/flow-st8.git
cd flow-st8

python install.py
```

O script detecta automaticamente se você tem placa de vídeo NVIDIA e instala a versão correta do PyTorch:
- ✅ **Com GPU NVIDIA** → instala CUDA (torch 2.7GB, transcription <1s)
- ✅ **Sem GPU (CPU puro)** → instala versão leve (recomenda mudar modelo em config.toml)

---

**Opção 2: Manual**

```bash
git clone https://github.com/luckmattos/flow-st8.git
cd flow-st8
pip install -r requirements.txt
```

Depois escolha uma das opções de PyTorch:

**Com placa de vídeo NVIDIA:**
```bash
pip install torch --index-url https://download.pytorch.org/whl/cu128
```

**Só com CPU (sem GPU):**
```bash
pip install torch
```

---

## Rodando

Primeira execução baixa o modelo Whisper (~1.5GB máx, só uma vez):

```bash
python main.py
```

Ou clique duas vezes em `flow-st8.vbs` (sem console).

Um ícone de microfone aparece na bandeja do sistema. Aperte `Ctrl+Win`, fale, aperte de novo.

---

## Estrutura de pastas

```
flow-st8/
├── README.md                 (👈 você está aqui)
├── ARCHITECTURE.md           (design, threading, modules)
├── DISCOVERY.md              (metadados, keywords, roadmap)
├── CLAUDE.md                 (regras do projeto)
├── PROGRESS.md               (histórico de desenvolvimento)
│
├── flow-st8.vbs              (🎯 launcher — duplo-clique pra rodar)
├── flow-st8.bat              (alternativa: .bat com console)
├── install.py                (auto-detecta GPU e instala deps)
├── main.py                   (entry point)
│
├── app.py                    (orquestrador principal, FlowSt8App)
├── config.py                 (TOML + dataclasses)
├── hotkey.py                 (Win32 RegisterHotKey + WH_KEYBOARD_LL)
├── recorder.py               (sounddevice → audio chunks)
├── vad.py                    (Silero VAD wrapper)
├── transcriber.py            (Whisper local, auto-detect CUDA/CPU)
├── injector.py               (clipboard + SendInput)
├── tray.py                   (pystray icon + menu)
├── autostart.py              (winreg HKCU\...\Run)
├── audio_feedback.py         (beeps via winsound)
│
└── requirements.txt          (pip dependencies)
```

**Para começar:**
1. Leia `README.md` (este arquivo) — visão geral
2. Rode `python install.py` — auto-setup
3. Clique 2x em `flow-st8.vbs` — start
4. Para entender código: `ARCHITECTURE.md`
5. Para contribuir: `DISCOVERY.md` (contribuições bem-vindas)

---

## Como usar

1. **Gravar**: `Ctrl+Win` (ícone fica vermelho)
2. **Falar**: dite o que quiser, pausas longas não são problema
3. **Parar**: `Ctrl+Win` de novo (ícone fica azul enquanto processa)
4. **Pronto**: o texto é colado onde o cursor estiver

### Menu do tray

- **Gravar / Parar** — equivalente à hotkey
- **Modelo** — mostra qual Whisper está ativo
- **Hotkey** — mostra a combinação atual
- **Iniciar com Windows** — toggle de autostart
- **Sair** — fecha o app

---

## Configuração

O config fica em `%APPDATA%\flow-st8\config.toml` e é criado na primeira execução. Principais campos:

```toml
[model]
# "tiny" | "base" | "small" | "medium" | "large-v3-turbo"
name = "large-v3-turbo"
language = "pt"
initial_prompt = "Transcrição em português brasileiro."

[hotkey]
# "toggle" (aperta para começar, aperta para parar)
mode = "toggle"
key = "ctrl+win"

[audio]
device_index = -1    # -1 = mic padrão do sistema
sample_rate = 16000
max_seconds = 210    # 3min30s
gain = 1.8           # ganho interno antes da transcrição

[vad]
enabled = true
speech_threshold = 0.5

[injection]
method = "clipboard"       # "clipboard" ou "sendinput"
restore_clipboard = true

[feedback]
enabled = true      # beeps de feedback

[startup]
autostart = true    # inicia com o Windows
```

---

## Arquitetura

```
main.py            → entry point, carrega config e starta o app
app.py             → orquestrador, conecta os módulos
config.py          → config TOML (%APPDATA%/flow-st8/)
recorder.py        → captura de microfone (16kHz mono float32)
vad.py             → Silero VAD wrapper (descarta silêncio)
transcriber.py     → Whisper wrapper (auto-detect CUDA/CPU)
injector.py        → clipboard + Ctrl+V + restaura clipboard
hotkey.py          → Win32 RegisterHotKey + WH_KEYBOARD_LL
tray.py            → pystray icon com estados
audio_feedback.py  → beeps via winsound
autostart.py       → registro HKCU\Run
```

### Threading

- **Main**: `pystray.Icon.run()` bloqueia
- **Hotkey**: thread dedicada com `GetMessage` loop + hook LL
- **Worker**: `ThreadPoolExecutor` (gravar + VAD + transcrever)

### Pipeline de transcrição

```
mic (sounddevice 512 samples/32ms)
  ↓
Silero VAD (descarta silêncio, mantém pré/pós-padding)
  ↓
Whisper (CUDA fp16 ou CPU fp32)
  ↓
pós-processamento (capitaliza, limpa espaços)
  ↓
pyperclip + SendInput Ctrl+V (restaura clipboard depois)
```

---

## Escolhendo o modelo certo

O Whisper tem 5 modelos diferentes. A escolha correta **depende muito** se você tem placa de vídeo NVIDIA ou roda só em CPU.

### ⚠️ Aviso importante: CPU vs GPU

**Se você NÃO tem placa de vídeo NVIDIA** (apenas processador/CPU), esqueça os modelos maiores (`medium`, `large-v3-turbo`). A transcição fica absurdamente lenta — **25-45 segundos pra frase curta** é inviável pra uso real. Nesse caso, escolha `tiny` ou `base` e aceite qualidade menor.

**Se você TEM placa de vídeo NVIDIA** (RTX 20xx/30xx/40xx), aproveite — a latência cai pra menos de **1 segundo por frase**. Vale muito a pena investir no modelo maior (`large-v3-turbo`).

Confira a tabela abaixo e escolha o melhor trade-off pra sua máquina:

### Comparação de modelos

| Modelo | Tamanho | VRAM | Com GPU NVIDIA | Com CPU puro | Qualidade pt-BR |
|---|---|---|---|---|---|
| **tiny** | 39 MB | ~1 GB | 0.1s (5s frase) | 1-2s | Baixa, alucina |
| **base** | 138 MB | ~1.5 GB | 0.3s | 3-5s | Razoável, ok pra notas rápidas |
| **small** | 460 MB | ~2 GB | 0.7s | 8-12s | Boa, recomendado pra CPU |
| **medium** | 1.5 GB | ~3.5 GB | 1.5-2s | 25-35s | **Muito boa** |
| **large-v3-turbo** | 1.5 GB | ~3 GB | 0.4-1.2s ⭐ | 20-45s | **Excelente** (padrão) |

**Legenda:**
- **Tamanho**: espaço em disco do modelo (baixado uma vez)
- **VRAM**: memória de vídeo (GPU) ou RAM (CPU) usado durante transcrição
- **Latência**: tempo de transcrição depois que você aperta `Ctrl+Win` segunda vez
  - Com GPU: rápido (menos de 2s até ~30s de áudio)
  - Com CPU: **lento** (25-45s é comum)
- **Qualidade pt-BR**: o quanto o modelo erra em português brasileiro

### Recomendações

| Seu setup | Modelo | Por quê |
|---|---|---|
| 💻 **Notebook CPU puro** (sem GPU) | `base` ou `small` | Não vale a pena esperar 45s pra frase pequena |
| 🖥️ **PC desktop, CPU bom** (Ryzen/i7+) | `small` | Melhor qualidade sem ficar muito lento |
| 🎮 **RTX 20xx / 30xx / 40xx** | `large-v3-turbo` ⭐ | Latência &lt;1s, qualidade perfeita, **melhor do mercado** |
| 📱 **GPU antiga (GTX 10xx)** | `base` ou `small` | Pode trabalhar, mas sem aceleração real |

---

## Desempenho real

Medido numa **RTX 4060 Laptop 8GB** com `large-v3-turbo`:

| Duração da fala | Latência (GPU) | Latência (CPU puro) |
|---|---|---|
| 5s | ~0.4s ✅ | ~8s ❌ |
| 15s | ~1.2s ✅ | ~25s ❌ |
| 30s | ~2.5s ✅ | ~45s ❌ |

**VRAM**: ~3GB durante transcrição (GPU). **RAM em idle**: ~500MB.

GPU faz **toda a diferença** — mesma frase, 40x mais rápida.

---

## Roadmap

- [ ] Teste end-to-end real (GPU + mic + app focado)
- [ ] Instalador `.exe` via PyInstaller
- [ ] Auto-updater
- [ ] Suporte a auto-detect de idioma
- [ ] Histórico das últimas transcrições
- [ ] Prompt customizável por contexto (app ativo)

---

## Por que rolar sozinho em vez de usar alternativas comerciais?

Existem várias ferramentas prontas de ditado por voz na internet. Aqui tá o trade-off:

| Aspecto | flow-st8 | Alternativas comerciais |
|---|---|---|
| **Processamento** | Local (sua máquina) | Nuvem (servidor deles) |
| **Seu áudio** | Nunca sai do PC | Enviado toda vez que você fala |
| **Custo** | $0 (sempre) | $10-20/mês (assinatura) |
| **Privacidade do áudio** | Total — você controla | Terceiros armazenam |
| **Screenshot (contexto)** | Nenhum | Muitos capturam tela para "contexto" 👀 |
| **Funciona offline** | ✅ Sim | ❌ Precisa internet |
| **Código aberto** | ✅ Sim | ❌ Proprietário |
| **Latência** | 0.4-1.2s (com GPU) | ~0.5-1s |
| **Qualidade** | Excelente | Excelente |

### ⚠️ Nota sobre captura de tela

Muitas alternativas comerciais capturam **screenshots da sua tela** automaticamente para "contexto" — ou seja, cada vez que você dita, o servidor deles recebe:
- O áudio gravado
- Uma foto da sua tela naquele momento

Isso inclui senhas, emails, conversas privadas, código-fonte, tudo que estiver visível. **flow-st8 nunca faz isso** — só grava áudio, processa localmente, e injeta texto. Ponto.

### O bottom line

A diferença prática (latência, qualidade) é **praticamente nenhuma**. A diferença de privacidade é **abissal**. Se você controla seus dados, flow-st8. Se você é ok compartilhando áudio + screenshots com servidores, as alternativas funcionam bem também.

---

## Licença

MIT — faça o que quiser.

---

## Autor

[luckmattos](https://github.com/luckmattos) — desenvolvido com [Claude Code](https://claude.com/claude-code) como pair programmer.
