# Sessions

## 2026-05-16 — Deploy no PC do evento + auditoria de robustez (v1.1.1 / v1.1.2)

### Contexto
Depois de empacotar o exe único, ele foi deployado no PC do evento (`vmix`, via SSH).
O usuário rodou lá e relatou: nenhum ícone na bandeja, e HTTP 500 ao salvar palestrante.
Pediu uma verificação completa de tudo que pode quebrar antes de usar ao vivo.

### Desafios e soluções
- **Ícone da bandeja não aparecia**: diagnóstico por SSH (o app rodava — server na 5000)
  mostrou no log `tray falhou: icon.ico nao encontrado`. No exe `--onefile` o `icon.ico`
  é embutido em `sys._MEIPASS`; o `_asset_path` do `server.py` já tratava isso, mas o
  `tray.py._icon_path()` (função separada) não — só olhava `recursos/` e a pasta do exe.
  Lição: ao mudar a resolução de recursos pro exe único, varrer TODOS os pontos que
  carregam arquivo, não só o óbvio.
- **HTTP 500 ao salvar numa instalação nova**: `GET /admin/api/config` fazia `open()` cru
  do `config.json`, que não existe numa instalação nova (criado no 1º save). O `/admin`
  chama esse GET dentro de `persistirConfig` ao salvar → 500 → impossível configurar do
  zero. O `carregar_config` do boot já tratava arquivo ausente; o endpoint GET não.
- **Cache de `fetch_vmix_xml` segurando o lock durante o fetch**: a 1ª versão segurava
  `_xml_cache_lock` durante o `urlopen`. Com vMix offline (fetch ~6 s) + vários pollers,
  tudo serializava — 5 `/state` concorrentes levavam ~30 s e o servidor travava. Corrigido:
  fetch FORA do lock; o lock só protege leitura/escrita do cache.
- **Caminho com acento via SSH**: a pasta do exe tem `USÁVEIS`; PowerShell por SSH→cmd
  embaralhava o `Á`. Solução: construir o path com `[char]0xC1` (ASCII puro no comando).
- **`Start-Process -LiteralPath`** não existe no PowerShell 5.1 (PC do evento) — usar `-FilePath`.

### Decisões tomadas
- Auditoria feita com 3 agentes de revisão em paralelo (server, tray/build, frontend).
  Falsos-positivos descartados conferindo a realidade — ex: um agente alertou que o tkinter
  poderia não ser empacotado, mas o log do PC do evento provou que `import tray` (que puxa
  tkinter/pystray/PIL) funcionou; o PyInstaller analisa `tray.py` por estar no mesmo dir
  do script. Só os bugs reais foram corrigidos (~15).
- Smoke test do exe direto no PC do evento via SSH — o server roda headless (o tray precisa
  de sessão interativa, mas server e endpoints não), o que permite validar tudo remoto.

### Descobertas
- PyInstaller `--onefile`: `sys.executable` = exe real, `sys._MEIPASS` = pasta temp de
  extração; recursos embutidos (`--add-data`/`--add-binary`) ficam em `_MEIPASS`.
- `urlopen` pra `localhost:8088` com vMix offline leva ~6 s neste ambiente (tentativa
  IPv6 `::1` + IPv4) — por isso segurar o lock durante o fetch arruína a concorrência.

## 2026-05-16 — Suporte a input List (VideoList) do vMix + frames de vídeo (v1.1.0)

### Contexto
A app só sincronizava inputs `Photos` (slideshow de imagens). O usuário usa inputs **List
(VideoList)** do vMix como "apresentação de vídeos" — playlist mista de slides + vídeos — e
queria que o modo apresentador funcionasse com eles, mostrando os vídeos de forma que o
palestrante reconheça que o item no ar é um vídeo.

### Desafios e soluções
- **Não chutar a API/XML do vMix**: o usuário forneceu um preset `.vmix` real e depois o vMix
  v29 estava acessível ao vivo. Inspecionar o `/api` revelou que os `<item>` de uma List **não
  têm** atributo `selected` — só o `selectedIndex` do input (1-based). `_parse_list_input` usa
  `selected="true"` como primário (defensivo) e cai no `selectedIndex`.
- **`build.bat` embaralhava ao rodar**: caracteres UTF-8 (em-dash, acentos) dessincronizavam o
  parser do `cmd.exe`, cortando palavras dos comandos. Reescrito em ASCII puro.
- **PyInstaller "Unable to find ...\build\src\tray.py"**: `--add-data` resolve caminhos
  relativos ao `--specpath`, não ao cwd. Corrigido usando caminhos absolutos.
- **Card de vídeo cortado em painel estreito**: o card era dimensionado em `vh` (viewport); num
  painel estreito o frame fica pequeno e o texto estourava. Trocado pra container query
  (`container-type: size` no frame + unidades `cqmin`).
- **Letterbox num slide 16:9**: `.slide-frame` tinha `border: 4px` + `box-sizing: border-box`
  → o `aspect-ratio` valia pra caixa COM borda, deixando o interior fora de 16:9. A borda
  virou `box-shadow` (não ocupa a caixa).
- **Não dava pra remover nem adicionar palestrante**: `validar_config` era all-or-nothing —
  uma entrada antiga com pasta morta reprovava QUALQUER save. Pasta inexistente no disco
  deixou de bloquear o save (segue sinalizada no health badge).
- **`gerar_thumbs` bloqueava a request**: geração síncrona de até N×30s. Virou assíncrona —
  thread daemon + registro de job (dict+lock, modelo `ProjetorManager`) + endpoint de status
  pra polling com barra de progresso no admin.
- **`ConnectionAbortedError` no log**: cliente fechando a aba durante o polling de 500ms.
  `ThreadingServer.handle_error` passa a silenciar `ConnectionError`.

### Decisões tomadas
- **Frames de vídeo pré-gerados** (não snapshot ao vivo do vMix): o operador clica "Gerar
  frames", ffmpeg extrai 1 frame representativo pra `_thumbpresentation/` ao lado dos vídeos.
  Mais simples, zero chamada ao vMix durante o show, frame persiste em disco.
- **ffmpeg/ffprobe embutidos no exe** — a máquina do evento não precisa instalar nada.
- **Build mantido `--onefile`** (exe único ~95 MB) apesar do cold start ~3-8s e do risco de
  falso-positivo de antivírus — decisão do usuário, que prefere 1 arquivo só. Mitigado com
  seção no `LEIA-ME.txt` + helper `Liberar no Defender.bat`.
- **Item de vídeo = frame + tag vermelha "VÍDEO" no canto** (não o card grande). O card grande
  virou fallback pra quando o frame ainda não foi gerado.
- **Duração via ffprobe em sidecar `.dur`** — o vMix só expõe duração do item atual; o sidecar
  resolve pros slots ATUAL e PRÓXIMO.

### Descobertas
- vMix v29 `/api`: `<item>` de List sem `selected`, só `selectedIndex` (1-based).
- `localhost` resolve IPv6 `::1` primeiro → ~2s de timeout em cliente sem Happy Eyeballs
  (`urllib`). Browser (Happy Eyeballs) e acesso via IP da LAN não sofrem.
- `--onefile` é a causa raiz tanto do cold start quanto do flag de antivírus (auto-extração
  SFX). `--onedir` resolveria os dois, mas foi recusado em favor do arquivo único.
