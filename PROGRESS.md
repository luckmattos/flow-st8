# PROGRESS — flow-st8

Rastreamento de trabalho em andamento. O `CLAUDE.md` aponta para cá.

## Como usar este arquivo

- Marque `[x]` **só quando a tarefa estiver entregue e verificada**, nunca quando estiver "quase".
- Ao fechar uma fase, adicione uma linha no **Log de entregas** no fim do arquivo.
- Se uma decisão da seção **Decisões travadas** for revista, edite lá e registre o porquê — não deixe a decisão antiga viva em outro lugar.
- Tarefas descobertas no meio do caminho entram na fase correspondente; não crie fase nova sem necessidade.

**Estado atual: Fases 0 a 6 entregues. O flow-st8 roda no macOS, empacotado como `.app` dentro de um `.dmg`.**

Único item aberto: **rodar a regressão da Fase 0 no Windows** — só o Lucas pode,
e nada do port foi validado lá. Todo o resto está verificado no macOS.

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
| 3 | A abstração fica no **protocolo**, não dentro dos módulos de shell | Win32 e Quartz compartilham ~0%; `backends/macos/hotkey.py` é escrito do zero. **Exceção descoberta na Fase 4:** o tray é compartilhado, porque o pystray já abstrai os dois SOs |
| 4 | **Não mexer no motor STT do Windows** | `openai-whisper` + CUDA funciona e tem usuários; trocar é risco de regressão sem ganho visível |
| 5 | macOS = **arm64 apenas** | Universal binary com PyTorch/MLX é dor; MLX só roda em Apple Silicon |
| 6 | **Sem gastar**: certificado autoassinado, sem notarização | Notarização exige conta paga (US$ 99/ano). A troca depois é só o `SIGN_IDENTITY` |
| 7 | UI de config **dentro do app**, não num instalador separado | Permissão de Acessibilidade fica amarrada ao bundle ID de quem pede; instalador separado a concederia para o bundle errado |
| 8 | No mac, overlay = **NSPanel no NSApp do pystray**; Tk fica só no Windows | Tk e AppKit disputam a main thread no macOS |
| 9 | **Modelo não vai dentro do DMG** | 1,5 GB; download na primeira execução já está no fluxo |
| 10 | A pasta é **`backends/`**, não `platform/` | `platform` é módulo da stdlib; um pacote com esse nome na raiz sombrearia o `platform.system()` que pystray, sounddevice e o PyInstaller usam |
| 11 | Injeção no mac é **`CGEventKeyboardSetUnicodeString`**, não clipboard + Cmd+V | Cmd+V herda os modificadores fisicamente pressionados (o próprio atalho do app), reentra no nosso event tap corrompendo a máquina de estados, assume que o app de destino tem paste em Cmd+V, e sequestra o clipboard. O evento unicode não tem nenhum desses. Clipboard fica como *fallback* selecionável em `injection.method` |
| 12 | Gatilho padrão no mac é **`ctrl+option`** (canônico `ctrl+alt`), **sem suprimir teclas** durante a gravação | Push-to-talk segura o acorde por 5-10s falando; com `ctrl+cmd` qualquer tecla encostada vira atalho de sistema — `Ctrl+Cmd+Q` **bloqueia a tela**. `Ctrl+Option+letra` não tem atalho destrutivo de sistema, então dispensa supressão. Bônus: já cabe no vocabulário de `core/keys.py` sem alteração |

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

**Não verificado:** nada foi executado no Windows.

## Fase 1 — Spike de main thread (timebox: 1 dia)

Responde se a Fase 4 é viável como planejada. Não escrever produto aqui.

- [x] Protótipo mínimo: `pystray` no backend Darwin + um `NSPanel` via pyobjc no mesmo `NSApplication`
- [x] Confirmar que o NSPanel não rouba foco (`canBecomeKey = False`) — se roubar, o Cmd+V vai para a janela errada
- [x] Confirmar update do ícone da barra a partir de outra thread
- [x] Registrar o resultado aqui e ajustar a Fase 4

### Resultado: passou em tudo. Plano B descartado.

Executado em 2026-08-01 no macOS (Darwin 25.3, Apple Silicon), pystray 0.19.5,
pyobjc 12.2.1.

