# Operations Log

## 2026-06-03 — relaunch-takeover + Painel fallback sem tray (v1.3.0)

- [x] Diagnóstico do cenário "app roda mas não aparece na bandeja" — beco sem saída no relaunch
- [x] Pesquisa: pystray já trata `WM_TASKBARCREATED` (ícone volta sozinho no restart do Explorer) → watchdog descartado
- [x] Relaunch-takeover (`server.py`): `_matar_outras_instancias` (frozen-only) + solta o próprio handle do mutex + re-adquire
- [x] Painel `.url` no porto real a cada boot (`_escrever_painel_url`) + auto-abrir Dashboard quando o tray falha (`_abrir_dashboard`)
- [x] Instalador: atalho "Painel do Apresentador" (Menu Iniciar + Desktop) + bump 1.3.0
- [x] 6 testes novos (`test_takeover_painel`); suíte 161 verdes
- [x] Build + smoke (Painel .url no porto real, /admin 200, **takeover ao vivo** validado, zero `_MEI`) + instalador compilado
- [x] Release v1.3.0 (via /voudormir, autônomo)

## 2026-06-03 — investigação do crash em /temp + migração --onedir + auditoria (v1.2.0)

- [x] Investigação profunda do crash relatado ("não conseguiu fazer algo em /temp") — causa-raiz: `--onefile` extraindo ~95 MB pra `%TEMP%\_MEIxxxx` a cada boot
- [x] Auditoria adversarial multi-agente (8 dimensões, 82 achados → 50 confirmados por refutação)
- [x] Migração `--onefile` → `--onedir` (`scripts\build.bat`) + fallback `_internal\` em `server.py`/`tray.py`
- [x] Instalador Inno Setup (`installer\apresentador.iss` + `build-installer.bat`) → `%LocalAppData%`, sem admin
- [x] Chrome kiosk usa `tempfile.gettempdir()` com fallback `APP_DIR\_kiosk_cache`
- [x] Blindagem anti-crash/DoS: timeout UNC, `_safe_int` no boot, `Content-Length` 413, `ParseError`, `resolve` OSError, `Popen`, `_thumbs_worker` finally, `gc()` projetor
- [x] Races de estado global resolvidas com snapshots sob `_cfg_lock` (RLock)
- [x] Robustez HTTP (BrokenPipe, info disclosure) + tray (clipboard Win32, shutdown, log firewall)
- [x] Docs corrigidos (CLAUDE.md/README/requirements: stdlib pura, build, timeouts)
- [x] 16 testes de regressão novos (`tests\test_robustez_v1_2.py`); suíte 155 verdes
- [x] Build `--onedir` validado + smoke do exe (zero `_MEI` em `%TEMP%`); instalador compilado (~70 MB)
- [x] Tags locais reconciliadas com o remote (`git fetch --tags`) — v1.1.1–v1.1.4 já existiam como releases no GitHub; o "tag faltando" era artefato de fetch local
- [x] Release v1.2.0

## 2026-04-17

- [x] Captura inicial da ideia (gatilho "bora") — entrevista + README.md alpha
- [x] Estrutura base do repositório: `src/`, `scripts/`, `tests/`, docs (CLAUDE/CHANGELOG/IMPLEMENTATIONS/OPERATIONS), `.gitignore`, `requirements.txt`
- [x] Primeira versão do `server.py` generalizada (config externa via JSON, sem GUIDs hardcoded)
- [x] Frontend `index.html` com layout 38/62, 16:9, bordas vermelho/amarelo, progresso
- [x] Script de build `scripts\build.bat` para gerar `.exe` standalone via PyInstaller
- [x] `config.example.json` com template para o operador copiar e editar
- [x] Criação do repositório privado no GitHub (`app-presentation-png-vmix`)
- [x] Primeiro commit e push para `main`

## 2026-04-19 — polimento UX v0.5.0 (layout, cores, preview, sync, menu hambúrguer)

- [x] User pediu: layout 150%, número do slide ao lado do badge, slider de proporção (discreto index + explícito admin), dúvida sobre Preview do vMix
- [x] Resposta sobre Preview: vMix expõe `<preview>N</preview>` mas só pro input inteiro, não slides dentro de uma Photos; útil só se user quisesse "X entrando em breve" baseado em quem está em Preview
- [x] Ajustes adicionais do user: swap de cores (atual=verde em vez de vermelho, progresso=azul em vez de vermelho→amarelo, vermelho reservado pra alerta), banner offline empurra (não sobrepõe), mini preview 16:9 "real" + confirmação de aplicado, "FIM" no canvas do próximo no último slide, preview palestrante usando nome configurado no admin
- [x] Ícone regerado com novas cores (verde/amarelo/azul)
- [x] Backend TDD: `ui_prefs` + `preview_palestrante` no `compute_state` (9 testes novos, total 69 verdes)
- [x] Frontend index: escala 150%, flex em vez de grid (corrigiu layout empilhado), `--atual-ratio` em `flex-grow`, banners de fluxo normal que empurram, classe `.fim` com fundo da página e "FIM" 72px
- [x] Frontend admin: mini preview 16:9 com `box-shadow: inset` pra borda colorida sem aumentar tamanho, `.split-applied` com feedback verde, POST debounce 350ms, polling de `ui_prefs`
- [x] Fix visual: `.slide-frame` estava causando letterbox lateral preto com PNGs 1920×1080; agora `max-width/max-height` + `aspect-ratio: 16/9` + `background: transparent`
- [x] Layout empilhado verticalmente (bug `calc(X * 1fr)` em Chromium); migrado pra `display: flex` com `flex-grow: var(--atual-ratio)`
- [x] Validação real: user testou o slider, monitor registrou 20+ POSTs `/ui_prefs` todos 200
- [x] **Plus — menu hambúrguer no index**: topo-direito, 4 controles (prev/next/goto com validação inteiro+range/reset), status colorido temporário, fecha com click-fora/ESC
- [x] Backend `vmix_control` (helper + rota `POST /admin/api/vmix_control`) chama vMix API `NextPicture`/`PreviousPicture`/`SelectIndex`; validação rejeita GUID não-configurado e índice fora do range antes de chamar o vMix
- [x] `/state` agora inclui `guid` quando ativo pro frontend identificar qual input controlar
- [x] End-to-end: next/prev/goto 5/reset todos 200 no vMix real; goto 9999 rejeitado com 400 "index fora do range (1 a 50)"
- [x] User testou o menu hambúrguer: 10+ POSTs `/vmix_control` registrados, todos 200
- [x] Release v0.5.0 (filé)

## 2026-04-20 — sanitização pré open-source v0.8.1

- [x] User perguntou se repo poderia ficar público — auditoria revelou: nenhuma credencial/token/email pessoal, mas dados cosméticos a limpar
- [x] Removido mock data morto em `src/admin.html` (arrays com GUIDs reais do preset de dev)
- [x] GUIDs de teste trocados por placeholder `aaaaaaaa-0000-...`
- [x] Nome comercial "Jornada Full Face" → genérico em config.example.json, mocks/tray.html, IMPLEMENTATIONS.md
- [x] `config.example.json` limpo com paths genéricos
- [x] `LICENSE` MIT adicionado
- [x] `README.md` redesign "estrela magnet" — badges, features por persona, quick start, arquitetura, API table, CTA de estrela
- [x] 108 testes passando após cleanup
- [x] Release v0.8.1 (filé)

## 2026-04-20 — Projetar Prévia v0.8.0

- [x] User pediu recurso tipo "Projetar Prévia" do OBS: abrir modo apresentador em monitor específico, tela cheia limpa, sem precisar tocar no monitor do palestrante
- [x] Análise do código OBS em `D:\Downloads\obs-studio-32.1.1` via Explore agent: OBS usa Qt (`QGuiApplication::screens()` + `showFullScreen()` + `Qt::BlankCursor`), tracking em vector, `DeleteProjector(this)` remoto
- [x] Decisão arquitetural: usar subprocess Chrome/Edge em modo kiosk (`--app=URL --start-fullscreen --window-position --window-size`) pra reaproveitar HTML existente em vez de reimplementar renderização
- [x] Backend: `list_monitors()` via ctypes `EnumDisplayMonitors`/`GetMonitorInfoW` (stdlib, sem dep nova), `ProjetorManager` com tracking por PID, endpoints `/admin/api/monitors|projetores|projetor_abrir|projetor_fechar`
- [x] Index: modo kiosk via `?kiosk=1` — cursor invisível, botões/slider escondidos
- [x] Admin: seção "Projetar em monitor" com cards visuais (verde quando aberto, clique alterna abrir/fechar)
- [x] Tray: submenu "📺 Projetar em monitor" com 1 item por monitor + "Fechar todos"
- [x] Shutdown: Sair no tray agora fecha projetores antes de parar server
- [x] Validação end-to-end: monitor detectado (`\\.\DISPLAY257` 2560×1440), Chrome encontrado (`C:\Program Files\Google\Chrome\Application\chrome.exe`)
- [x] 7 testes novos (ProjetorManager.abrir/fechar/gc), total 108 verdes
- [x] Release v0.8.0 (filé)

## 2026-04-20 — polish visual v0.7.1

- [x] User testou v0.7.0: port fallback ok, config watcher ok, banner offline ok, F11 ok
- [x] Bug visual: canvas dos slides aparecia vazio com só dots pequenos quando sem palestrante — fix com fundo cinza `#e8e8e8`, placeholders com texto maior ("Sem palestrante ao vivo" / "Aguardando palestrante" / "Sem próximo slide" / "FIM")
- [x] Status overlay movido pro canto inferior esquerdo (estava sobrepondo botões ⛶/☰); só aparece em erros reais
- [x] Banner "entrando em breve" escalado pra 15vh com unidades vh no texto (6vh/3vh) e inclusão da contagem de slides via novo campo `preview_total` no `/state`
- [x] Clique simples/duplo no tray agora abre o Dashboard (antes Modo Apresentador) — mais util pro operador
- [x] Removido auto-abrir do browser no boot — app roda discreto no tray
- [x] Discussão sobre YAML vs JSON: ficou JSON por ora (admin é via primário; alternativa `D:/path` em vez de `D:\\path` resolve escapes)
- [x] Release v0.7.1 (filé)

