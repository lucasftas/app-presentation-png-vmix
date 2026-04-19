# app-presentation-png-vmix

Aplicação Windows que se conecta à API HTTP do vMix e serve um **modo apresentador web** (estilo PowerPoint Presenter View) com o **slide atual + próximo** do palestrante ativo, mais um **dashboard administrativo** que descobre e configura palestrantes automaticamente a partir do vMix.

**Status:** ✅ v0.1.0 — funcional

---

## Proposta

Em lives onde os slides são projetados pelo vMix (PNGs dentro de inputs `Photos`/`ImageList`), o *Presenter View* nativo do PowerPoint não funciona — o palestrante não tem como ver o que vem a seguir. Esta app preenche essa lacuna: faz polling da API do vMix, identifica qual palestrante está ao vivo (inclusive quando o slide é layer de uma composição com câmera ou está em overlay global), cruza com os PNGs do filesystem e serve uma página web para tablet/notebook na mesa do palestrante.

## Componentes

| URL | Finalidade | Quem usa |
|---|---|---|
| `http://<host>:5000/` | Modo apresentador (slide atual + próximo) | Palestrante — tablet/notebook |
| `http://<host>:5000/admin` | Dashboard de configuração | Operador vMix |
| `http://<host>:5000/state` | JSON com estado atual (integrações) | — |
| `http://<host>:5000/admin/api/*` | API REST do dashboard | Dashboard (interno) |

## Fluxo do operador

1. Copia a pasta da aplicação pra máquina escolhida (a do vMix ou outra na rede local)
2. Dá duplo-clique em `apresentador.exe` → abre console + navegador
3. Vai em `http://localhost:5000/admin` — vê **todos os inputs `Photos` do vMix atual** e **sugestões de pares** quando há Colour envelopando Photos (blanks camera+slides)
4. Adiciona palestrantes com 1 clique: o dashboard auto-sugere o nome (do `shortTitle` do input) e faz auto-match de pasta pelos tokens do nome dentro dos drives/atalhos detectados
5. Palestrante acessa `http://<ip-da-maquina>:5000/` pelo tablet — sincroniza em até 500 ms

## Detecção do palestrante em 3 prioridades

O vMix raramente joga o `Photos` direto no Program. O fluxo típico é: **Colour composto (blank) com Photos em overlay → o blank vai pra Overlay global por cima da câmera**. A detecção respeita essa ordem:

1. **Program direto** — input em Program é um Photos registrado? Usa.
2. **Overlay interno** — Program é Colour composto? Varre `<overlay>` procurando um Photos registrado.
3. **Overlay global** — alguma das 16 overlays globais (`<overlays><overlay number="N">key</overlay>`) aponta pra Photos ou Colour+Photos? Usa.

Cruzamento com o filesystem: o `title` do vMix contém o filename atual (ex: `"SLIDE 001 - Wagner - slide 26.png"`) — match por substring contra os PNGs da pasta.

## Dashboard `/admin`

Interface web dinâmica que se atualiza a cada 500 ms com o estado do vMix:

- **Cards dos palestrantes configurados** com slide atual, filename, barra de progresso e destaque vermelho quando ao vivo
- **Sugestões automáticas** de pares blank ↔ slideshow detectados
- **Lista de inputs** agrupada por tipo (Photos / Blanks compostos / Todos)
- **Modal adicionar/editar** com:
  - Auto-preenchimento do nome a partir do `shortTitle` do input
  - **File browser estilo explorer**: drives do Windows + atalhos detectados (preset do vMix + pasta pai) + navegação livre com breadcrumb + botão "✓ usar esta pasta"
  - Auto-match de pasta por tokens do nome do slideshow (ex: shortTitle "003 - Vinícius" → sugere `…\Slides\003 - Vinícius`)
- **Edição inline** do nome via ✎ no card
- **Persistência** no `config.json` com hot-reload em memória (sem restart do servidor)

Números de input exibidos com box padronizado e padding de 2 dígitos (`05`, `07`, `89`) — todos lidos ao vivo do vMix, então se você reordenar/renomear inputs lá, o dashboard atualiza sozinho. O **GUID** é a chave estável persistida no config.

