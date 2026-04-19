# Operations Log

## 2026-04-17

- [x] Captura inicial da ideia (gatilho "bora") — entrevista + README.md alpha
- [x] Estrutura base do repositório: `src/`, `scripts/`, `tests/`, docs (CLAUDE/CHANGELOG/IMPLEMENTATIONS/OPERATIONS), `.gitignore`, `requirements.txt`
- [x] Primeira versão do `server.py` generalizada (config externa via JSON, sem GUIDs hardcoded)
- [x] Frontend `index.html` com layout 38/62, 16:9, bordas vermelho/amarelo, progresso
- [x] Script de build `scripts\build.bat` para gerar `.exe` standalone via PyInstaller
- [x] `config.example.json` com template para o operador copiar e editar
- [x] Criação do repositório privado no GitHub (`app-presentation-png-vmix`)
- [x] Primeiro commit e push para `main`

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