## 2026-04-19 — distribuição portable v0.4.0 (ícone + estrutura amigável)

- [x] Conversa sobre distribuição: portable zip como primário (padrão da indústria em broadcast — Companion, OBS, Stream Deck), Inno Setup opcional futuramente
- [x] Ícone iteração 1: letra "A" branca com gradiente vermelho→amarelo (rejeitado pelo user)
- [x] Ícone iteração 2: representação do layout do index — retângulo menor à esquerda (borda vermelha) + maior à direita (borda amarela) + barra de progresso no rodapé, sobre card escuro arredondado (aprovado)
- [x] `scripts/gerar_icone.py` com Pillow, exporta multi-tamanho pro .ico
- [x] Estrutura portable amigável: renomeia raiz pra "Apresentador vMix", exe pra "Iniciar Apresentador", HTMLs pra `recursos/`, adiciona LEIA-ME, `config.json` pré-preenchido
- [x] `server.py` ganha `_asset_path` (busca em `recursos/` primeiro), `_ip_lan` (descobre IP da LAN via trick de socket UDP), banner redesenhado mostrando URL pro tablet do palestrante, onboarding automático pro /admin quando não há palestrantes
- [x] `scripts/build.bat` reescrito: gera `dist/Apresentador vMix/` com estrutura montada automaticamente
- [x] `installer/LEIA-ME.txt` em pt-BR com fluxo em 3 passos + troubleshooting
- [x] `meta viewport` nos HTMLs — tira o nome vermelho do explorer do VS Code + rendering correto em tablet
- [x] Build validado: 8.3 MB total, todos os endpoints funcionais, onboarding abre /admin no primeiro boot
- [x] Release v0.4.0 (filé)