| Pergunta | Resultado |
|---|---|
| pystray Darwin roda um `NSApplication` de verdade? | Sim — `NSApplication.sharedApplication()` + `.run()`. `NSApp()` é o mesmo objeto |
| NSPanel criado nesse loop aparece? | Sim, `isVisible() == True` |
| Rouba foco? | **Não.** `canBecomeKeyWindow() == False`, `keyWindow() is None`, app frontmost inalterado |
| Update do ícone fora da main thread? | Funciona |
| Política *accessory* (LSUIElement em runtime)? | Funciona (`activationPolicy() == 1`) |

Detalhes que a Fase 4 herda:

- Chamadas AppKit vão para a main thread com `PyObjCTools.AppHelper.callAfter`.
- Painel: `NSPanel` com `NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel`,
  `setLevel_(NSStatusWindowLevel)`, `setIgnoresMouseEvents_(True)`,
  `setHidesOnDeactivate_(False)` e collection behavior
  `CanJoinAllSpaces | Transient | FullScreenAuxiliary`.
- `pystray.Icon` aceita a opção `nsapplication`, então dá para injetar um
  `NSApplication` próprio se algum dia for preciso.
- **`icon.notify()` já funciona no Darwin** — o pystray chama
  `osascript -e 'display notification'` internamente. O item de fallback que
  estava na Fase 4 era desnecessário e foi removido.
- **`HAS_MENU_RADIO = False` no backend Darwin**: os itens de modelo em
  `tray.py` usam `radio=True` e não vão renderizar como radio no macOS.
  Precisa de outra affordance — virou item da Fase 4.
- `set_title()` vira `setToolTip_` no botão da barra: é tooltip, não texto
  visível. Comportamento aceitável, nenhuma mudança necessária.

Ambiente do spike: `.venv/` na raiz (ignorado pelo git) com pystray, pillow e
pyobjc. Script em scratchpad — descartável, o resultado é o que importa.

## Fase 2 — macOS headless

Sem interface: aperta o atalho, grava, transcreve, cola.

- [x] `backends/macos/hotkey.py` — `CGEventTap` + `CFRunLoop` (análogo do `WH_KEYBOARD_LL` + `GetMessage`)
- [x] Hold via `kCGEventFlagsChanged`: `ctrl+option` (ver decisão 12). **Não suprimir** nenhuma tecla — o tap só observa
- [x] Toggle (`ctrl+option+o`) confirmado como hands-free. Varredura do `com.apple.symbolichotkeys` em 2026-08-01: dos 43 atalhos de sistema ativos, nenhum usa `ctrl+option` nem a tecla O. Não cobre bindings internos de apps — esses só valem com o app em foco e são remapeáveis pelo usuário
- [x] Ignorar eventos que nós mesmos postamos: ler `kCGEventSourceUserData` e pular os marcados
- [x] Re-armar o tap quando o sistema o desabilita (`kCGEventTapDisabledByTimeout`) — senão fica surdo pelo resto da sessão
- [x] `backends/macos/injector.py` — `CGEventKeyboardSetUnicodeString` (decisão 11), event source privado, `CGEventSetFlags(ev, 0)`, texto em blocos de 20 chars
- [x] Manter clipboard + Cmd+V como fallback em `injection.method` para apps que leem keycode cru (terminal em raw mode, desktop remoto)
- [x] `core/permissions.py` — acessibilidade (`AXIsProcessTrustedWithOptions`) e Secure Event Input
- [x] Adicionar `pyobjc-framework-Quartz`, `-Cocoa` e `-ApplicationServices` às dependências (marcadas `sys_platform == "darwin"`)
- [x] Permissão de microfone em `core/permissions.py` (`AVCaptureDevice`). Retorna `None` quando indeterminado, não `False`: o prompt também aparece quando o `sounddevice` abre o stream, e uma checagem inconclusiva não pode travar o boot
- [x] Detectar VoiceOver ligado e avisar — ele usa Ctrl+Option como tecla modificadora e consumiria tudo
- [x] Exibição do combo no mac via `core.keys.display()` (`⌃⌥O`) sem mudar o que é gravado no TOML (`ctrl+alt`)
- [x] `app.on_tray_ready()` reporta permissão faltando no tray, no overlay e no log em vez de falhar em silêncio

Beeps já saíram daqui: `core/audio_feedback.py` virou multiplataforma na Fase 0.

### Verificado (2026-08-01, macOS, 13/13)

Teste automatizado postando eventos sintéticos e observando o tap:

