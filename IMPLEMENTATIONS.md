# Implementations

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
