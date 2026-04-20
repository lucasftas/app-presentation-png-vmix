# Implementations

## v0.5.0 — 2026-04-19

**Resumo:** release de polimento UX — layout do modo apresentador escala 150%, controle deslizante de proporção sincronizado entre todos os tablets via server, banner "entrando em breve" usando Preview do vMix, "FIM" explícito quando acaba o slideshow, paleta reorganizada (atual=verde, progresso=azul, vermelho só pra alerta). Coberto por 69 testes stdlib (9 novos).

**Menu de controle do slideshow (novo em v0.5):**
- `vmix_control(funcao, guid, value=None)` — helper stdlib que monta a URL `http://vmix/api/?Function=...&Input=...&Value=...` e chama via `urllib.request`. Captura exceções (rede, vMix offline) em `{ok: false, erro: str}`
- Rota `POST /admin/api/vmix_control` com body `{action, guid, index?}` — mapeia `action` pra `NextPicture`/`PreviousPicture`/`SelectIndex`; valida que `guid` está em `PALESTRANTES`; `index` inteiro 1 ≤ n ≤ total; 400 com mensagem descritiva em caso de erro
- Campo `guid` no retorno de `/state` quando `ativo` — usado pelo frontend pra identificar qual input controlar
- Frontend `index.html`: botão `.hamburger-btn` (fixed top-right, ☰ branco), painel `.menu-panel` com 3 linhas (prev/next, goto input+btn, reset), status colorido com timeout 2.5s, fecha via click-fora/click-botão/ESC, `_stateAtual` armazena último `/state` pra saber guid e total
- Validação frontend: `Number.isInteger(n) && n >= 1 && n <= total` toggle `.invalid` e `btn-goto.disabled`; Enter submete; input `type="number" min="1" step="1" inputmode="numeric"`
- Botões `.btn-ctrl.primary` (verde próximo, cor do slide atual), `.btn-ctrl.reset` (vermelho discreto, único vermelho na UI fora dos alertas — semanticamente "ação destrutiva reversível")

**Backend (`src/server.py`):**
- `UI_PREFS_DEFAULTS = {"split_ratio": 38}` + `get_ui_prefs()` / `salvar_ui_prefs(novo)` com clamp 20-80 e merge que **preserva palestrantes** do config.json ao atualizar só as prefs
- Rotas novas `GET /admin/api/ui_prefs` (silenciada no log) e `POST /admin/api/ui_prefs`
- `compute_state()` agora inclui sempre `ui_prefs` no retorno (inclusive em erros) — clientes usam esse valor como fonte da verdade
- `_preview_palestrante(root, ativo_guid)` — lê `<preview>N</preview>` do XML, chama `_find_palestrante_em` no input N; retorna `None` se não tiver preview, se não for palestrante ou se for o mesmo já em Program

**Frontend (`src/index.html`):**
- Variável CSS `--atual-ratio` controla a proporção; layout migrado de `display: grid` + `calc(var * 1fr)` (bugava em Chromium) para `display: flex` com `flex-grow: var(--atual-ratio)` / `calc(100 - var(--atual-ratio))` — sintaxe universal
- `.slide-frame`: removido `width: 100%` + `background: #000` que causavam letterbox lateral com PNGs 1920×1080; agora `max-width/max-height: 100%` + `aspect-ratio: 16/9` + `background: transparent`
- Escala 150%: badges 14→21px, palestrante 22→33, contador 18→27, progress 8→12, padding 20→24
- `.slide-num` grande ao lado do badge (`7 / 49`)
- `.panel-proximo.fim .slide-frame` — quando último slide, fundo `#f2f2f2` (cor da página), borda cinza claro `#c8cdd4`, placeholder "FIM" em 72px 800-weight letter-spacing 10
- Slider discreto no rodapé (`opacity: 0.18` / hover `1.0`), debounce 400ms, POST pro server
- `aplicarSplitDoServer(ratio)` respeita flag `_splitDirty` — enquanto user arrasta, ignora polling pra evitar race
- Banner offline virou fluxo normal (flex child, `display: none/block`); novo `.preview-banner` amarelo usando mesmo mecanismo de push

