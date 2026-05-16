<div align="center">

# 🎥 Apresentador vMix

### Presenter View pra palestrantes em lives com vMix

**O palestrante vê o slide atual + próximo no tablet, sincronizado automaticamente.**
O operador controla tudo do seu PC. Sem mexer no tablet do palestrante durante o show.

[![Release](https://img.shields.io/github/v/release/lucasftas/app-presentation-png-vmix?style=flat-square&color=2ea043)](https://github.com/lucasftas/app-presentation-png-vmix/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3b82f6.svg?style=flat-square)](https://www.python.org/)
[![vMix 29](https://img.shields.io/badge/vMix-29%2B-f2b705.svg?style=flat-square)](https://www.vmix.com/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4.svg?style=flat-square)](#)

![preview do icone](assets/icon.png)

</div>

---

## 🤔 Por que existe?

Em lives onde os slides são projetados **pelo vMix** (não pelo PowerPoint direto), o *Presenter View* nativo do PowerPoint simplesmente **não funciona**. O palestrante fica sem saber o que vem a seguir, dependendo do operador ou de um monitor de confidence que só mostra o slide atual.

Este app preenche essa lacuna:

- 🔌 Conecta na **API HTTP do vMix** (rede local)
- 🔍 Detecta automaticamente qual palestrante está **ao vivo** — mesmo quando o slide aparece como overlay de um input composto com câmera
- 🖼️ Exibe uma página web com **slide atual + próximo** (e mais metadados)
- 📱 Funciona em qualquer tablet/notebook na mesa do palestrante

---

## ✨ Features

### 🎬 Pro palestrante

- **Modo apresentador** estilo PowerPoint com slide atual + próximo + barra de progresso
- **Controle remoto embutido** — menu hambúrguer pra avançar/voltar/ir direto num slide, sem precisar do vMix
- **Modo kiosk** (tela cheia limpa, sem cursor) em monitor dedicado
- Banner **"Fulano entrando em breve"** quando você está em Preview do vMix
- **"FIM"** destacado quando o slideshow acaba
- **Suporte a input List (VideoList)** — playlist mista de slides + vídeos; cada vídeo aparece como um frame com tag **"VÍDEO"** e duração
- Ajuste de proporção atual/próximo por slider

### ⚙️ Pro operador

- **Dashboard web completo** pra gerenciar palestrantes sem editar JSON
- **Grid de miniaturas** ao adicionar palestrante — confirma visualmente se a pasta é a correta
- **Detecção automática de padrões no vMix** — sugere pares blank↔slideshow
- **File browser estilo explorer** com drives, atalhos detectados, match automático de pasta por nome
- Badges de saúde por palestrante: `✓ OK` / `⚠ GUID órfão` / `✕ Pasta inacessível` / `⚠ Filename não bate`
- **Proximidade dos clientes conectados** — chip mostra quantos tablets estão assistindo agora
- **"Gerar frames dos vídeos"** — pré-extrai (ffmpeg) um frame de cada vídeo de um input List, com barra de progresso

### 🖥️ System tray nativo Windows

- Ícone na bandeja com **controle completo do vMix** por palestrante (avançar/voltar/reset)
- **Notificações** em eventos críticos: vMix offline, palestrante no ar, servidor parou
- **"Projetar em monitor"** — abre modo apresentador em tela cheia no monitor escolhido (inspirado no OBS "Fullscreen Projector")
- Editar IP do vMix direto do tray via dialog
- Copiar URL do palestrante pra clipboard com 1 clique
- Liberar porta no firewall do Windows com 1 clique
- Ícone troca pra ⚠️ quando vMix está offline >10s

### 🛡️ À prova de show ao vivo

- **Port fallback** — se 5000 estiver ocupada, tenta 5001, 5002...
- **Single-instance guard** — duplo duplo-clique não abre 2 cópias conflitantes
- **Health check interno** — detecta se o próprio servidor HTTP morreu e notifica
- **Recovery de config corrompido** — backup automático, app sobe sempre
- **Timeout em share de rede (UNC) lento** — share caído não trava o dashboard
- **File watcher do config** — editar `config.json` externamente recarrega automaticamente
- **Logs com rotação** em `logs/YYYY-MM-DD.log`
- **Match ancorado de filename** — resolve ambiguidade `slide 1.png` vs `slide 10.png`

---

## 🚀 Quick start

### 1. Baixe o portable

[**⬇️ Baixar `Iniciar Apresentador.exe` — release mais recente**](https://github.com/lucasftas/app-presentation-png-vmix/releases/latest)

**Exe único** (~95 MB) — app + ffmpeg embutidos. Sem instalação, sem dependências: baixe e duplo-clique.

Ou veja [todas as releases](https://github.com/lucasftas/app-presentation-png-vmix/releases).

### 2. Duplo-clique no `Iniciar Apresentador.exe`

- Ícone aparece na **bandeja do Windows** perto do relógio
- Sem janela preta, sem poluição visual
- Single-instance: não rola abrir 2 cópias por engano

### 3. Clique no ícone → Dashboard abre no browser

- Adicione palestrantes: escolha o input `Photos` do vMix, navegue até a pasta dos slides, confirme pelo **grid de miniaturas**, salve
- Rede? O banner de boot mostra `http://192.168.x.x:5000/` — abra essa URL no browser do tablet do palestrante
- Pronto. Quando você passar slide no vMix, o tablet sincroniza em **≤500 ms**

---

## 🎯 Pra quem serve

- **Produtores de live** (eventos, cursos, pitches) que passam slides pelo vMix
- **Palestrantes remotos** que só têm um tablet na mesa e precisam ver o próximo slide
- **Igrejas / lives de culto** com 2-3 pregadores e apresentações separadas
- **Workshops online** com múltiplos palestrantes durante o dia

Funciona especialmente bem quando:
- Você tem **múltiplos palestrantes no mesmo evento** (a app detecta qual está ao vivo)
- Os slides entram como **blank composto** (input Colour com Photos em overlay) — padrão comum em lives com câmera+slide

---

## 🏗️ Como funciona (arquitetura em 3 linhas)

```
                          [ config.json ]
                                │
┌──────────────┐       ┌────────┴────────┐       ┌──────────────┐
│ vMix (8088)  │◀──────│ Apresentador    │──────▶│ Tablet web   │
│ XML API      │       │ server.py       │       │ :5000/       │
│ (polling     │       │ + tray          │       │ (palestrante)│
│  500ms)      │       │ + projetor      │       └──────────────┘
└──────────────┘       └────────┬────────┘
                                │
                       ┌────────┴────────┐
                       │ Dashboard /admin│
                       │ (operador)      │
                       └─────────────────┘
```

**Detecção em 3 prioridades:**

1. Input diretamente em Program é um palestrante? → usa
2. Input em Program é Colour com Photos em overlay? → usa (blanks composto)
3. Alguma das 16 overlays globais aponta pra Photos? → usa

O filename atual (`title` do XML do vMix) é matched contra os arquivos da pasta com sort natural.

---

## 🛠️ Stack

- **Backend:** Python 3.11+ stdlib pura (`http.server`, `urllib`, `xml.etree`, `ctypes`, `tkinter`, `concurrent.futures`) + `pystray` + `Pillow`
- **Frontend:** HTML/CSS/JS vanilla (sem build step)
- **Vídeo:** `ffmpeg` + `ffprobe` (frames e duração dos vídeos de inputs List) — embutidos no exe
- **Distribuição:** PyInstaller `--onefile` + `--noconsole` → exe único (~95 MB, ffmpeg incluído)
- **Plataforma:** Windows 10/11 (tray icon + `ctypes.windll`)

**139 testes unittest** cobrindo config, filesystem, vMix parsing (Photos e List), match ancorado, frames de vídeo, resiliência, projetores e tray.

---

## 🖼️ Screenshots

<div align="center">

### Modo apresentador (o que o palestrante vê)
![hero](assets/icon_alert.png)

*Slide atual (verde) menor à esquerda, próximo (amarelo) maior à direita, barra de progresso azul, nome do palestrante e contador no rodapé.*

</div>

---

## 📦 Releases

- 🟢 **v1.1.0** — Suporte a input List (VideoList): playlist mista slides + vídeos, frames de vídeo via ffmpeg, exe único
- **v1.0.0** — Primeira release pública (MIT, open-source)
- **v0.8.0** — "Projetar Prévia" estilo OBS: abre modo apresentador em tela cheia limpa no monitor escolhido
- **v0.7.0** — À prova de falhas silenciosas: port fallback, single-instance, health check, file watcher
- **v0.6.0** — Tray icon nativo com menu completo + notificações
- **v0.5.0** — Layout escalado, proporção sincronizada entre tablets, preview palestrante
- **v0.4.0** — Pacote portable amigável pra leigo
- **v0.3.0** — À prova de show ao vivo: match ancorado, recovery, grid de miniaturas

[Veja o CHANGELOG completo](CHANGELOG.md) · [Todas as releases](https://github.com/lucasftas/app-presentation-png-vmix/releases)

---

## 🧪 Desenvolvimento

```bash
# Clone
git clone https://github.com/lucasftas/app-presentation-png-vmix.git
cd app-presentation-png-vmix

# Rodar direto com Python
cp config.example.json src/config.json
python src/server.py

# Testes (stdlib puro, sem pytest)
python -m unittest discover tests/ -v

# Build do exe único (requer ffmpeg/ffprobe no PATH — embutidos no exe)
pip install pyinstaller pystray Pillow
scripts\build.bat
# Saída: dist/Iniciar Apresentador.exe
```

---

## 📡 API REST (integrações)

| Endpoint | Método | Descrição |
|---|---|---|
| `/` | GET | Modo apresentador (HTML) |
| `/admin` | GET | Dashboard (HTML) |
| `/state` | GET | Estado atual do palestrante ao vivo (JSON) |
| `/admin/api/config` | GET/POST | Config atual + persistência |
| `/admin/api/health` | GET | Diagnóstico por palestrante |
| `/admin/api/vmix_control` | POST | `{action: "next\|prev\|goto\|reset", guid, index?}` |
| `/admin/api/monitors` | GET | Monitores detectados no Windows |
| `/admin/api/projetor_abrir` | POST | Abre projetor em tela cheia num monitor |
| `/admin/api/preview?pasta=` | GET | Lista imagens da pasta (miniaturas do modal) |

Mais 8 endpoints — veja o [código do server](src/server.py) ou rode `grep "sub ==" src/server.py`.

---

## 🤝 Contribuindo

Issues e PRs bem-vindos! Em especial:

- 📸 **Screenshots reais de uso** pra colocar no README
- 🐛 Relatos de bugs em produção com vMix
- 🌍 Testes em outras versões do vMix (27, 28, 29, 30+)
- 💡 Ideias de integrações (OBS overlay, Companion, Stream Deck)

Abra uma [issue](https://github.com/lucasftas/app-presentation-png-vmix/issues) ou mande um PR.

---

## 📜 Licença

MIT — [veja LICENSE](LICENSE). Pode usar livremente em eventos comerciais.

---

<div align="center">

**Gostou? ⭐ dá uma estrelinha aí — ajuda a descobrir que tem gente usando.**

Feito pra funcionar em live, testado em live, publicado em live.

</div>
