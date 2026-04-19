# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento segue [Semantic Versioning](https://semver.org/).

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