**Frontend (`src/admin.html`):**
- Controle "PROPORÇÃO ATUAL / PRÓXIMO" na seção top dos palestrantes com:
  - Mini preview 16:9 — `<div class="preview">` com 2 `.slot` lado-a-lado, `aspect-ratio: 16/9`, `box-shadow: inset 0 0 0 2px <cor>` em vez de `border` (não estoura o tamanho), `flex: var(--ratio)`
  - Badge `.split-applied` que aparece 1.4s com "✓ aplicado" (ou vermelho se erro)
  - POST com debounce 350ms, `_adminSplitDirty` evita overwrite pelo polling enquanto user arrasta
- `pollTick` agora fetcha `ui_prefs` em paralelo e chama `sincronizarSplitComServer` — cross-device sync real
- Paleta nova: `#2ea043` (verde) em `.badge.program`, `.card-live`, `.input-row.program`, `.live-preview .dot`; `#3b82f6`→`#0ea5e9` (gradient azul) em `.card .mini-fill`, `.input-progress .mini-fill`, `accent-color` dos sliders

**Ícone (`scripts/gerar_icone.py`):**
- `GREEN = (0x2E, 0xA0, 0x43)` substitui `RED` no slide atual
- Barra de progresso usa `BLUE_A=(0x3B,0x82,0xF6) → BLUE_B=(0x0E,0xA5,0xE9)` em vez do antigo vermelho→amarelo
- Vermelho totalmente removido — preservado para alertas na UI

**Testes (69 total, 9 novos):**
- `UiPrefsTests` × 5: default quando ausente, persiste, clampa fora do range, ignora campos desconhecidos, não destrói palestrantes
- `PreviewPalestranteTests` × 4: palestrante diferente do ativo, igual ao ativo retorna None, não-palestrante retorna None, `/state` inclui `ui_prefs` default

**Validação end-to-end:**
- `POST /admin/api/ui_prefs {split_ratio: 55}` persiste, `/state` reflete imediatamente, admin mostra "✓ aplicado"
- `/state` detectou `preview_palestrante: "003 - Vinícius"` porque operador tinha input 79 em Preview no vMix
- Monitor registrou 20+ POSTs `ui_prefs` durante teste do user, todos 200

## v0.4.0 — 2026-04-19

**Resumo:** release de distribuição — o app vira um portable pronto-pra-copiar com estrutura "obvia pra leigo", ícone dedicado representando o próprio layout do produto, onboarding automático e banner de boot que diz explicitamente qual URL entregar pro palestrante.

**Ícone (`assets/icon.ico` + `scripts/gerar_icone.py`):**
- 512px master + export multi-tamanho (16/32/48/64/128/256) pro .ico
- Design = representação do index.html: 2 retângulos 16:9, esquerda menor (38%) com borda vermelha `#e63946`, direita maior (62%) com borda amarela `#f2b705`, centralizados verticalmente dentro de um card escuro arredondado `#1a1d23`
- Barra de progresso com gradiente vermelho→amarelo embaixo (mesma do rodapé do modo apresentador)
- Máscara `rounded_rectangle` no final garante cantos arredondados transparentes

**Estrutura portable (`dist/Apresentador vMix/`):**
- 8.3 MB total
- Apenas 3 arquivos na raiz: `Iniciar Apresentador.exe`, `LEIA-ME.txt`, `config.json`
- HTMLs escondidos em `recursos/` (o leigo não encosta neles)
- `config.json` já vem pré-preenchido — não exige `cp config.example.json config.json` mental

**`server.py`:**
- `_asset_path(name)` — helper que busca `recursos/name` primeiro, fallback `APP_DIR/name`; `INDEX_PATH` e `ADMIN_PATH` usam isso. Mantém dev mode (arquivos em `src/`) funcionando sem mudar nada
- `_ip_lan()` — truque clássico de socket UDP (conecta em `8.8.8.8:80` sem enviar nada, lê `getsockname()`) pra descobrir IP da LAN sem DNS
- `main()`: banner redesenhado com alinhamento fixo em 68 colunas, mostra URL de rede quando disponível com comentário "(use esta URL no tablet do palestrante)"
- Onboarding: `abrir_path = "/admin" if not PALESTRANTES else "/"` — primeira execução leva direto pra configuração