| Verificação | Resultado |
|---|---|
| Tap instala com Acessibilidade concedida | passa |
| `ctrl` sozinho não dispara | passa |
| `ctrl+option` dispara `hold_down` | passa |
| Repetição não redispara | passa |
| Soltar option dispara `hold_up` | passa |
| `ctrl+option+o` dispara `toggle` | passa |
| `o` sozinho é ignorado | passa |
| Evento marcado com `SYNTHETIC_MARK` é ignorado | passa — protege contra auto-disparo |
| Payload unicode preservado, com acento (`"Olá, ação — çãüê"`) | passa |
| Evento do injetor sai marcado e com flags zerados | passa |
| Thread do tap encerra limpa | passa |

**Digitação ponta a ponta: passa nos dois métodos.** Documento novo do TextEdit,
injeção pelo `TextInjector` real, texto lido de volta via AppleScript e
comparado. `"Olá! Este é um teste de injeção do flow-st8 — com acentuação,
çedilha e 123."` chega idêntico tanto por `unicode` quanto por `clipboard`.
Isso verifica **entrega**, não só o envio.

**Não verificado ainda:**

- Teclado físico. Só eventos sintéticos foram testados; passam pelo mesmo caminho do tap, e a checagem é `(flags & required) == required`, tolerante a bits extras que hardware real costuma trazer — mas não é prova.
- `capture_next_combo` (remapear atalho pelo tray).
- Secure Event Input: implementado, nunca exercitado (precisa de campo de senha em foco).

Permissão de Acessibilidade em desenvolvimento fica no **Visual Studio Code** —
o macOS atribui ao processo responsável, e o Python roda como filho dele. No
app empacotado será o próprio `flow-st8.app`.

## Fase 3 — Backend de transcrição plugável

Sem isso o mac leva 20-45s por frase e parece travado.

- [x] Protocolo `SttBackend` em `core/stt/base.py`
- [x] Implementação `openai-whisper` (Windows/CUDA) — parâmetros de decodificação copiados sem alteração
- [x] Implementação `mlx-whisper` (Apple Silicon, GPU via Metal)
- [x] Detecção de device: `cuda` → `mlx` → `cpu`. O modelo pesado em CPU gera **aviso** e `recommended_model()`, nunca troca sozinho a escolha do usuário
- [x] Preservar no caminho mac: anti-alucinação, detect restrito pt/en, trim de silêncio, `initial_prompt` — tudo vive no facade `core/transcriber.py`, compartilhado pelos dois motores
- [x] Download do modelo na primeira execução (cache do Hugging Face, não no empacotamento)

### Medido no macOS (M-series, `large-v3-turbo` via MLX)

| | |
|---|---|
| Carregar modelo (cache quente) | 1,7s |
| Frase de 6,1s | 2,1s |
| Frase de 3,6s | 1,9s |
| Frase curta, idioma forçado | 1,0s |

Referência do CPU no README: 20-45s para o mesmo modelo. É a diferença entre
usável e parecer travado.

**Dois bugs achados e corrigidos durante o teste:**

1. `pad_or_trim` do MLX só aceita `mx.array`. Passar numpy estourava dentro do
   `mx.pad`, e o `except` do facade engolia — resultado: **toda** gravação era
   fixada no primeiro idioma da lista. Só apareceu porque o teste comparava o
   idioma detectado com o esperado.
2. `mlx_whisper.transcribe` busca o modelo num `ModelHolder` em `float16`,
   enquanto o `load()` criava uma instância separada em `float32`. Duas cópias
   residentes (~3GB no turbo) e a detecção rodando num modelo diferente do que
   transcrevia. Passando pelo holder: carga caiu de 42s para 1,7s.

**Não verificado:** qualidade com fala humana real. O teste usa vozes sintéticas
do `say`, que o Whisper transcreve mal por natureza — o texto em português sai
aproximado. Isso mede encanamento e velocidade, não acurácia.

## Fase 4 — Interface do macOS

- [x] Tray unificado em `backends/tray.py` — pystray já abstrai Shell_NotifyIcon e NSStatusItem; uma implementação separada seriam 170 linhas duplicadas. `backends/windows/tray.py` foi removido
- [x] Menu de modelos marca o ativo com `●` quando `HAS_MENU_RADIO` é falso
- [x] `backends/macos/overlay.py` — NSPanel click-through, `NSStatusWindowLevel`, sem roubar foco. Frames renderizados com Pillow num `NSImageView`, reaproveitando o pipeline de arte do tray
- [ ] Janela de preferências dedicada: **adiada de propósito**. O menu do tray já expõe atalhos e modelo, que era a funcionalidade pedida; uma janela própria é polimento
- [ ] Reaproveitar a mesma janela no Windows, aposentando parte do menu do tray (depende do item acima)

