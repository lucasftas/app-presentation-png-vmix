# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento segue [Semantic Versioning](https://semver.org/).

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