**`scripts/build.bat`:**
- Auto-gera `assets/icon.ico` se faltar (chamando `python scripts/gerar_icone.py`)
- PyInstaller com `--icon`, `--specpath build`, `--distpath dist/tmp`
- Depois do compile, monta `dist/Apresentador vMix/` + `recursos/`, move o exe, copia HTMLs, ícone, LEIA-ME, config pré-preenchido
- Remove `dist/tmp` no final — só sobra a pasta final pronta pra copiar

**`installer/LEIA-ME.txt`:**
- ~90 linhas em ASCII puro (compatível com CMD/Notepad sem cedilha quebrada)
- Fluxo em 3 passos + seção de troubleshooting ("banner vermelho", "card vermelho", "slides não sincronizam") + lista de formatos aceitos + onde ficam os logs
- Linguagem direta, sem jargão técnico além do mínimo necessário

**`meta viewport` nos HTMLs:** `<meta name="viewport" content="width=device-width, initial-scale=1">` — elimina o único Error do lint do VS Code (antes deixava os nomes em vermelho no explorer) e garante rendering correto em tablet.

**Validação:**
- PyInstaller build concluiu em ~7.5s
- Exe portable (8.2 MB) sobe em `localhost:5001`, serve `/admin` (recursos/admin.html), `/` (recursos/index.html), `/admin/api/config` com o config.json da raiz
- Primeiro boot sem palestrantes abre direto o `/admin` no browser
- Pasta final 8.3 MB pronta pra copiar ou zipar

## v0.3.0 — 2026-04-19

**Resumo:** release "à prova de show ao vivo" — fecha as 10 rachaduras identificadas após v0.2.0. Coberto por 60 testes stdlib (24 novos).

**Fase 1 — Match ancorado (`match_filename`):**
- Antes: `s in title` batia com substrings (slide 1 ganhava quando era slide 10)
- Agora: `casefold()` + escolha do filename de maior comprimento em empate
- Usado por `compute_state` e `diagnosticar_palestrante`

**Fase 2 — Recovery automático:**
- `carregar_config`: trata `FileNotFoundError`, `json.JSONDecodeError` e `OSError` sem derrubar o server; faz backup em `config.bak.json` e sobe com `_config_default()`
- `rescan_pasta(guid) -> list[str]` pública — re-lê filesystem de um palestrante e atualiza `PALESTRANTES` sob `_cfg_lock`
- Handler `/img/<guid>/<arq>` chama `rescan_pasta` no miss; se ainda não achar, responde **HTTP 410 Gone** com JSON `{error: "arquivo_removido", detalhe: ...}`

**Fase 3 — Resiliência de rede:**
- `_LS_EXECUTOR` (ThreadPoolExecutor, 4 workers) isola `list_dir` — `future.result(timeout=3.0)` devolve `{items: [], timeout: true}` se UNC travar
- Nova rota `GET /admin/api/vmix_xml` proxifica o XML do vMix (útil quando admin corre num host sem acesso direto ao vMix)
- Admin frontend: `fetchVmixXml` agora é array `[direct, proxy]`, itera até dar certo
- Banner global fixo no admin quando `failStreak >= 3`, com contador `secs` desde offlineSince
- Banner equivalente no modo apresentador (`index.html`) quando `/state.ok === false` em 3 ticks
- Heartbeat no rodapé: `atualizado há X ms/s`, classes CSS `warn` (>2s) e `err` (>8s); tick independente de 250ms pra manter contador correndo

**Fase 4 — Observabilidade:**
- `_CLIENTES: dict[str, float]` + `_clientes_lock` — IP → timestamp do último `GET /state`
- `registrar_cliente(ip)` chamado em cada request de `/state`; GC automático após 5min de inatividade
- `clientes_ativos(janela_s=30)` retorna lista `[{ip, ultimo_hit_s}]` ordenada
- Rota `GET /admin/api/clientes` + chip `👤 N` no header do admin com tooltip listando IPs
- `setup_logging()` usa `RotatingFileHandler` em `logs/YYYY-MM-DD.log` (10MB, 5 backups); handler do servidor encaminha log via `logger.info`

**Fase 5 — Streaming:**
- `_send_file` usa `Path.stat().st_size` pra `Content-Length` e `shutil.copyfileobj(..., length=64*1024)` em vez de `read_bytes()`
- Trata `BrokenPipeError` e `ConnectionResetError` como normal (cliente desconectou mid-stream)

