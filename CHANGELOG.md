# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento segue [Semantic Versioning](https://semver.org/).

## [0.8.0] — 2026-04-20

### Added
- **"Projetar Prévia" inspirado no OBS** — abre o modo apresentador em tela cheia num monitor específico, controlado remotamente pelo admin/tray
- **Enumeração de monitores** via `EnumDisplayMonitors`/`GetMonitorInfoW` (ctypes stdlib, sem dep nova): retorna `indice`, `nome` (ex: `\\.\DISPLAY1`), `x`, `y`, `width`, `height`, `primario`
- **`ProjetorManager`**: abre Chrome/Edge em modo `--app=` + `--start-fullscreen` + `--window-position=X,Y` + `--window-size=W,H`, usa `--user-data-dir` isolado por monitor pra não colidir com sessão normal. Tracking por PID.
- **Modo kiosk no index** (`?kiosk=1`): esconde cursor (`cursor: none`), esconde botões ⛶/☰ e o slider discreto, bloqueia seleção de texto — palestrante só vê o conteúdo
- **Endpoints novos**:
  - `GET /admin/api/monitors` → lista de monitores
  - `GET /admin/api/projetores` → projetores abertos (polling)
  - `POST /admin/api/projetor_abrir {monitor_idx}` → lança projetor, retorna PID
  - `POST /admin/api/projetor_fechar {pid}` ou `{pid: "todos"}` → fecha
- **Admin UI**: nova seção "Projetar em monitor" com cards clicáveis de cada monitor (mostra resolução + posição + badge "primário"); card fica verde quando projetor está aberto; clique alterna abrir/fechar
- **Tray submenu**: "📺 Projetar em monitor" com um item por monitor detectado, indica `●` nos que já têm projetor, inclui "✕ Fechar todos"
- **Detecção automática de Chrome/Edge** em `%ProgramFiles%`, `%ProgramFiles(x86)%`, `%LocalAppData%`
- **Shutdown limpo**: `Sair` do tray agora também fecha todos os projetores abertos
- 7 testes novos em `tests/test_projetor.py` (abrir, fechar, fechar_todos, gc, tracking por monitor)

### Changed
- `_shutdown_server()` fecha projetores antes de parar o HTTP server
- `/admin/api/monitors` e `/admin/api/projetores` silenciados no log (polling frequente)

## [0.7.1] — 2026-04-20

### Added
- Campo `preview_total` no `/state` — número de slides do palestrante em preview
- Banner "entrando em breve" **escalado pra 15vh** com texto grande em vh units (6vh no nome, 3vh no meta) e contagem de slides: `🟡 49 slides · Wagner entrando em breve`
- Placeholders dos slides com texto maior e mais claro: **"Sem palestrante ao vivo"** / **"Aguardando palestrante"** / **"Sem próximo slide"** / **"FIM"**

### Changed
- Clique simples/duplo no ícone do tray agora abre o **Dashboard (admin)** (antes era Modo Apresentador) — mais útil pro operador
- Removido auto-abrir do browser no boot — app roda discreto no tray, operador abre manualmente pelo menu
- Status overlay movido de `top:right` pra `bottom:left` (não colide mais com botões ⛶/☰ do index)
- Status só aparece em **erros reais** (`ok: false`) — sem spam de "Nenhum palestrante" quando ativo=false
- `.slide-frame` com fundo cinza claro `#e8e8e8` (combina com a página) em vez de transparente

### Fixed
- Canvas dos slides apareciam vazios com só "bolinhas" (dots dos badges) quando sem palestrante ativo — agora mostra placeholder com texto explícito centralizado

## [0.7.0] — 2026-04-19