## Fase 5 — Empacotamento e distribuição

- [x] `packaging/macos/flow-st8-mac.spec` — bundle `.app`, `LSUIElement`, `NSMicrophoneUsageDescription`, bundle ID fixo, `target_arch=arm64`, UPX desligado
- [x] `packaging/macos/entitlements.plist` — só para o caminho notarizado; App Sandbox proibido
- [x] `packaging/macos/release.sh` — icns, build, assinatura inside-out, DMG (`create-dmg` com fallback `hdiutil`), notarização opcional via `NOTARY_PROFILE`
- [x] Seção de macOS no `README.md` — build, `xattr` de quarentena, caminho notarizado
- [x] **Build executado.** DMG de 320MB, `.app` assinado, `satisfies its Designated Requirement`, monta e abre. Três falhas de empacotamento corrigidas (ver log de entregas)
- [x] Tamanho do DMG: 320MB
- [ ] Excluir `torch` do bundle no mac — só o `silero-vad` ainda o usa; trocar o VAD encolheria bastante o `.app` de 707MB
- [ ] `build.yml`: adicionar job `macos-14` à matriz
- [x] `packaging/macos/make-dev-cert.sh` cria o certificado autoassinado sem GUI
- [ ] Decidir se o certificado entra no CI ou se o DMG é gerado só localmente

## Fase 6 — Autostart e acabamento

- [ ] `platform/macos/autostart.py` — LaunchAgent em `~/Library/LaunchAgents/com.luckmattos.flow-st8.plist` com `RunAtLoad`
- [x] Rótulo por plataforma: "Start with Windows" / "Iniciar com o sistema"
- [ ] Revisar strings do tray e do README para os dois SOs
- [ ] Atualizar o Roadmap do `README.md`

---

## Riscos abertos

| Risco | Impacto | Mitigação |
|---|---|---|
| ~~pystray Darwin não expor o `NSApp` de forma utilizável~~ | — | **Resolvido pelo spike da Fase 1**: expõe, e o NSPanel convive sem roubar foco |
| Permissão de Acessibilidade negada ou esquecida | App fica mudo, sem erro visível | Checagem no boot + aviso explícito no onboarding |
| Bundle gigante por causa do PyTorch | DMG de vários GB | Excluir `torch` do bundle mac depois da Fase 3 |
| Gatekeeper sem notarização | Alerta de "possível malware" ao instalar | `xattr` documentado; conta paga quando alguém reclamar |
| Refatoração da Fase 0 quebrar o Windows | Regressão para usuários reais | Teste manual completo antes de fechar a fase |
| Overlay do Windows tem o mesmo problema de HiDPI que o mac tinha (bitmap em pixels lógicos, esticado pelo SO) | Badge borrado em tela com escala >100% | Não corrigido — exige declarar DPI awareness do processo (`SetProcessDpiAwareness` + reposicionar em pixels de dispositivo), risco alto de fazer às cegas sem máquina Windows real |

---

## Log de entregas