**Fase 6 — Grid de miniaturas + lightbox:**
- `listar_preview(pasta) -> {path, total, items: [{name, url}]}` — imagens ordenadas naturalmente; URLs apontam pro `/admin/api/preview/img`
- `preview_img_path(pasta, arq) -> Path` — resolve com `relative_to` pra bloquear path traversal; levanta `PermissionError` em caso de ataque ou tentativa de servir não-imagem
- 2 rotas novas no handler + silêncio de log pra `/admin/api/preview` (50+ requests por abertura do modal)
- Frontend: bloco `preview-grid` (CSS `grid auto-fill minmax(120px, 1fr)` + `aspect-ratio: 16/9 object-fit: cover`) alimentado por `renderPreview()`, disparado junto com `agendarTestar` (debounce 400 ms)
- Lightbox: overlay fullscreen com Esc-to-close, click no fundo também fecha

**Validação end-to-end real:**
- `/admin/api/vmix_xml` retornou HTTP 200 com 42850 bytes do XML do vMix
- `/admin/api/clientes` registrou e expôs 1 cliente ativo após GET `/state`
- `/admin/api/health` com match ancorado reportou `ok` para Wagner + Vinícius
- `/admin/api/preview` listou 50 imagens da pasta do Wagner em ordem natural
- `/admin/api/preview/img` serviu 370KB de uma miniatura real
- Path traversal (`..\..\etc\passwd`) → HTTP 404
- Arquivo inexistente em `/img/<guid>/...` → HTTP 410 (não mais 404 silencioso)
- `logs/2026-04-19.log` criado automaticamente no boot do server

## v0.2.0 — 2026-04-19

**Resumo:** release de robustez — config inválido não salva, cada card do dashboard mostra o estado real do palestrante, próximo slide não pula mais na ordem errada, e slides em JPG/JPEG/BMP/GIF/WEBP funcionam sem precisar renomear pra PNG. Coberto por 36 testes stdlib.

**Backend (`src/server.py`, +300 linhas):**
- `IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")` + helper `_is_image(p)`
- `_natural_key(s)` — regex `(\d+)` para quebrar em tokens texto/número e converter numéricos pra int
- `validar_config(cfg) -> list[str]` — checa tipos, campos obrigatórios, GUID duplicado case-insensitive, pasta no disco, presença de imagens aceitas. Retorna lista vazia = OK
- `salvar_config(cfg)` passa por `validar_config` antes de escrever — levanta `ValueError("config_invalida", [erros])` quando inválido, mantendo `config.json` em disco inalterado
- Helpers `_input_by_num`, `_input_by_key`, `_find_palestrante_em` extraídos do `compute_state` para uso pelo diagnóstico
- `diagnosticar_palestrante(guid, nome, pasta, xml_root) -> dict` — status estruturado + detalhe legível + metadados (num_input, shorttitle, totais); trata caso `pasta=""` como `sem_pasta` (usado pelo `/validate`)
- `diagnosticar_todos() -> list[dict]` — roda o diagnóstico para todos os palestrantes do config; se vMix offline, devolve lista com status `vmix_offline` para cada
- Rotas novas: `GET /admin/api/health`, `GET /admin/api/validate?guid=&pasta=&nome=`
- `_handle_admin_post` trata `ValueError("config_invalida", erros)` devolvendo `{ok:false, error:"config_invalida", erros:[...]}` status 400

**Frontend (`src/admin.html`):**
- `HEALTH_BY_GUID` — dicionário global alimentado pelo `/admin/api/health` a cada tick; `pollTick` faz fetch em paralelo com XML do vMix via `Promise.all`
- `STATUS_META` — mapa `{status → {icone, label}}` pra renderização uniforme
- `renderStatusRow(guid)` — bloco de badge + detalhe acima do "Input agora"
- `testarPalestrante()` + `agendarTestar()` (debounce 400 ms) — chama `/admin/api/validate`, renderiza check-list colorida no bloco `#modal-diag`
- `apiPost` agora preserva `err.detalhes` vindo do campo `erros` do servidor; `salvarPalestrante` renderiza os erros estruturados dentro do modal em vez de `alert()`
- Todos os `pngs` → `imagens` no template e no JS (renderTree, matchFolderByTokens, inline use button, dataset attrs)
- CSS novo: `.status-row`, `.status-badge.status-{ok,guid_orfao,pasta_inacessivel,sem_imagens,filename_mismatch,vmix_offline,sem_pasta}`, `.modal-diagnostic`, `.diag-check.{ok,fail,warn}`

