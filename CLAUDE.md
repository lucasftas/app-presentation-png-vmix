# CLAUDE.md — app-presentation-png-vmix

Instruções para assistentes de IA trabalhando neste repositório.

## Visão geral

Aplicação Windows que serve um modo apresentador web (estilo PowerPoint Presenter View) sincronizado com o vMix via API HTTP. Monitora o input em Program (inclusive quando o palestrante está como overlay/layer de um input composto) e exibe slide atual + próximo para o palestrante consultar no tablet/notebook da mesa.

- **Plataforma alvo:** Windows 10/11 com vMix rodando na mesma rede
- **Linguagem:** Python 3.11+ (**stdlib pura** — nenhuma dependência de runtime)
- **Frontend:** HTML/CSS/JS vanilla (sem build step)
- **Empacotamento:** PyInstaller `--onefile` → `apresentador.exe`
- **Config:** `config.json` externo (IP do vMix + lista de palestrantes com GUID/pasta)

## Regras do projeto

- **Sem dependências de runtime** — manter `requirements.txt` vazio de runtime. Dependências de build (PyInstaller) em bloco separado.
- **Sem framework web** — usar `http.server` + `ThreadingMixIn`. Simplicidade acima de tudo.
- **Pastas dos palestrantes**: caminhos no `config.json` podem ser absolutos ou relativos ao diretório do `config.json` (ou do `.exe`).
- **URLs das imagens** expostas por GUID (`/img/<guid>/<arquivo>`), não por nome de pasta — evita expor estrutura de filesystem.
- **Polling do vMix**: 500 ms. Timeout de 3 s na chamada HTTP.
- **Logs**: silenciar logs do `/state` (ruído no console); manter demais.

## Padrão de commits

- Português + prefixo convencional: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
- Mensagens curtas e focadas no "porquê"
- Co-author do Claude:
  ```
  Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
  ```

## Como rodar

### Modo desenvolvimento (com Python instalado)

```bash
cd src
python server.py
```

Requer `config.json` na mesma pasta do `server.py` (ou copie `config.example.json` → `config.json` e edite).

### Modo produção (build + distribuir)

```bash
scripts\build.bat
```

Gera `dist\apresentador.exe` + copia `index.html` e `config.example.json` ao lado. Distribuir a pasta `dist\` inteira para a máquina do evento.

## Estrutura do projeto

```
app-presentation-png-vmix/
├── src/
│   ├── server.py          # Servidor HTTP + cliente vMix API
│   └── index.html         # Frontend do modo apresentador
├── scripts/
│   └── build.bat          # Compila .exe com PyInstaller
├── tests/                 # (reservado para testes)
├── config.example.json    # Template de configuração
├── requirements.txt       # Só pyinstaller para build
├── README.md              # Proposta e docs do projeto
├── CHANGELOG.md           # Histórico de versões (Keep a Changelog)
├── IMPLEMENTATIONS.md     # Log de implementações por release
├── OPERATIONS.md          # Log de operações/sessões
└── CLAUDE.md              # Este arquivo
```

## Build

Pré-requisito: `pip install pyinstaller`

```bash
scripts\build.bat
```

Flags principais:
- `--onefile` — um único .exe portável (~8 MB)
- `--name apresentador` — nome do executável
- Manter console visível (sem `--noconsole`) — útil pra logs/troubleshoot durante live

## Gatilho "filé"

Ver CLAUDE.md global do usuário (`~/.claude/CLAUDE.md`). Quando o usuário disser **"filé"**, executar o fluxo automático: commit → push → release → CHANGELOG/IMPLEMENTATIONS/OPERATIONS.

## Dicas para assistentes

- **API do vMix** retorna XML. Inputs tipo `Photos`/`ImageList` têm `selectedIndex` e `title` (com nome do arquivo atual no título). Inputs compostos têm `<overlay key="...">` apontando para outros inputs.
- **Detecção do palestrante ativo**: 1) se o input em Program tem `key` nos GUIDs configurados → é ele. 2) senão, varrer as `<overlay>` do input em Program procurando um `key` que seja um palestrante.
- **Cruzamento com filesystem**: o `title` do vMix contém o nome do arquivo (ex: `"SLIDE 001 - Wagner - slide 26.png"`). Fazer match por substring contra a lista ordenada de PNGs da pasta.
- **UNC paths no Windows**: `cd /d` não suporta UNC no CMD; usar `pushd` quando o `.exe` está em share de rede.
