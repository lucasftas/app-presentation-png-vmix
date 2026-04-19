# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento segue [Semantic Versioning](https://semver.org/).

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