**Testes (`tests/`, stdlib `unittest`, 36 casos):**
- `tests/conftest_helpers.py` — `make_images(path, nomes)` cria arquivos vazios; `fake_vmix_xml(inputs, active, overlays_global, preset)` monta XML minimal
- `tests/test_filesystem.py` — IMAGE_EXTS, formatos mistos, natural sort com zero-pad e sem, case-insensitive, `list_dir` com campo `imagens`
- `tests/test_config.py` — validação feliz e de erro (todas as regras), `salvar_config` não sobrescreve em caso de erro
- `tests/test_vmix.py` — `compute_state` com Program direto/overlay interno/overlay global; `diagnosticar_palestrante` em 6 cenários; `diagnosticar_todos` mescla palestrantes bons e órfãos

**Validação end-to-end contra vMix real do usuário:**
- `/admin/api/health` retornou `ok` para Wagner + Vinícius com detalhe `"arquivo atual: slide 07.png (#7 de 50)"`
- `/admin/api/validate` retornou `guid_orfao` para GUID inventado e `pasta_inacessivel` para `Z:\fake`
- `POST /admin/api/config` com dados inválidos retornou `HTTP 400` + `erros` listando todos os problemas (nome vazio, pasta vazia, pasta inexistente, GUID duplicado)
- `/admin/api/ls` listou pasta com 4 imagens mistas (.jpg, .jpeg, .webp, .bmp) retornando `imagens: 4`

## v0.1.0 — 2026-04-19

**Resumo:** primeira release marcando o MVP completo — modo apresentador + dashboard administrativo integrados, ambos alimentados por polling ao vivo do vMix.

**Backend (`src/server.py`, ~460 linhas, stdlib pura):**
- `compute_state()` detecta palestrante em 3 prioridades: Program direto → overlay interno de input composto → overlay global (Overlay1–16)
- `salvar_config()` grava `config.json` atomicamente (tmp + rename) e recarrega `PALESTRANTES` em memória com lock
- `get_preset_dir()` extrai pasta pai do `.vmixZip` do XML do vMix
- `get_roots()` agrega raízes: `config.roots` + preset + avô + pasta do app
- `list_drives()` enumera drives Windows acessíveis (C:, D:, ...)
- `list_dir()` lista subpastas com contagem de PNGs (sem restrição de raiz — app local)
- Rotas novas: `GET /admin`, `GET /admin/api/config`, `POST /admin/api/config`, `GET /admin/api/roots`, `GET /admin/api/ls`

**Frontend admin (`src/admin.html`, ~1000 linhas vanilla JS):**
- Boot carrega `config.json` via `/admin/api/config` e popula o painel
- Polling `http://<vmix>:8088/api` a cada 500 ms direto do browser (CORS do vMix é permissivo)
- Parse XML → extrai automaticamente Photos + Colour com overlay[Photos] + preset
- Re-render ao vivo: slide atual, filename, barra de progresso, destaque do palestrante ativo
- Modal adicionar/editar: auto-sugere nome (shortTitle), auto-match de pasta por tokens
- File browser: drives + atalhos detectados + tree navegável + "✓ usar esta pasta" + 🏠 início
- Edição inline de nome via lápis, persistência automática via POST
- Box padronizado de número de input com padding de 2 dígitos (`05`, `07`, `89`)

**Build/distro:**
- `scripts\build.bat` copia `admin.html` junto do `apresentador.exe` e `index.html`
- `config.example.json` atualizado com campo `roots` e `palestrantes` vazio

**Padrões identificados no vMix real do usuário (Jornada Full Face II):**
- 6 inputs `Photos` (slideshows por palestrante)
- 6 inputs `Colour` que envelopam Photos em `overlay[1]` (blanks camera+slides)
- Nomenclatura `LETRA + espaços + descrição` nos blanks