### Added
- **Port fallback**: se 5000 ocupado, tenta 5001…5009 automaticamente e notifica a porta real
- **Single-instance guard** via `CreateMutexW` do Windows (ctypes, stdlib puro) — segunda instância mostra MessageBox e sai sem conflito
- **Health check interno**: thread daemon no tray pinga `/state` a cada 1.5s; 3 falhas seguidas → notificação "🔴 Servidor interno parou" (detecta thread zumbi sem visibilidade externa)
- **ConfigWatcher**: poll do `mtime` do config.json; edição externa (fora do admin) dispara reload automático de `CFG`, `VMIX_HOST`, `VMIX_PORT`, `PALESTRANTES` sem precisar de restart
- **Timeout em `carregar_palestrantes`** (default 5s por pasta) — UNC lento/caído não trava mais `salvar_config` nem o admin
- **Ícone de alerta** (`assets/icon_alert.ico`) com badge vermelho "!" no canto — tray troca pro ícone de alerta quando vMix offline >10s, volta ao normal quando reconecta
- **Notificação de palestrante com nome** — "⚪ Wagner saiu do ar" em vez do genérico (guardando nome anterior)
- **Feedback do firewall**: `ShellExecuteW` retorna código checado → notify "✓ Porta liberada" / "Permissão negada (UAC cancelado)" / "Erro"
- **Fallback do dialog tkinter**: se `simpledialog.askstring` falhar (runtime Tcl ausente no exe), notifica "use o Dashboard pra editar IP"
- **Modo kiosk no index**: botão **⛶** no canto superior direito + tecla **F11** alternam tela cheia (via Fullscreen API), pro palestrante não ver a barra de endereço
- 6 testes novos em `tests/test_resilience.py` cobrindo bind com fallback, single-instance, health check, config watcher

### Changed
- `_LS_EXECUTOR` (ThreadPoolExecutor) compartilhado entre `list_dir` e `carregar_palestrantes` — isolamento de operações de filesystem
- `main()`: 1º verifica single-instance, 2º faz bind com fallback, 3º inicia server thread + file watcher, 4º monitor inicia dentro do tray
- `scripts/gerar_icone.py` gera `icon.ico` + `icon_alert.ico` numa só execução

### Fixed
- **Thread do HTTP server morrendo em silêncio**: antes o tray continuava ativo mesmo com server zumbi; agora detectamos em ≤5s e avisamos
- **Duas instâncias do .exe causando conflito de porta**: agora a segunda detecta mutex e sai com mensagem amigável
- **Edição manual de config.json ignorada até restart**: agora recarrega em ≤1s

## [0.6.0] — 2026-04-19

### Added
- **Tray icon na bandeja do Windows** (pystray + Pillow): ícone do app perto do relógio, menu contextual com clique direito
- Menu dinâmico do tray (reconstruído a cada abertura):
  - Status: `✓ vMix host:port` (clique abre dialog tkinter pra editar IP/porta)
  - Rede LAN: `🌐 Rede: http://IP:5000/` (clique copia URL pra clipboard)
  - **Por palestrante configurado**: label com posição `X / Y` (prefixo `●` em verde quando ao vivo), + 3 ações `▶ Avançar` / `◀ Voltar` / `↺ Reset`
  - `🖼️ Abrir Modo Apresentador` (default do clique simples no ícone)
  - `⚙️ Abrir Dashboard (admin)`
  - Submenu `🛠️ Configs`: abrir pasta de logs, liberar porta 5000 no firewall (UAC), reiniciar servidor, sair
- Dialog tkinter pra editar `host:port` do vMix direto do tray, com `parse_host_port()` aceitando `host`, `host:port` ou `http://host:port/`
- Helper `copiar_para_clipboard()` via tkinter (sem dep extra)
- Liberação de porta no firewall via `netsh` + `ShellExecuteW runas` (UAC prompt)
- **Notificações Windows** (via `icon.notify`) em eventos críticos:
  - 🔴 vMix offline há >10s
  - 🟢 vMix voltou online
  - 🟢 Palestrante X entrou no ar
  - ⚪ Palestrante saiu do ar
- `MonitorNotificacoes` em thread daemon polando `compute_state()` a cada 1.5s
- `_shutdown_server()` parando o HTTP server limpo quando user clica Sair/Reiniciar no tray
- 18 testes novos em `tests/test_tray.py` cobrindo parse, menu builder, posição e helpers