## 2026-04-19 — sessão "à prova de show ao vivo" v0.3.0 (TDD + miniaturas)

- [x] Conversa identificou 10 rachaduras após v0.2.0: match ambíguo, arquivo sumido, config corrompido, CORS dependency, UNC lento, sem heartbeat, sem telemetria de clientes, logs sem rotação, imagens em RAM
- [x] Plano em 6 fases: (2) recovery → (1) match ancorado → (6) miniaturas → (3) rede → (4) observabilidade → (5) streaming
- [x] Fase 2: `carregar_config` com recovery em caso de JSON corrompido + backup em `config.bak.json`; `rescan_pasta(guid)` + `/img` responde 410 Gone quando arquivo some
- [x] Fase 1: `match_filename(title, imagens)` ancorado com casefold e desempate por comprimento
- [x] Fase 6: `listar_preview` + `preview_img_path` com bloqueio de traversal; grid CSS 16:9 + lightbox fullscreen; auto-render no `agendarTestar`
- [x] Fase 3: `_LS_EXECUTOR` com `future.result(timeout=3s)`; `/admin/api/vmix_xml` como proxy; frontend `fetchVmixXml` com fallback; banners globais no dashboard e index; heartbeat "atualizado há X"
- [x] Fase 4: `_CLIENTES` + `registrar_cliente` + `clientes_ativos`; chip `👤 N` no header; `setup_logging` com `RotatingFileHandler` em `logs/YYYY-MM-DD.log`
- [x] Fase 5: `_send_file` streaming via `shutil.copyfileobj` + tratamento de `BrokenPipeError`
- [x] TDD: 60 testes no total, 24 novos cobrindo as 6 fases
- [x] Validação real contra vMix rodando: todos os endpoints retornaram o esperado incluindo 410 Gone e bloqueio de path traversal
- [x] Docs atualizados (README resiliência + CHANGELOG v0.3.0 + IMPLEMENTATIONS detalhes técnicos)
- [x] Release v0.3.0 (filé)