| Data | Entrega |
|---|---|
| 2026-08-01 | Pipeline de empacotamento macOS: spec, entitlements, `release.sh`, seção do README (Fase 5 parcial). Não executado ainda. |
| 2026-08-01 | Fase 0: split `core/` + `backends/`, protocolos, `paths.py`, `keys.py`, `resources.py`, beeps via sounddevice, CI com import-check. Pendente: rodar no Windows. |
| 2026-08-01 | Fase 1: spike de main thread executado no macOS. NSPanel convive com o `NSApplication` do pystray e não rouba foco. Plano B descartado, Fase 4 ajustada. |
| 2026-08-01 | Fase 2: `CGEventTap` + injeção unicode + `core/permissions.py`. 13/13 automatizados; digitação ponta a ponta verificada lendo o TextEdit de volta. |
| 2026-08-02 | Fase 3: `core/stt/` com openai-whisper e MLX atrás de um protocolo. Dois bugs corrigidos (`pad_or_trim` com numpy fixava o idioma; `ModelHolder` em dtype diferente mantinha duas cópias do modelo). |
| 2026-08-02 | Fase 4: tray unificado em `backends/tray.py` (Windows removido), overlay NSPanel. 13/13 verificações. |
| 2026-08-02 | Fases 2/6: microfone, VoiceOver, LaunchAgent. App inteiro rodando no mac: gravou, transcreveu e digitou no TextEdit em 6,5s. Dois bugs: MLX abortava o processo ao ser chamado de outra thread; detecção de idioma decidia no par ou ímpar. |
| 2026-08-02 | Fase 5: build executado pela primeira vez. Três falhas de empacotamento do MLX corrigidas, mais o `Future` do preload que engolia erros. DMG de 320MB assinado e validado. |
| 2026-08-02 | Rebrand: novo logo em tray/overlay/instalador, spinner do loading (rotação horária verificada por pixel, sem depender de screenshot), círculo pulsante na gravação ligado à amplitude real do microfone. Assets antigos removidos. |
| 2026-08-02 | Instalação em `/Applications` expôs bug real: `enable()` do LaunchAgent faz `launchctl bootstrap` na hora (de propósito, pra não exigir logout), e com `RunAtLoad` isso sobe uma segunda instância ~10s depois — toda vez que autostart liga com o app já rodando manualmente, ou seja, todo primeiro launch. No mac isso é grave (CGEventTap não é exclusivo; dois processos reagiriam à mesma tecla), diferente do Windows (RegisterHotKey falha educado pro segundo). Corrigido com `core/singleton.py` — trava consultiva de SO (fcntl/msvcrt) em `APP_DIR`, checada antes de tudo em `main.py`. Verificado: segunda instância nasce, bate na trava, sai limpo sem tocar tap/mic/modelo. |
| 2026-08-02 | Teste real do usuário achou dois bugs. (1) Texto não colava nem ia pro clipboard — causa real: `mlx_whisper/assets/{mel_filters.npz,gpt2.tiktoken,multilingual.tiktoken}` nunca entravam no bundle (PyInstaller empacota `.py` automaticamente, nunca arquivos de dado soltos); toda transcrição morria com `[load_npz] Input must be a zip file`, então a injeção nunca era sequer chamada — a queixa era um sintoma a três camadas de distância da causa. Corrigido com `collect_data_files("mlx_whisper", ...)` no spec. Verificado direto no arquivo dentro do bundle (`mx.load()` no `.npz` exato) e depois ponta a ponta: hotkey sintético + `say` pelo alto-falante + captura real pelo microfone → texto correto no TextEdit pelo `.app` de verdade. (2) Círculo de gravação grande e cortando a borda — `_draw_recording_circle` desenhava `[0,0,_BADGE,_BADGE]` sem margem nenhuma. Corrigido com `_REC_CIRCLE_R = _BADGE/4` (diâmetro 34px num canvas de 68px, 17px de folga de cada lado) e raio do ponto interno também pela metade (3.5–7.5, era 7–15). |
| 2026-08-02 | Usuário reportou o círculo pixelado/sem resolução. Duas causas empilhadas, só no macOS. (1) O bitmap sempre foi renderizado a 68×68px reais e o `NSImageView` esticava pro tamanho físico da tela Retina (136×136px em escala 2x) — `NSImage` nunca foi construída como Retina de verdade (bitmap em pixels físicos, `size` em pontos lógicos). Corrigido lendo `NSScreen.backingScaleFactor()` uma vez e desenhando tudo (logo, círculo, texto) já em pixels físicos. (2) Mesmo corrigido (1), `ImageDraw.ellipse` do Pillow não tem anti-aliasing — desenha serrilhado em qualquer resolução. Corrigido desenhando em super-resolução 4x e reduzindo com LANCZOS (~1.6ms/frame, folga enorme no orçamento de 33ms a 30fps); confirmado numericamente (7 valores intermediários de alfa na borda, antes zero — transição binária). Nesse processo achei um bug de verdade introduzido por mim: no modo *loading* a variável `draw` do texto de dica nunca era criada, e o `NSTimer` engolia a `UnboundLocalError` em silêncio — o spinner ficaria **invisível** (painel transparente, nunca chamava `setImage_`), sem log nenhum. Só apareceu comparando o estado interno (`mode`/`icon_none`/`spin_deg`) no instante exato da captura contra o pixel renderizado. Corrigido criando o `draw` sempre no frame final, não no buffer supersampled descartado. Windows tem o mesmo problema latente de HiDPI mas não foi tocado — a forma de corrigir lá é declarar DPI awareness do processo, categoria de mudança que não dá pra fazer sem uma máquina Windows real pra testar. |
