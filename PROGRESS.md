# PROGRESS — flow-st8

Rastreamento de trabalho em andamento. O `CLAUDE.md` aponta para cá.

## Como usar este arquivo

- Marque `[x]` **só quando a tarefa estiver entregue e verificada**, nunca quando estiver "quase".
- Ao fechar uma fase, adicione uma linha no **Log de entregas** no fim do arquivo.
- Se uma decisão da seção **Decisões travadas** for revista, edite lá e registre o porquê — não deixe a decisão antiga viva em outro lugar.
- Tarefas descobertas no meio do caminho entram na fase correspondente; não crie fase nova sem necessidade.

**Estado atual: Fase 0 entregue, faltando o teste de regressão no Windows.** A Fase 5 foi parcialmente adiantada (pipeline de empacotamento pronto, mas sem app funcional para empacotar).

---

## Objetivo

Rodar o flow-st8 no macOS **sem parar de evoluir o Windows**, mantendo um único projeto: núcleo compartilhado + camada de sistema escrita uma vez por plataforma.

---

## Decisões travadas

Não relitigar sem motivo novo.

| # | Decisão | Motivo |
|---|---|---|
| 1 | **Um único codebase**, não dois apps separados | Windows segue ativo; duplicar o núcleo faria toda correção de VAD/anti-alucinação/modelo ser feita duas vezes |
| 2 | App mac **nativo em Swift está descartado** | Só compensaria se o Windows fosse congelado |
| 3 | A abstração fica no **protocolo**, não dentro dos módulos de shell | Win32 e Quartz compartilham ~0%; `platform/macos/hotkey.py` é escrito do zero |
| 4 | **Não mexer no motor STT do Windows** | `openai-whisper` + CUDA funciona e tem usuários; trocar é risco de regressão sem ganho visível |
| 5 | macOS = **arm64 apenas** | Universal binary com PyTorch/MLX é dor; MLX só roda em Apple Silicon |
| 6 | **Sem gastar**: certificado autoassinado, sem notarização | Notarização exige conta paga (US$ 99/ano). A troca depois é só o `SIGN_IDENTITY` |
| 7 | UI de config **dentro do app**, não num instalador separado | Permissão de Acessibilidade fica amarrada ao bundle ID de quem pede; instalador separado a concederia para o bundle errado |
| 8 | No mac, overlay = **NSPanel no NSApp do pystray**; Tk fica só no Windows | Tk e AppKit disputam a main thread no macOS |
| 9 | **Modelo não vai dentro do DMG** | 1,5 GB; download na primeira execução já está no fluxo |
| 10 | A pasta é **`backends/`**, não `platform/` | `platform` é módulo da stdlib; um pacote com esse nome na raiz sombrearia o `platform.system()` que pystray, sounddevice e o PyInstaller usam |

---

## Fase 0 — Abstração de plataforma (Windows intacto)

Mover código, sem mudar lógica. Critério de saída: **regressão zero no Windows**, verificada rodando o app antes e depois.

- [x] Criar `core/` e mover: `config.py`, `recorder.py`, `vad.py`, `transcriber.py`, `app.py` (via `git mv`, histórico preservado)
- [x] Criar `backends/base.py` com os protocolos: `HotkeyBackend`, `Injector`, `Overlay`, `Tray`, `Autostart`
- [x] Criar `backends/windows/` e mover sem alterar lógica: `hotkey.py`, `injector.py`, `overlay.py`, `tray.py`, `autostart.py`
- [x] Criar `backends/__init__.py` com factory por `sys.platform` + stubs inertes fora do Windows
- [x] Criar `core/paths.py`: `%APPDATA%/flow-st8` (Windows) vs `~/Library/Application Support/flow-st8` (macOS)
- [x] Criar `core/resources.py` — os assets quebrariam ao mover `tray.py`/`overlay.py` um nível abaixo da raiz
- [x] Substituir `winsound` por beeps gerados com `sounddevice` (já é dependência)
- [x] Vocabulário de teclas normalizado em `core/keys.py` (`win`/`super`/`cmd`/`meta` → `OS_MOD`), com defaults por plataforma
- [x] Garantir que `config.toml` já existente no `%APPDATA%` continua carregando e **vence** os defaults novos
- [x] `ci.yml`: import-check em `ubuntu-latest`, sem instalar dependências
- [x] Atualizar o bloco `## Arquitetura` do `CLAUDE.md` para a estrutura nova de pastas
- [ ] **Testar no Windows: hold, toggle, remap pelo tray, troca de modelo, autostart** ← única coisa que falta; não dá para fazer no Mac

### Verificado até aqui (no macOS)

- `python -m compileall .` limpo na árvore inteira
- `import core.*` e `import backends` funcionam no macOS — antes quebrava no `import winsound`
- Simulando `sys.platform = "win32"`: `DEFAULT_HOLD == "ctrl+win"`, `DEFAULT_TOGGLE == "ctrl+win+o"`, `APP_DIR == %APPDATA%/flow-st8` — idênticos aos valores antigos
- Stub de autostart é inerte (`sync()` não levanta), então o boot não quebra fora do Windows

**Não verificado:** nada foi executado no Windows. O app não rodou nem no Mac (falta o backend).

## Fase 1 — Spike de main thread (timebox: 1 dia)

Responde se a Fase 4 é viável como planejada. Não escrever produto aqui.