## 2026-04-19 — sessão robustez v0.2.0 (TDD + formatos de imagem)

- [x] Plano em plan mode aprovado com 6 fases (infra testes + IMAGE_EXTS + natural sort + validação POST + health endpoint + botão testar)
- [x] Fase 0: infra `tests/__init__.py` + `conftest_helpers.py` com fixtures (`make_images`, `fake_vmix_xml`); 3 arquivos de teste
- [x] TDD red → 36 testes escritos primeiro, todos falhando inicialmente (6 fails + 23 errors por funções não existentes)
- [x] Fase 1: `IMAGE_EXTS` + `_is_image` + refactor de `carregar_palestrantes` e `list_dir`; frontend `admin.html` renomeando `pngs`→`imagens` em 9 lugares
- [x] Fase 2: `_natural_key` + aplicado no sort de `carregar_palestrantes` e `list_dir`
- [x] Fase 3: `validar_config(cfg) -> list[str]` com todas as regras; `salvar_config` levanta `ValueError("config_invalida", [erros])`; handler POST devolve `erros` estruturado em 400
- [x] Fase 4: helpers `_input_by_num` / `_input_by_key` / `_find_palestrante_em` extraídos top-level; `diagnosticar_palestrante` + `diagnosticar_todos`; rota `/admin/api/health`; frontend com `HEALTH_BY_GUID`, `STATUS_META`, `renderStatusRow`, CSS de badges coloridas
- [x] Fase 5: rota `/admin/api/validate`; frontend com `testarPalestrante` + `agendarTestar` (debounce 400 ms) + bloco `.modal-diagnostic` com check-list colorida; `apiPost` preserva `err.detalhes` e `salvarPalestrante` mostra erros inline
- [x] TDD green → 36/36 testes passando
- [x] Validação end-to-end contra vMix real do usuário: `/health` retorna `ok` para Wagner + Vinícius; `/validate` corretamente detecta guid_orfao e pasta_inacessivel; POST com dados inválidos rejeitado com 400 e lista de erros; pasta mock com JPG + JPEG + WEBP + BMP conta `imagens=4`
- [x] Docs atualizados (README + CHANGELOG + IMPLEMENTATIONS)
- [x] Release v0.2.0 (filé)

## 2026-04-19 — sessão de ajustes (v0.1.0)

- [x] Análise do projeto + leitura do vMix real (localhost:8088/api) pra mapear inputs e padrões de uso
- [x] Detecção dos padrões: 6 Photos + 6 Colour com overlay[Photos], nomenclatura `LETRA + descrição` nos blanks
- [x] Mock estático `admin.html` validado com o usuário (cards, tabs, sugestões automáticas, modal)
- [x] Iteração 1: box padronizado de número de input com padding 2 dígitos, lápis de edição inline no card, sugestão automática de nome
- [x] Iteração 2: tree de pastas com raízes detectadas (preset + avô), auto-match por tokens do shortTitle
- [x] Iteração 3: polling real do vMix direto via CORS — admin 100% dinâmico, re-renderiza ao vivo conforme vMix muda
- [x] Iteração 4: layout aproveitando largura total (2560 friendly), paths completos sem truncar
- [x] Backend: rotas `/admin`, `/admin/api/config` (GET/POST com hot-reload), `/admin/api/ls` (com drives + atalhos), `compute_state` varrendo overlays globais
- [x] Iteração 5: file browser estilo explorer (drives + atalhos + tree grande), botão "usar esta pasta" + 🏠 início, navegação livre sem sandbox
- [x] Teste real: usuário adicionou 2 palestrantes (Wagner + Vinícius), `/state` retornou dados corretos, sem erros no monitor
- [x] Release v0.1.0 + push para `main`

