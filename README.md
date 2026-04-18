# app-presentation-png-vmix

Aplicação Windows que se conecta à API HTTP do vMix e serve um **modo apresentador web** (estilo PowerPoint Presenter View) com o **slide atual + próximo slide** do palestrante ativo no Program.

**Status:** 🚧 Alpha — ideia em captura

---

## Proposta / Visão

Um serviço leve, portátil e sem instalação que resolve a ausência de *Presenter View* em transmissões ao vivo onde os slides são exibidos pelo vMix (e não pelo PowerPoint diretamente). O aplicativo faz polling na API do vMix, identifica o palestrante ativo (inclusive quando o slide aparece como overlay/layer de um input composto com câmera) e monta uma página web com o slide em exibição e o próximo, de forma que o palestrante tenha a mesma referência visual que teria num setup PowerPoint tradicional.

## Problema que resolve

Em lives, slides são projetados via vMix como PNGs dentro de inputs tipo `Photos`/`ImageList`. Nesse cenário, o *Presenter View* nativo do PowerPoint não funciona — o palestrante não tem como ver o que vem a seguir sem depender do operador ou de um monitor de confidence que só mostra o slide atual. A app preenche essa lacuna extraindo o estado do vMix em tempo real e servindo uma tela de apresentador adequada para tablet/notebook na mesa do palestrante.

## Usuário-alvo

**Operador/diretor de vMix** responsável pela transmissão. Ele:
- Configura os palestrantes do evento (GUIDs dos inputs + pastas de slides)
- Abre o aplicativo na máquina que tem acesso ao vMix (mesma ou outra na rede local)
- Disponibiliza o link `http://ip:5000/` para o palestrante acessar pelo tablet

## Fluxo principal

1. Operador copia a pasta da aplicação para a máquina escolhida (vMix ou outra na rede)
2. Edita `config.json` com o IP do vMix e os palestrantes do evento (nome, GUID, pasta de slides)
3. Dá duplo-clique em `apresentador.exe`
4. A aplicação:
   - Abre uma janela de console com o log
   - Inicia um servidor HTTP local na porta `5000`
   - Abre o navegador padrão em `http://localhost:5000/`
5. Palestrante acessa `http://<ip-da-maquina>:5000/` pelo tablet na mesa
6. Quando o operador coloca o input do palestrante (ou um input composto com ele como layer) em Program no vMix, a página sincroniza em até 500 ms mostrando slide atual + próximo

## Inputs e Outputs

**Inputs:**
- API HTTP do vMix (`http://<vmix-host>:8088/api`) — XML com estado dos inputs, Program, Preview e overlays
- Pasta(s) locais com PNGs dos slides (uma por palestrante)
- `config.json` com IP do vMix + lista de palestrantes (GUID → pasta)

**Outputs:**
- Página web em `http://localhost:5000/` com:
  - Slide **atual** (menor, borda vermelha, à esquerda)
  - Slide **próximo** (maior, borda amarela, à direita)
  - Rodapé com nome do palestrante + "Slide X de Y"
  - Barra de progresso baseada na posição dentro da apresentação
- Endpoint `GET /state` retornando JSON com estado atual (útil para integrações futuras)

## Stack e arquitetura

- **Linguagem:** Python 3.11+ (stdlib pura — sem dependências externas)
- **Servidor HTTP:** `http.server` + `socketserver.ThreadingMixIn`
- **Cliente vMix:** `urllib.request` + `xml.etree.ElementTree`
- **Frontend:** HTML/CSS/JS vanilla (sem build step, sem framework)
- **Empacotamento:** PyInstaller `--onefile` → `apresentador.exe` (~8 MB)
- **Plataforma alvo:** Windows (onde o vMix roda). Funciona em qualquer máquina da rede local do vMix.

**Por que stdlib pura:** zero `pip install` na máquina do operador, .exe pequeno, menos superfície de falha em ambiente de live.

## Integrações externas

- **vMix HTTP API** — consulta XML a cada 500 ms para detectar input ativo em Program e suas overlays
- Nenhuma outra integração (sem dependências de nuvem, sem telemetria)

## Escopo do MVP (v0.1.0)

- [x] Polling da API do vMix na porta 8088 (configurável via `config.json`)
- [x] Detecção do palestrante ativo quando o input está **direto em Program**
- [x] Detecção quando o palestrante está em **overlay/layer de um input composto** (ex: "SLIDES WAGNER + CAM" em Program com Wagner como layer 2)
- [x] Cruzamento do `title` do vMix com a lista de PNGs do filesystem para identificar slide atual + próximo
- [x] Layout web com slide atual menor (vermelho) e próximo maior (amarelo), proporção 16:9 em ambos
- [x] Rodapé com nome do palestrante + "Slide X de Y" + barra de progresso
- [x] Empacotamento como `.exe` single-file
- [x] Configuração via `config.json` externo editável na mão

### Exemplo de config.json

```json
{
  "vmix": {
    "host": "192.168.X.X",
    "port": 8088
  },
  "server_port": 5000,
  "palestrantes": [
    {
      "nome": "Wagner",
      "guid": "51f89804-b46f-4716-8914-4f692c63c38c",
      "pasta": "001 - Wagner"
    },
    {
      "nome": "Vinicius",
      "guid": "1cb3e57a-b400-4751-8c16-a5d5a88dfe03",
      "pasta": "003 - Vinícius"
    },
    {
      "nome": "Camila",
      "guid": "fc56787d-71c7-4708-bb14-e75ac2c70e46",
      "pasta": "004 - Camila"
    }
  ]
}
```

O caminho da pasta de slides é **relativo** à pasta onde o `.exe` está sendo executado (tipicamente dentro da pasta do evento). PNGs são ordenados alfabeticamente dentro de cada pasta.

## Fora de escopo (MVP)

- **Controle ativo do vMix** (Next/Prev slide pela interface web) — a app é monitor passivo
- **GUI de configuração** — v0.1.0 configura apenas via JSON editado à mão; uma interface de setup web pode vir em versões futuras
- Suporte a tipos de input além de `Photos`/`ImageList` (PowerPoint input, VirtualSet, vídeos)
- Anotações, timer, chat ou demais recursos de um *presenter view* completo
- Customização de tema/cores via config

## Referências

- [vMix Web API — documentação oficial](https://www.vmix.com/help27/index.htm?DeveloperAPI.html)
- Inspiração de UX: *Presenter View* do PowerPoint / Keynote

---

**Projeto privado — uso interno.**