- [ ] Protótipo mínimo: `pystray` no backend Darwin + um `NSPanel` via pyobjc no mesmo `NSApplication`
- [ ] Confirmar que o NSPanel não rouba foco (`canBecomeKey = False`) — se roubar, o Cmd+V vai para a janela errada
- [ ] Confirmar update do ícone da barra a partir de outra thread
- [ ] Registrar o resultado aqui e ajustar a Fase 4

**Plano B se falhar:** primeira versão do mac sem overlay (só ícone na barra + beeps).

## Fase 2 — macOS headless

Sem interface: aperta o atalho, grava, transcreve, cola.

- [ ] `platform/macos/hotkey.py` — `CGEventTap` + `CFRunLoop` (análogo do `WH_KEYBOARD_LL` + `GetMessage`)
- [ ] Suporte a combo só-de-modificador (hold) via flags-changed
- [ ] Suporte ao toggle (hold + tecla extra) e à supressão da tecla
- [ ] `platform/macos/injector.py` — `pyperclip` + Cmd+V via `CGEventPost`, com restauração do clipboard
- [ ] `platform/macos/sound.py` — beeps
- [ ] `core/permissions.py` — `AXIsProcessTrustedWithOptions` (acessibilidade) + microfone
- [ ] Fluxo de primeira execução pedindo as duas permissões, com instrução clara (não falhar em silêncio)
- [ ] Adicionar `pyobjc-framework-Quartz` e `pyobjc-framework-Cocoa` às dependências (só macOS)

## Fase 3 — Backend de transcrição plugável

Sem isso o mac leva 20-45s por frase e parece travado.

- [ ] Protocolo `TranscriptionBackend` em `core/`
- [ ] Implementação `openai-whisper` (Windows/CUDA) — comportamento idêntico ao de hoje
- [ ] Implementação `mlx-whisper` (Apple Silicon, GPU via Metal)
- [ ] Detecção de device: `cuda` → `mlx` → `cpu`, rebaixando o modelo default quando o hardware não aguenta
- [ ] Preservar no caminho mac: anti-alucinação, detect restrito pt/en, trim de silêncio, `initial_prompt`
- [ ] Download do modelo na primeira execução (não no empacotamento)

## Fase 4 — Interface do macOS

- [ ] `platform/macos/tray.py` — ícone na barra (validar lacunas do backend Darwin do pystray: `notify`, `title`, update fora da main thread)
- [ ] Notificações via `osascript -e 'display notification'` se o pystray não cobrir
- [ ] `platform/macos/overlay.py` — NSPanel click-through, `NSStatusWindowLevel`, sem roubar foco
- [ ] Janela de preferências no app: **atalhos + modelo** (o que foi pedido para o "instalador")
- [ ] Reaproveitar a mesma janela no Windows, aposentando parte do menu do tray

## Fase 5 — Empacotamento e distribuição

- [x] `packaging/macos/flow-st8-mac.spec` — bundle `.app`, `LSUIElement`, `NSMicrophoneUsageDescription`, bundle ID fixo, `target_arch=arm64`, UPX desligado
- [x] `packaging/macos/entitlements.plist` — só para o caminho notarizado; App Sandbox proibido
- [x] `packaging/macos/release.sh` — icns, build, assinatura inside-out, DMG (`create-dmg` com fallback `hdiutil`), notarização opcional via `NOTARY_PROFILE`
- [x] Seção de macOS no `README.md` — build, `xattr` de quarentena, caminho notarizado
- [ ] **Rodar o build de verdade** e corrigir o que aparecer (nunca foi executado — falta `pyinstaller` e deps na máquina)
- [ ] Conferir tamanho final do DMG; avaliar excluir `torch` do bundle depois da Fase 3
- [ ] `build.yml`: adicionar job `macos-14` à matriz
- [ ] Decidir se o certificado autoassinado entra no CI ou se o DMG é gerado só localmente

## Fase 6 — Autostart e acabamento

- [ ] `platform/macos/autostart.py` — LaunchAgent em `~/Library/LaunchAgents/com.luckmattos.flow-st8.plist` com `RunAtLoad`
- [ ] Renomear "Start with Windows" → "Iniciar com o sistema"
- [ ] Revisar strings do tray e do README para os dois SOs
- [ ] Atualizar o Roadmap do `README.md`

---

## Riscos abertos

| Risco | Impacto | Mitigação |
|---|---|---|
| pystray Darwin não expor o `NSApp` de forma utilizável | Fase 4 muda de forma | Spike da Fase 1; plano B sem overlay |
| Permissão de Acessibilidade negada ou esquecida | App fica mudo, sem erro visível | Checagem no boot + aviso explícito no onboarding |
| Bundle gigante por causa do PyTorch | DMG de vários GB | Excluir `torch` do bundle mac depois da Fase 3 |
| Gatekeeper sem notarização | Alerta de "possível malware" ao instalar | `xattr` documentado; conta paga quando alguém reclamar |
| Refatoração da Fase 0 quebrar o Windows | Regressão para usuários reais | Teste manual completo antes de fechar a fase |

---

## Log de entregas

| Data | Entrega |
|---|---|
| 2026-08-01 | Pipeline de empacotamento macOS: spec, entitlements, `release.sh`, seção do README (Fase 5 parcial). Não executado ainda. |
| 2026-08-01 | Fase 0: split `core/` + `backends/`, protocolos, `paths.py`, `keys.py`, `resources.py`, beeps via sounddevice, CI com import-check. Pendente: rodar no Windows. |