## 2026-05-16 — suporte a input List (VideoList) + frames de vídeo (v1.1.0)

- [x] Análise da app + leitura do código (`server.py`, `index.html`, `admin.html`, config)
- [x] Entrevista via `AskUserQuestion`: List mista vídeo+imagem, tag de vídeo, frame pré-gerado, formato do build
- [x] Inspeção do preset `.vmix` real do usuário pra confirmar a estrutura de um input List
- [x] Validação contra vMix v29 ao vivo: `<list><item>` não tem atributo `selected`, só `selectedIndex` (1-based)
- [x] Backend: `_parse_list_input`, `_kind_de`, `_estado_lista`, ramo List no `compute_state`, `vmix_list_control`, endpoints `/list-img` e `/list-thumb`
- [x] Frames de vídeo: `gerar_thumb_video` (ffmpeg), `_ensure_dur` (ffprobe), pasta `_thumbpresentation/` ao lado dos vídeos
- [x] Geração assíncrona: `_thumbs_worker` + registro de job + `GET gerar_thumbs/status`, polling no admin
- [x] Frontend: card de vídeo → frame + tag vermelha "VÍDEO" + tempo no canto; `pintarSlot`, container query
- [x] Admin: seletor de tipo Photos/List, botão "Gerar frames dos vídeos", diagnóstico List-aware
- [x] Build: exe único `--onefile` com ffmpeg/ffprobe embutidos; `build.bat` reescrito em ASCII + caminhos absolutos
- [x] Fixes: `validar_config` não-bloqueante por pasta morta, `box-shadow` no lugar de `border` (letterbox), `cqmin`, `ConnectionAbortedError` silenciado
- [x] Docs antivírus: seção no `LEIA-ME.txt` + `Liberar no Defender.bat`
- [x] Monitor de erros do server ativo durante toda a sessão de testes
- [x] 139 testes verdes; validação ao vivo (2 inputs List, 6 frames gerados, 0 falhas)
- [x] Release v1.1.0 (filé) — exe único anexado como asset da release

## 2026-05-16 — deploy no PC do evento + auditoria de robustez (v1.1.1 / v1.1.2)

- [x] Deploy do exe no PC do evento (`PC-do-evento`, 192.168.X.X) via SSH; usuário relatou "sem ícone na bandeja"
- [x] Diagnóstico via SSH: app rodava, mas log mostrava `tray falhou: icon.ico nao encontrado`
- [x] **v1.1.1** — `tray.py._icon_path` passou a procurar em `sys._MEIPASS` (icon embutido no exe); `icon_alert.ico` embutido no build
- [x] Liberada a porta 5000 no firewall do PC do evento (`netsh advfirewall`) via SSH
- [x] Usuário reportou HTTP 500 ao salvar palestrante numa instalação nova
- [x] Causa: `GET /admin/api/config` dava 500 sem `config.json` — corrigido (devolve config padrão)
- [x] **Auditoria completa** — 3 revisões de código em paralelo (server.py, tray.py+build, frontend)
- [x] **v1.1.2** — ~15 correções de robustez: cache de `fetch_vmix_xml`, blindagem de `carregar_config`/handlers/`salvar_ui_prefs`, `Handler.timeout`, `_reiniciar` libera mutex, `pollTick`/`tick` com timeout e separação de erros, `pollThumbs` com parada, build com `--paths`/`--hidden-import`
- [x] 139 testes verdes; rebuild do exe
- [x] Smoke test do exe no PC do evento via SSH: instalação nova, `GET /config` → 200, endpoints OK, payload inválido → 400, log limpo, `/state` concorrente em paralelo
- [x] Releases v1.1.1 e v1.1.2 — exe único anexado como asset