### Changed
- `main()` agora roda o HTTP server em thread daemon e o **tray bloqueia a main thread** (pystray.Icon.run); fallback pra bloqueio no serve_forever se pystray não estiver disponível
- `scripts/build.bat`: `--noconsole` (sem janela CMD preta), `--hidden-import pystray._win32`, `--hidden-import PIL`
- Exe passou de 8.3 MB → 29 MB (pystray + tkinter + Pillow embutidos) — ainda perfeitamente portable
- `requirements.txt` ganha `pystray>=0.19.5` + `Pillow>=10.0` como runtime (antes eram só build)

## [0.5.1] — 2026-04-19

### Added
- Grid de botões numerados no menu hambúrguer (até **200** botões; slides acima do limite mostram **…** com tooltip sugerindo o campo "Ir pro slide")
- Botão do slide atual em verde sólido com glow; próximo (atual+1) com borda amarela
- Event delegation no grid — um único listener cobre os 200 botões

### Changed
- Removida a setinha spinner do `input[type=number]` do campo "Ir pro slide" (CSS `-webkit-appearance: none` + `-moz-appearance: textfield`)
- `.claude/` agora no `.gitignore` (settings locais do Claude Code não vão mais pro repo)

## [0.5.0] — 2026-04-19

### Added
- **Menu hambúrguer no index** (topo direito) com controles do slideshow:
  - **◀ Anterior** / **Próximo ▶** (verde)
  - **Campo "Ir pro slide"** com validação inteiro + range (1 a N, destaca borda vermelha se inválido; Enter envia; auto-disabled quando fora do range ou sem palestrante ativo)
  - **↺ Reiniciar** (volta pro primeiro slide)
  - Status colorido (verde ok / vermelho erro) que some em 2.5s
  - Fecha clicando fora, no próprio botão ☰ ou tecla ESC
- `vmix_control(funcao, guid, value)` — helper que chama a API HTTP do vMix (`NextPicture`, `PreviousPicture`, `SelectIndex`)
- Endpoint `POST /admin/api/vmix_control` aceitando `{action: "next|prev|goto|reset", guid, index?}` com validação: GUID deve estar configurado, index inteiro dentro do range da pasta
- Campo `guid` no retorno de `/state` quando ativo — frontend usa pra saber qual input controlar
- Layout do modo apresentador escalado 150% — badges ATUAL/PRÓXIMO (14→21px), palestrante (22→33px), contador (18→27px), progress bar (8→12px)
- Número do slide em grande destaque ao lado de cada badge: `7 / 49` em ATUAL, `8 / 49` em PRÓXIMO
- Controle deslizante de proporção ATUAL/PRÓXIMO (20-80%, default 38), com discrição no rodapé do index (opacity 0.18, hover 1.0)
- Slider explícito no dashboard com mini preview "real" 16:9 dos 2 slides (verde/amarelo) + confirmação visual "✓ aplicado" por 1.4s após salvar
- Sync da proporção entre todos os clientes via `ui_prefs` no `config.json` — admin muda → server persiste → todos os tablets pollando `/state` aplicam em ≤ 500ms
- Novas rotas `GET/POST /admin/api/ui_prefs` (validação + clamp 20-80)
- Campo `preview_palestrante` no `/state` — detecta quando `<preview>N</preview>` do vMix aponta pra um input de palestrante diferente do que está em Program
- Banner amarelo "🟡 Wagner entrando em breve" no topo do modo apresentador (empurra conteúdo, não sobrepõe) usando o nome de exibição configurado no admin
- "FIM" grande no canvas do próximo quando o slideshow acabou — borda cinza clara, fundo cor da página, fonte 72px letter-spacing 10
- 9 testes novos cobrindo `ui_prefs` (default, persist, clamp, preserva palestrantes) e `preview_palestrante` (diferente, igual, não-palestrante)

### Changed
- **Cores do app:** slide atual de vermelho → **verde** `#2ea043`; progress bar de vermelho→amarelo → **azul** `#3b82f6 → #0ea5e9`; vermelho reservado para alertas (banner offline, input ausente, diagnósticos falhos)
- Ícone regerado com as novas cores (verde/amarelo/azul)
- `cardLive` no admin: borda + sombra verde em vez de vermelha
- `badge.program` verde no admin; dot do `live-preview` pulsa em verde
- Banner offline mudou de `position: fixed` sobrepondo pra fluxo normal que **empurra conteúdo** (mais amigável pro palestrante)
- Layout do `<main>` do index trocou `display: grid` com `calc(var * 1fr)` (bugava em alguns Chromium) para `display: flex` com `flex-grow: var(--atual-ratio)` — sintaxe 100% compatível

