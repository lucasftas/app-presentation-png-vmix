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