## Stack

- **Linguagem:** Python 3.11+ (**stdlib pura** — zero dependências de runtime)
- **Servidor HTTP:** `http.server` + `socketserver.ThreadingMixIn`
- **Cliente vMix:** `urllib.request` + `xml.etree.ElementTree`
- **Frontend:** HTML/CSS/JS vanilla (sem build step, sem framework)
- **Empacotamento:** PyInstaller `--onefile` → `apresentador.exe` (~8 MB)
- **Plataforma alvo:** Windows 10/11 com vMix 29+ acessível na rede (porta 8088)

**Por que stdlib pura:** zero `pip install` na máquina do operador, .exe pequeno, menos superfície de falha em ambiente de live.

## Como rodar

### Desenvolvimento

```bash
cd src
python server.py
```

Requer `config.json` em `src/` (copie `config.example.json` pra `src/config.json`).

### Produção (build do .exe)

```bash
pip install pyinstaller
scripts\build.bat
```

Gera `dist/apresentador.exe` + copia `index.html`, `admin.html` e `config.example.json` ao lado. Distribuir a pasta `dist/` inteira pra máquina do evento.

## Configuração — `config.json`

```json
{
  "vmix": {
    "host": "localhost",
    "port": 8088
  },
  "server_port": 5000,
  "roots": [
    "\\\\vmix\\4TB\\Live Jornada Full Face\\Slides",
    "D:\\Slides"
  ],
  "palestrantes": []
}
```

- **`vmix.host`**: IP/hostname da máquina com vMix
- **`roots`**: pastas extras para aparecer como atalhos no file browser do dashboard. Opcional — o preset do vMix e sua pasta pai já viram atalhos automaticamente
- **`palestrantes`**: começa vazio. O dashboard preenche conforme você adiciona

Cada palestrante fica com:

```json
{
  "nome": "Wagner",
  "guid": "51f89804-b46f-4716-8914-4f692c63c38c",
  "pasta": "D:\\Slides\\001 - Wagner"
}
```

Pastas podem ser absolutas ou relativas ao `config.json`. Aceita UNC (`\\servidor\share\...`).

## API REST (`/admin/api`)

| Endpoint | Método | Descrição |
|---|---|---|
| `/admin/api/config` | GET | Retorna `config.json` atual |
| `/admin/api/config` | POST | Salva config + recarrega em memória |
| `/admin/api/roots` | GET | Raízes detectadas (preset vMix + pasta pai + pasta do app + `config.roots`) |
| `/admin/api/ls` | GET | Sem `?path` → retorna drives + atalhos; com `?path=...` → lista subpastas com contagem de PNGs |

## Arquitetura de pastas

```
app-presentation-png-vmix/
├── src/
│   ├── server.py          # Servidor HTTP + cliente vMix + API admin (~460 linhas)
│   ├── index.html         # Modo apresentador (palestrante)
│   └── admin.html         # Dashboard (operador)
├── scripts/
│   └── build.bat          # PyInstaller --onefile
├── config.example.json    # Template de configuração
├── CHANGELOG.md
├── IMPLEMENTATIONS.md
├── OPERATIONS.md
├── CLAUDE.md
└── README.md
```

## Fora de escopo (v0.1.0)

- **Controle ativo do vMix** (Next/Prev slide pela interface web) — a app é monitor passivo
- **Multi-instância de vMix** (vários PCs com vMix no mesmo painel) — previsto em versões futuras
- **Scan automático de rede** pra descobrir vMix — previsto
- **Suporte a inputs PowerPoint / VirtualSet / vídeos** como fonte de slides (apenas `Photos`/`ImageList` por ora)
- **Anotações, timer, chat** — não faz parte da proposta
- **Customização de tema** via config

## Referências

- [vMix Web API — documentação oficial](https://www.vmix.com/help27/index.htm?DeveloperAPI.html)
- Inspiração de UX: *Presenter View* do PowerPoint / Keynote

---

**Projeto privado — uso interno.**