### Fixed
- Slide-frame deixava **letterbox lateral preto** com PNGs 1920×1080 porque `width: 100%` + `max-height: 100%` quebravam o aspect-ratio; agora usa só `max-width/max-height` + `aspect-ratio: 16/9`, browser escolhe a maior dimensão sem estourar, e `background: transparent` em vez de preto
- Banner offline antes sobrepunha os slides; agora empurra

## [0.4.0] — 2026-04-19

### Added
- Ícone dedicado (`assets/icon.ico`) com o próprio layout do modo apresentador — slide atual pequeno (esq, vermelho) + slide próximo maior (dir, amarelo) + barra de progresso vermelho→amarelo, fundo escuro do card do dashboard
- Script `scripts/gerar_icone.py` pra regerar via Pillow (multi-tamanho 16/32/48/64/128/256)
- Estrutura portable amigável pra leigo em `dist/Apresentador vMix/`: exe nomeado "Iniciar Apresentador", `LEIA-ME.txt` com fluxo em 3 passos, HTMLs em subpasta `recursos/`
- `config.json` pré-preenchido (em vez de exigir copiar de `config.example.json`)
- Banner de boot mostra URL de LAN (`http://192.168.X.X:5000/`) explicitamente pro operador passar pro tablet
- Onboarding automático: no primeiro boot sem palestrantes, browser abre direto no `/admin` (em vez de `/`)
- `meta viewport` nos HTMLs — melhor rendering em tablet e sem error no lint do VS Code

### Changed
- `server.py` busca HTMLs em `recursos/` primeiro, com fallback para `APP_DIR` (mantém dev mode funcionando)
- `scripts/build.bat` reescrito: PyInstaller com `--icon`, spec file em `build/`, montagem automática da estrutura portable
- Exe renomeado de `apresentador.exe` para `Iniciar Apresentador.exe`

## [0.3.0] — 2026-04-19

### Added
- Match de filename ancorado (`match_filename`) — resolve ambiguidade `slide 1.png` vs `slide 10.png`, desempate pelo mais longo
- Re-scan automático no handler `/img/<guid>/<arquivo>` — se arquivo sumiu depois do boot, re-lê a pasta; se realmente não existe mais, responde **410 Gone** com JSON descritivo
- Recovery automático de `config.json` corrompido — backup em `config.bak.json`, log de aviso, server sobe com config vazia
- Endpoint `GET /admin/api/preview?pasta=...` + `GET /admin/api/preview/img?pasta=&arq=` — grid de miniaturas do modal com path-traversal bloqueado
- Endpoint `GET /admin/api/vmix_xml` — proxy do XML do vMix (fallback CORS pro admin)
- Endpoint `GET /admin/api/clientes` — IPs que acessaram `/state` nos últimos 30 s
- Grid de miniaturas + lightbox fullscreen no modal de adicionar/editar palestrante
- Banner vermelho fixo (dashboard e modo apresentador) quando vMix offline há 3 ticks
- Heartbeat visual no rodapé do admin ("atualizado há X ms/s" com cor por severidade)
- Chip "👤 N" no header mostrando tablets/browsers conectados
- Logs com rotação em `logs/YYYY-MM-DD.log` via `logging.handlers.RotatingFileHandler` (10MB × 5 backups)
- Timeout de 3s em `list_dir` via `ThreadPoolExecutor` — UNC lento não bloqueia worker
- `rescan_pasta(guid)` como função pública reusável
- 24 testes novos (total 60) cobrindo: match ancorado, recovery, rescan, preview, path traversal, clientes ativos, timeout, streaming

