# CLAUDE.md — app-presentation-png-vmix

Instruções para assistentes de IA trabalhando neste repositório.

## Visão geral

Aplicação Windows que serve um modo apresentador web (estilo PowerPoint Presenter View) sincronizado com o vMix via API HTTP. Monitora o input em Program (inclusive quando o palestrante está como overlay/layer de um input composto) e exibe slide atual + próximo para o palestrante consultar no tablet/notebook da mesa.

- **Plataforma alvo:** Windows 10/11 com vMix rodando na mesma rede
- **Linguagem:** Python 3.11+. O **core do servidor (`server.py`) é stdlib pura**; o tray (`tray.py`) depende de **pystray + Pillow** (runtime) e usa `tkinter` (stdlib) para diálogos. Sem essas libs o app cai em modo headless (sem ícone na bandeja).
- **Frontend:** HTML/CSS/JS vanilla (sem build step)
- **Empacotamento:** PyInstaller `--onedir` → pasta `Iniciar Apresentador\` (exe + `_internal\`), distribuída via instalador Inno Setup (`Apresentador vMix Setup.exe`). **Não usar `--onefile`** — extrai ~95 MB em `%TEMP%\_MEIxxxx` a cada boot e o antivírus/temp travava o app em produção.
- **Config:** `config.json` externo (IP do vMix + lista de palestrantes com GUID/pasta)

## Regras do projeto

- **Deps de runtime mínimas** — `requirements.txt` lista o runtime do tray (pystray, Pillow) e o build (pyinstaller) em blocos separados. O servidor HTTP em si não depende de libs externas.
- **Sem framework web** — usar `http.server` + `ThreadingMixIn`. Simplicidade acima de tudo.
- **Pastas dos palestrantes**: caminhos no `config.json` podem ser absolutos ou relativos ao diretório do `config.json` (ou do `.exe`).
- **URLs das imagens** expostas por GUID (`/img/<guid>/<arquivo>`), não por nome de pasta — evita expor estrutura de filesystem.
- **Polling do vMix**: 500 ms. Timeouts: 3 s na chamada HTTP ao vMix (`fetch_vmix_xml`/`vmix_control`), 3 s nas operações de filesystem (`list_dir`/`rescan_pasta`/`_is_file_timeout`, isoladas em `_LS_EXECUTOR` contra UNC lento), 30 s no socket do handler (`Handler.timeout`).
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
- `--onedir` — pasta `Iniciar Apresentador\` com o exe + `_internal\` (dll, ffmpeg/ffprobe, HTML, ícones), ~95 MB. **Não** `--onefile` (extração em `%TEMP%` quebrava em produção).
- `--name "Iniciar Apresentador"` — nome do executável
- `--noconsole` — sem janela preta; o app roda no tray e os logs vão pra `logs\YYYY-MM-DD.log` ao lado do exe (rotação 10 MB × 5).
- `--add-binary ffmpeg/ffprobe` — embutidos pra gerar frames de vídeo do input List sem ffmpeg instalado.

Empacotamento final: `installer\build-installer.bat` roda o build e compila `installer\apresentador.iss` (Inno Setup) → `dist\Apresentador vMix Setup.exe`, que instala em `%LocalAppData%\Apresentador vMix` sem admin.

## Gatilho "filé"

Ver CLAUDE.md global do usuário (`~/.claude/CLAUDE.md`). Quando o usuário disser **"filé"**, executar o fluxo automático: commit → push → release → CHANGELOG/IMPLEMENTATIONS/OPERATIONS.

## Tipos de palestrante (`config.json`)

Cada palestrante tem um campo `tipo` (opcional, default `photos`):

- **`photos`**: input `Photos` do vMix. Slides vêm de uma `pasta` no disco; o app cruza o `title` do vMix com os arquivos.
- **`list`**: input `List` (`VideoList`) do vMix. A playlist (mistura de slides PNG/JPG + vídeos MP4/MOV) vem do **próprio XML do vMix** — não precisa de `pasta`. Itens de vídeo viram um card "VÍDEO" no apresentador; itens de imagem são servidos via `/list-img/<guid>/<indice>`.

```json
{ "nome": "Pitch", "guid": "05c4d1a0-...", "tipo": "list" }
```

## Dicas para assistentes

- **API do vMix** retorna XML. Inputs tipo `Photos`/`ImageList` têm `selectedIndex` e `title` (com nome do arquivo atual no título). Inputs compostos têm `<overlay key="...">` apontando para outros inputs.
- **Input List (`VideoList`)**: expõe a playlist inteira em `<list><item>caminho</item></list>` (cada `<item>` é um path absoluto). O item atual tem `selected="true"`; fallback é o atributo `selectedIndex` (vMix usa 1-based pra List). `duration`/`position` (ms) só valem pro item atual. Parsing em `_parse_list_input`, estado em `_estado_lista`. next/prev de List não usam `NextPicture` — traduzem pra `SelectIndex` via `vmix_list_control`.
- **Detecção do palestrante ativo**: 1) se o input em Program tem `key` nos GUIDs configurados → é ele. 2) senão, varrer as `<overlay>` do input em Program procurando um `key` que seja um palestrante.
- **Cruzamento com filesystem**: o `title` do vMix contém o nome do arquivo (ex: `"SLIDE 001 - Wagner - slide 26.png"`). Fazer match por substring contra a lista ordenada de PNGs da pasta.
- **UNC paths no Windows**: `cd /d` não suporta UNC no CMD; usar `pushd` quando o `.exe` está em share de rede.
