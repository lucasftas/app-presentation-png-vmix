# Sessions

## 2026-06-03 — "Roda mas sem ícone": relaunch-takeover + Painel fallback (v1.3.0, via /voudormir)

### Contexto
Após o v1.2.0, o usuário perguntou como o app lida quando já está em execução mas **não
aparece na bandeja** — e pediu um "matar o antigo e subir o novo" ágil. Depois pediu também
uma **alternativa de controle além do ícone do tray**. Rodado via `/voudormir` (front-load das
aprovações, execução autônoma, release no fim) pra deixar pronto pro deploy do dia seguinte.

### Desafios e soluções
- **Por que o ícone some**: investiguei o pystray instalado — ele **já trata `WM_TASKBARCREATED`**
  (`_on_taskbarcreated` → `_show()`, com opt-in via `ChangeWindowMessageFilterEx`). Ou seja, no
  restart do Explorer o ícone volta sozinho. O watchdog que o usuário tinha pedido seria
  redundante — reportei e ele topou pular. O caso real de "sem ícone" é o **tray falhar na init**
  (cai no `except` do `main()` → headless segurando o mutex).
- **Takeover e o refcount do mutex**: o pulo do gato — quando `aquirir_single_instance` falha,
  o `CreateMutexW` daquela tentativa **também abre um handle**. O mutex só é destruído quando o
  refcount zera. Então, mesmo matando o processo antigo, se eu não soltar o **meu próprio**
  handle antes de re-adquirir, o `CreateMutexW` seguinte ainda vê `ERROR_ALREADY_EXISTS`.
  Solução: `_single_instance.release()` antes do loop de re-aquisição, e `cand.release()` em
  cada tentativa falha.
- **Não matar `python.exe` em dev**: `_matar_outras_instancias` é gated em `sys.frozen` +
  `win32` — `taskkill /F /IM "Iniciar Apresentador.exe"` só no exe. Em dev é no-op (teste cobre).
- **Alternativa ao tray = o Dashboard que já existe**: o `/admin` já é um painel completo. Em
  vez de criar UI nova, o instalador cria um atalho "Painel do Apresentador" (Menu Iniciar +
  Desktop) apontando pra um `.url`, e o app **reescreve esse `.url` com o porto real** (5000-5009)
  a cada boot — então o atalho nunca aponta pro porto errado mesmo com o fallback de porta. E
  quando o tray falha, o app **auto-abre o Dashboard**.
- **Takeover validado ao vivo**: smoke lançou a instância A (PID X, /admin 200), depois a B —
  que detectou o mutex, matou A e assumiu; sobrou 1 processo respondendo. Confirmou também que
  o fix de `%TEMP%` do v1.2.0 segue (zero `_MEI`).

### Decisões tomadas
- Watchdog de re-registro de ícone: **descartado** (pystray já faz).
- Alternativa ao tray: **atalho pro Dashboard + auto-open no fail** (não janela nativa, não hotkey).
- Versão **v1.3.0** (minor). Release autônoma no fim do `/voudormir` (pré-aprovada).
- Limitação aceita: janelas Chrome kiosk de projetores da instância morta podem ficar órfãs no
  takeover (sem sweep agressivo de chrome nesta entrega) — operador fecha.

## 2026-06-03 — Crash em /temp: migração --onedir + instalador + auditoria de 50 achados (v1.2.0)

### Contexto
O app crashou em produção com mensagem de que "não conseguiu fazer algo em /temp".
O usuário pediu investigação profunda (não pode travar em produção), perguntou se
o caminho era um instalador, e o que estava sendo gravado em `/temp`. Pediu também
uma varredura ampla por outras coisas que pudessem quebrar e inconsistências.

### Desafios e soluções
- **Causa-raiz do "/temp"**: o build `--onefile` do PyInstaller extrai TODO o bundle
  (runtime Python + `ffmpeg.exe` + `ffprobe.exe` ≈ 90 dos 95 MB + HTML + ícones) pra
  `%TEMP%\_MEIxxxx` a CADA boot e apaga ao sair. Antivírus escaneando/quarentenando
  esses 90 MB, `%TEMP%` sem permissão (perfil itinerante/política), disco cheio ou
  `_MEIxxxx` órfão → o bootloader falha com erro de temp. **Fix: `--onedir`** — carrega
  de `_internal\` ao lado do exe, **zero extração em `%TEMP%`**. Empacotado num instalador
  Inno Setup que instala em `%LocalAppData%` (sem admin → pasta gravável pro config/logs).
- **Provar o fix**: smoke do exe com snapshot de `_MEI*` no `%TEMP%` antes/depois — delta 0.
- **Probe HTTP "falhando" no smoke**: `Invoke-WebRequest http://localhost:5000` resolvia
  `localhost` → `::1` (IPv6), mas o server binda IPv4 (`("", porta)`) — sem resposta.
  Além disso `/state` espera o timeout de 3 s do vMix (ausente na máquina de build), que
  estourava o timeout de 2 s do cliente. Resolvido usando `127.0.0.1` + timeout 10 s, e
  validando primeiro `GET /` (serve `index.html` de `_internal\`, sem tocar vMix).
- **Auditoria adversarial**: workflow multi-agente em 8 dimensões (concorrência, parsing
  XML, filesystem/path, config/boot, HTTP, tray/projetor, docs↔código, deps) — 82 achados,
  cada um verificado por um agente tentando REFUTAR; 50 confirmados, priorizados por severidade.
- **`_cfg_lock` → RLock**: ao introduzir helpers que leem estado global sob lock
  (`_palestrante_info`/`_vmix_target`), um `Lock` simples arriscaria auto-deadlock se algum
  caminho já o detivesse; `RLock` (reentrante) elimina o risco.
- **Teste do limite de Content-Length**: simulado com socket cru enviando só os headers
  (`Content-Length` gigante, sem corpo) contra um `ThreadingServer` real → 413 antes do `read()`.
- **"Tags v1.1.x faltando" (achado da auditoria)**: era falso-positivo — `git tag` local só
  ia até v1.0.0, mas as releases v1.1.1–v1.1.4 existem no GitHub. `git fetch --tags` reconciliou.

### Decisões tomadas
- **Escopo "Tudo"** (escolha do usuário): corrigir os 50 achados nesta entrega, não só a
  migração — alinhado com "não pode travar em produção".
- **`%LocalAppData%` (não `%ProgramFiles%`)**: instalação per-usuário sem UAC mantém a pasta
  gravável, então `config.json`/`logs\` continuam ao lado do exe sem mudar o código (`APP_DIR`).
- **`/admin` só no PC operador (confiável)**: o path traversal em `/admin/api/ls` foi mantido
  como baixa prioridade (decisão do usuário), sem whitelist de raiz.
- **Exclusão do Defender vira opcional/nice-to-have**: com `--onedir` o antivírus escaneia 1×
  no install em vez de a cada boot, então a exclusão deixou de ser crítica.

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