### Changed
- `_send_file` agora usa `shutil.copyfileobj` com chunks de 64KB (streaming) — slides grandes não explodem RAM
- `compute_state` e `diagnosticar_palestrante` usam o novo `match_filename` ancorado
- `carregar_config`: não crasha mais em JSON corrompido ou arquivo ausente; retorna default com aviso
- `main()` chama `setup_logging()` e adiciona `Logs:` ao banner de boot
- Handler `log_message` encaminha pro logger (console + arquivo) em vez de stderr bruto
- `fetchVmixXml` no admin tenta CORS direto primeiro, fallback para proxy `/admin/api/vmix_xml`

### Fixed
- `/img/<guid>/<arq>` retornava 404 silencioso quando arquivo era removido da pasta depois do boot — agora faz rescan e responde 410 Gone com diagnóstico

## [0.2.0] — 2026-04-19

### Added
- Suporte a múltiplos formatos de imagem — PNG, JPG, JPEG, BMP, GIF, WEBP (os mesmos que o vMix aceita); constante `IMAGE_EXTS` parametrizada
- Natural sort de arquivos — `slide 2.png` antes de `slide 10.png` mesmo sem zero-padding (tanto em `carregar_palestrantes` quanto em `list_dir`)
- Validação stricta no `POST /admin/api/config` — rejeita nome vazio, GUID duplicado, pasta inexistente, pasta sem imagens, com lista de `erros` estruturada por caminho
- Endpoint `GET /admin/api/health` — diagnóstico ao vivo por palestrante (`ok`, `guid_orfao`, `pasta_inacessivel`, `sem_imagens`, `filename_mismatch`, `vmix_offline`)
- Endpoint `GET /admin/api/validate?guid=&pasta=` — diagnóstico avulso sem persistir no config
- Badges de saúde em cada card do dashboard, atualizadas a 500 ms
- Botão "🔍 testar" no modal com check-list inline
- Debounce 400 ms — ao trocar input ou colar pasta, valida automaticamente
- Suíte de testes `unittest` (stdlib) com 36 casos cobrindo config/filesystem/vmix

### Changed
- Campo JSON `pngs` renomeado para `imagens` em `/admin/api/ls` (contagem agregada)
- Label do modal "Pasta de PNGs" → "Pasta de imagens (PNG, JPG, JPEG, BMP, GIF, WEBP)"
- Helpers internos de `compute_state` extraídos para top-level (`_input_by_num`, `_input_by_key`, `_find_palestrante_em`) para reuso pelo diagnóstico
- Log silencia também `/admin/api/health` (polling 500 ms)

### Fixed
- Saída do "próximo slide" quebrava quando PNGs não tinham zero-padding (natural sort corrige)

## [0.1.0] — 2026-04-19

### Added
- Estrutura inicial do repositório
- Servidor HTTP stdlib puro com endpoints `/`, `/state`, `/img/<guid>/<arquivo>`, `/favicon.ico`
- Cliente da API HTTP do vMix com polling a cada 500 ms
- Detecção do palestrante ativo em Program direto, como overlay de input composto ou em overlay global (Overlay1–16)
- Frontend web com layout 38/62 (atual/próximo), aspect-ratio 16:9, bordas vermelho/amarelo, barra de progresso
- Dashboard `/admin` com CRUD de palestrantes (adicionar, editar nome inline, remover)
- Endpoints `/admin/api/config` (GET/POST) com hot-reload em memória — sem restart
- Endpoint `/admin/api/ls` com navegação livre por drives + atalhos detectados (preset vMix + pasta pai)
- File browser estilo explorer: drives, atalhos, breadcrumb, botão "usar esta pasta"
- Auto-match de pasta ↔ slideshow por tokens do `shortTitle`
- Dashboard dinâmico: re-renderiza ao vivo conforme o vMix muda (slide atual, arquivo, Program)
- Padronização visual dos números de input com box e padding de 2 dígitos
- Configuração externa via `config.json` (IP do vMix + raízes + lista de palestrantes)
- Build via PyInstaller `--onefile` gerando `apresentador.exe` (~8 MB); copia `admin.html` junto
- README.md alpha com proposta, fluxo e exemplo de config
- CLAUDE.md com instruções para assistentes de IA
