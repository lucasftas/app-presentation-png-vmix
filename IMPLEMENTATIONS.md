# Implementations

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
