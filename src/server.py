"""Servidor do Modo Apresentador sincronizado com vMix.

- Faz polling na API HTTP do vMix e identifica o input em Program
- Suporta tanto palestrante direto em Program quanto como overlay/layer
  de um input composto (ex: Colour com camera + slides)
- Extrai o slide atual do atributo `title` do vMix e cruza com a pasta
  de PNGs para descobrir o proximo slide
- Serve frontend HTML e os PNGs via HTTP local

Sem dependencias externas - stdlib pura. Requer Python 3.9+.
"""
from __future__ import annotations

import concurrent.futures
import datetime as _dt
import http.server
import json
import logging
import logging.handlers
import mimetypes
import os
import re
import shutil
import socket
import socketserver
import string
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

# PyInstaller --noconsole pode deixar sys.stdout/stderr como None — qualquer
# print() (banner, avisos de config) quebraria com AttributeError, e isso roda
# no import do modulo (carregar_config). Garante um destino seguro antes disso.
for _stream in ("stdout", "stderr"):
    if getattr(sys, _stream, None) is None:
        try:
            setattr(sys, _stream, open(os.devnull, "w", encoding="utf-8"))
        except OSError:
            pass

# -------------------- Constantes globais --------------------

# Formatos de imagem aceitos pelo vMix (Photos/ImageList).
# Fonte: dialogo de arquivos do vMix — "*.JPG;*.BMP;*.PNG;*.GIF;*.JPEG;*.WEBP".
IMAGE_EXTS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

# Formatos de video que podem aparecer como item de um input List (VideoList).
# Itens de video nao tem como ser exibidos no apresentador — viram um card "VIDEO".
VIDEO_EXTS: tuple[str, ...] = (
    ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".ts", ".m4v",
    ".mpg", ".mpeg", ".webm", ".flv", ".m2ts", ".mts",
)

_NAT_RE = re.compile(r"(\d+)")


def _natural_key(s: str) -> list:
    """Chave de sort natural: `slide 2.png` antes de `slide 10.png`.

    Quebra a string em tokens alternados texto/numero e converte os numericos
    para int para comparacao correta.
    """
    return [int(t) if t.isdigit() else t.lower() for t in _NAT_RE.split(s)]


def _is_image(p: Path) -> bool:
    return p.suffix.lower() in IMAGE_EXTS


def _kind_de(nome: str) -> str:
    """Classifica um item de List pela extensao: 'imagem', 'video' ou 'outro'.

    Inputs List do vMix misturam slides (PNG/JPG) e videos (MP4/MOV) na mesma
    playlist. O apresentador exibe a imagem quando da, e um card "VIDEO" quando
    o item e um video (nao da pra mostrar frame).
    """
    ext = os.path.splitext(nome)[1].lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "imagem"
    return "outro"


def match_filename(title: str, imagens: list[str]) -> int | None:
    """Procura qual elemento de `imagens` corresponde ao filename dentro de `title`.

    Estrategia (em ordem de prioridade):
    1. Match exato: filename inteiro presente no title (case-insensitive no suffix)
    2. Em caso de empate, escolhe o filename mais longo (mais especifico)

    Isso resolve ambiguidades tipo `slide 1.png` vs `slide 10.png` quando o
    title e `"... slide 10.png"` — antes bateria nos dois via substring.
    """
    if not title or not imagens:
        return None

    title_fold = title.casefold()
    # Casefold pro title; pra cada imagem, busca match exato
    matches: list[tuple[int, int, str]] = []  # (idx, length, nome)
    for i, nome in enumerate(imagens):
        if nome.casefold() in title_fold:
            matches.append((i, len(nome), nome))

    if not matches:
        return None

    # Desempate: maior comprimento primeiro (mais especifico)
    matches.sort(key=lambda t: -t[1])
    return matches[0][0]

# -------------------- Localizacao --------------------

def app_dir() -> Path:
    """Pasta do .exe/script — onde config.json e logs/ ficam (externos)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundle_dir() -> Path:
    """Pasta dos recursos embutidos (HTML, ffmpeg, icone).

    No exe --onefile, PyInstaller extrai os --add-data/--add-binary pra um
    diretorio temporario em sys._MEIPASS. Fora do exe, e a pasta do script.
    """
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else app_dir()


APP_DIR = app_dir()
_BUNDLE_DIR = bundle_dir()
_RECURSOS_DIR = APP_DIR / "recursos"


def _asset_path(name: str) -> Path:
    """Localiza um asset (index.html, admin.html, icon.ico).

    Ordem: embutido no exe (_MEIPASS) → pasta recursos/ (portable antigo)
    → APP_DIR (dev mode).
    """
    for base in (_BUNDLE_DIR, _RECURSOS_DIR, APP_DIR):
        cand = base / name
        if cand.is_file():
            return cand
    return APP_DIR / name


CONFIG_PATH = APP_DIR / "config.json"
INDEX_PATH = _asset_path("index.html")
ADMIN_PATH = _asset_path("admin.html")
LOG_DIR = APP_DIR / "logs"

logger = logging.getLogger("apresentador")


def setup_logging(verbose: bool = True) -> None:
    """Configura logging para console + arquivo em logs/YYYY-MM-DD.log.

    Arquivo rotaciona automaticamente ao passar de 10MB (max 5 arquivos).
    """
    if logger.handlers:
        return  # ja configurado (ex: em testes)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S")

    if verbose:
        ch = logging.StreamHandler(sys.stderr)
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    try:
        LOG_DIR.mkdir(exist_ok=True)
        hoje = _dt.date.today().isoformat()
        fh = logging.handlers.RotatingFileHandler(
            LOG_DIR / f"{hoje}.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError as e:
        print(f"[aviso] nao foi possivel criar log em arquivo: {e}", file=sys.stderr)

_cfg_lock = threading.Lock()
_clientes_lock = threading.Lock()
# IP → timestamp Unix do ultimo GET /state; registra quem esta assistindo
_CLIENTES: dict[str, float] = {}


def registrar_cliente(ip: str) -> None:
    if not ip:
        return
    with _clientes_lock:
        _CLIENTES[ip] = time.time()


def clientes_ativos(janela_s: int = 30) -> list[dict]:
    """Retorna lista de clientes com hit nos ultimos `janela_s` segundos."""
    agora = time.time()
    out: list[dict] = []
    with _clientes_lock:
        for ip, ts in list(_CLIENTES.items()):
            if agora - ts > janela_s:
                # GC de entries muito antigas (>5min)
                if agora - ts > 300:
                    _CLIENTES.pop(ip, None)
                continue
            out.append({
                "ip": ip,
                "ultimo_hit_s": round(agora - ts, 1),
            })
    out.sort(key=lambda c: c["ultimo_hit_s"])
    return out

# -------------------- Config --------------------

def _config_default() -> dict:
    return {
        "vmix": {"host": "localhost", "port": 8088},
        "server_port": 5000,
        "palestrantes": [],
    }


def _backup_config_corrompido(motivo: str) -> None:
    """Move config.json invalido pra config.bak.json e loga o motivo."""
    backup = CONFIG_PATH.with_suffix(".bak.json")
    try:
        CONFIG_PATH.replace(backup)
        print(f"[ERRO] config.json {motivo} — movido para {backup.name}, "
              f"iniciando com config vazia.", file=sys.stderr)
    except OSError as move_err:
        print(f"[ERRO] config.json {motivo} e nao consegui fazer backup: "
              f"{move_err}", file=sys.stderr)


def carregar_config() -> dict:
    """Carrega config.json com recovery automatico.

    Casos tratados:
    - arquivo ausente: retorna default (cria em disco ao primeiro save)
    - JSON corrompido: faz backup em config.bak.json, loga aviso, retorna default
    - erro inesperado de IO: retorna default para nao derrubar o server
    """
    if not CONFIG_PATH.is_file():
        print(f"[aviso] config.json nao encontrado em {CONFIG_PATH} — "
              f"iniciando com config vazia. Use /admin para configurar.",
              file=sys.stderr)
        return _config_default()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        _backup_config_corrompido(f"corrompido ({e})")
        return _config_default()
    except OSError as e:
        print(f"[ERRO] falha lendo config.json: {e} — usando config vazia",
              file=sys.stderr)
        return _config_default()
    # JSON valido mas nao e um objeto (ex: arquivo editado errado virou lista)
    # — sem isso, CFG.get(...) lancaria AttributeError no import e o exe
    # --noconsole morreria no boot sem nenhum feedback.
    if not isinstance(data, dict):
        _backup_config_corrompido("nao e um objeto JSON")
        return _config_default()
    return data


# Executor compartilhado: isola operacoes de filesystem (UNC lento, share caido)
# Usado por list_dir() e carregar_palestrantes() com timeout.
_LS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="fs_worker"
)


def _listar_imagens_em(pasta_path: Path) -> list[str]:
    """Lista imagens de uma pasta (natural sort). Pode demorar em UNC lento."""
    return sorted(
        (x.name for x in pasta_path.iterdir() if x.is_file() and _is_image(x)),
        key=_natural_key,
    )


def carregar_palestrantes(cfg: dict, timeout_por_pasta: float = 5.0) -> dict:
    """Retorna {guid: (nome, pasta_path, [imagens], tipo)}.

    `tipo` e "photos" (default) ou "list":
    - "photos": input Photos do vMix — slides vem de uma pasta no disco,
      lida aqui com timeout (default 5s) pra nao travar em UNC lento/caido.
    - "list": input List (VideoList) — a playlist (slides + videos) vem do
      proprio XML do vMix em runtime, entao nao precisa de pasta. Fica como
      (nome, None, [], "list").

    Aceita PNG, JPG, JPEG, BMP, GIF, WEBP. Ordenacao natural.
    """
    out: dict = {}
    for p in cfg.get("palestrantes", []):
        nome = p.get("nome", "").strip()
        guid = p.get("guid", "").strip().lower()
        tipo = (p.get("tipo") or "photos").strip().lower()
        pasta_raw = p.get("pasta", "").strip()

        if tipo == "list":
            if not (nome and guid):
                print(f"[aviso] entrada List invalida (nome/guid): {p}",
                      file=sys.stderr)
                continue
            out[guid] = (nome, None, [], "list")
            continue

        if not (nome and guid and pasta_raw):
            print(f"[aviso] entrada invalida de palestrante: {p}", file=sys.stderr)
            continue
        pasta_path = Path(pasta_raw)
        if not pasta_path.is_absolute():
            pasta_path = (APP_DIR / pasta_raw).resolve()

        # is_dir() tambem pode travar em UNC — protege tambem
        try:
            future = _LS_EXECUTOR.submit(pasta_path.is_dir)
            eh_dir = future.result(timeout=timeout_por_pasta)
        except concurrent.futures.TimeoutError:
            print(f"[aviso] timeout ao acessar pasta de {nome}: {pasta_path}",
                  file=sys.stderr)
            continue
        except Exception as e:
            print(f"[aviso] erro acessando pasta de {nome}: {e}", file=sys.stderr)
            continue
        if not eh_dir:
            print(f"[aviso] pasta nao encontrada para {nome}: {pasta_path}",
                  file=sys.stderr)
            continue

        try:
            future = _LS_EXECUTOR.submit(_listar_imagens_em, pasta_path)
            imagens = future.result(timeout=timeout_por_pasta)
        except concurrent.futures.TimeoutError:
            print(f"[aviso] timeout listando imagens de {nome}: {pasta_path}",
                  file=sys.stderr)
            continue
        except Exception as e:
            print(f"[aviso] erro listando imagens de {nome}: {e}", file=sys.stderr)
            continue

        if not imagens:
            print(f"[aviso] pasta sem imagens para {nome}: {pasta_path}",
                  file=sys.stderr)
            continue
        out[guid] = (nome, pasta_path, imagens, "photos")
    return out


CFG = carregar_config()
VMIX_HOST = CFG.get("vmix", {}).get("host", "localhost")
VMIX_PORT = int(CFG.get("vmix", {}).get("port", 8088))
SERVER_PORT = int(CFG.get("server_port", 5000))
PALESTRANTES = carregar_palestrantes(CFG)


def validar_config(new_cfg: dict) -> list[str]:
    """Retorna lista de erros BLOQUEANTES do payload. Vazia = OK pra salvar.

    Valida (bloqueante):
    - payload e dict
    - 'palestrantes' e lista (se presente)
    - cada palestrante tem nome e guid; photos tem 'pasta' nao-vazia
    - GUIDs unicos (case-insensitive)
    - tipo e 'photos' ou 'list'

    NAO bloqueia por pasta inexistente / vazia no disco: o app e resiliente a
    isso em runtime (carregar_palestrantes pula, health badge sinaliza) e
    bloquear aqui impediria salvar QUALQUER coisa quando o config ja tem uma
    entrada com pasta morta — inclusive impediria remover a propria entrada.
    O estado da pasta no disco e checado em /admin/api/validate e /health.
    """
    erros: list[str] = []

    if not isinstance(new_cfg, dict):
        erros.append("config deve ser um objeto JSON")
        return erros

    pals = new_cfg.get("palestrantes", [])
    if not isinstance(pals, list):
        erros.append("'palestrantes' deve ser uma lista")
        return erros

    guids_vistos: dict[str, int] = {}
    for i, p in enumerate(pals):
        base = f"palestrantes[{i}]"
        if not isinstance(p, dict):
            erros.append(f"{base}: deve ser um objeto")
            continue

        nome = (p.get("nome") or "").strip()
        guid = (p.get("guid") or "").strip().lower()
        tipo = (p.get("tipo") or "photos").strip().lower()
        pasta_raw = (p.get("pasta") or "").strip()

        if not nome:
            erros.append(f"{base}.nome: obrigatorio")
        if not guid:
            erros.append(f"{base}.guid: obrigatorio")
        if tipo not in ("photos", "list"):
            erros.append(f"{base}.tipo: deve ser 'photos' ou 'list' (recebido: {tipo!r})")
        # Input List le a playlist do XML do vMix — nao exige pasta.
        if tipo == "photos" and not pasta_raw:
            erros.append(f"{base}.pasta: obrigatorio")

        if guid:
            if guid in guids_vistos:
                erros.append(
                    f"{base}.guid: duplicado — ja usado em palestrantes[{guids_vistos[guid]}]"
                )
            else:
                guids_vistos[guid] = i

        # Pasta no disco NAO e validada aqui de proposito — ver docstring.

    return erros


UI_PREFS_DEFAULTS = {"split_ratio": 38}


def get_ui_prefs() -> dict:
    """Retorna ui_prefs do CFG com defaults preenchidos."""
    cur = CFG.get("ui_prefs") if isinstance(CFG.get("ui_prefs"), dict) else {}
    out = dict(UI_PREFS_DEFAULTS)
    for k in UI_PREFS_DEFAULTS:
        if k in cur:
            out[k] = cur[k]
    return out


def salvar_ui_prefs(novo: dict) -> None:
    """Salva ui_prefs no config.json preservando demais campos.

    Ignora chaves desconhecidas e clampa split_ratio no range [20, 80].
    """
    global CFG
    if not isinstance(novo, dict):
        raise ValueError("ui_prefs deve ser um objeto")

    prefs = dict(UI_PREFS_DEFAULTS)
    prefs.update(get_ui_prefs())  # mantem o que ja estava

    if "split_ratio" in novo:
        try:
            v = int(novo["split_ratio"])
        except (TypeError, ValueError):
            raise ValueError("split_ratio deve ser numero")
        prefs["split_ratio"] = max(20, min(80, v))

    with _cfg_lock:
        # Le do disco, atualiza campo, grava atomico
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                atual = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            atual = dict(CFG)
        # config.json pode existir mas conter JSON nao-objeto — sem isso o
        # `atual["ui_prefs"] = ...` abaixo levantaria TypeError -> 500.
        if not isinstance(atual, dict):
            atual = dict(CFG)
        atual["ui_prefs"] = prefs
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(atual, f, ensure_ascii=False, indent=2)
        tmp.replace(CONFIG_PATH)
        CFG = atual
    if _config_watcher:
        _config_watcher.marcar_escrita_nossa()


def rescan_pasta(guid: str) -> list[str]:
    """Re-le o filesystem da pasta de um palestrante e atualiza PALESTRANTES.

    Retorna a nova lista de arquivos de imagem (ordenacao natural), ou [] se
    o GUID nao esta em PALESTRANTES ou a pasta nao existe mais.
    """
    global PALESTRANTES
    g = (guid or "").lower().strip()
    info = PALESTRANTES.get(g)
    if info is None:
        return []
    nome, pasta_path, _, tipo = info
    # List nao tem pasta — playlist vem do vMix em runtime, nada pra rescanear.
    if tipo == "list" or pasta_path is None:
        return []
    if not pasta_path.is_dir():
        return []
    try:
        imagens = sorted(
            (x.name for x in pasta_path.iterdir() if x.is_file() and _is_image(x)),
            key=_natural_key,
        )
    except (PermissionError, OSError):
        return []
    with _cfg_lock:
        PALESTRANTES[g] = (nome, pasta_path, imagens, tipo)
    return imagens


_config_watcher: "ConfigWatcher | None" = None


def salvar_config(new_cfg: dict) -> None:
    """Valida, escreve config.json atomicamente e recarrega estado em memoria.

    Levanta ValueError("config_invalida", [lista_de_erros]) se validacao falhar.
    Config em disco nao e alterado quando ha erros.
    """
    global CFG, VMIX_HOST, VMIX_PORT, PALESTRANTES
    erros = validar_config(new_cfg)
    if erros:
        raise ValueError("config_invalida", erros)

    with _cfg_lock:
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(new_cfg, f, ensure_ascii=False, indent=2)
        tmp.replace(CONFIG_PATH)
        CFG = new_cfg
        VMIX_HOST = CFG.get("vmix", {}).get("host", "localhost")
        VMIX_PORT = int(CFG.get("vmix", {}).get("port", 8088))
        PALESTRANTES = carregar_palestrantes(CFG)
    if _config_watcher:
        _config_watcher.marcar_escrita_nossa()


# -------------------- Admin helpers --------------------

def _safe_resolve(p: str) -> Path:
    return Path(p).expanduser().resolve()


def get_preset_dir() -> Path | None:
    """Extrai o diretorio pai do .vmixZip do preset atual do vMix."""
    try:
        root = fetch_vmix_xml()
        preset = root.findtext("preset")
        if preset:
            p = _safe_resolve(preset).parent
            if p.is_dir():
                return p
    except Exception:
        return None
    return None


def get_roots() -> list[dict]:
    """Lista raizes permitidas para navegar no file browser."""
    out: list[dict] = []
    seen: set[str] = set()

    def add(path: Path, source: str) -> None:
        if not path.is_dir():
            return
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        out.append({"path": str(path), "source": source})

    # 1. Raizes configuradas explicitamente
    for r in CFG.get("roots", []) or []:
        try:
            add(_safe_resolve(r), "configurado em config.json")
        except Exception:
            continue

    # 2. Pasta pai do preset do vMix + avo (tipicamente pasta do evento)
    preset_dir = get_preset_dir()
    if preset_dir:
        add(preset_dir, "pasta do preset vMix")
        if preset_dir.parent != preset_dir:
            add(preset_dir.parent, "pasta pai do preset vMix")

    # 3. Fallback: pasta do app
    add(APP_DIR, "pasta do app")

    return out


def list_drives() -> list[dict]:
    """Enumera drives Windows acessiveis (C:\\, D:\\, ...)."""
    out: list[dict] = []
    for letter in string.ascii_uppercase:
        p = Path(f"{letter}:\\")
        try:
            if p.exists() and p.is_dir():
                out.append({"path": str(p), "label": f"{letter}:"})
        except OSError:
            continue
    return out


def listar_preview(path_str: str) -> dict:
    """Lista imagens dentro de `path_str` com URLs servidas por /admin/api/preview/img.

    Usado pelo grid de miniaturas do modal de adicionar palestrante:
    o operador ve todas as imagens pra confirmar visualmente que a pasta
    e do palestrante correspondente antes de salvar.
    """
    target = _safe_resolve(path_str)
    if not target.is_dir():
        raise FileNotFoundError(f"Nao e uma pasta: {target}")

    items: list[dict] = []
    try:
        nomes = sorted(
            (x.name for x in target.iterdir() if x.is_file() and _is_image(x)),
            key=_natural_key,
        )
    except (PermissionError, OSError) as e:
        raise PermissionError(f"Sem acesso a pasta: {e}")

    pasta_enc = urllib.parse.quote(str(target), safe="")
    for nome in nomes:
        arq_enc = urllib.parse.quote(nome, safe="")
        items.append({
            "name": nome,
            "url": f"/admin/api/preview/img?pasta={pasta_enc}&arq={arq_enc}",
        })
    return {"path": str(target), "total": len(items), "items": items}


def preview_img_path(pasta_str: str, arq: str) -> Path:
    """Resolve path seguro para servir uma imagem de preview.

    Levanta PermissionError em tentativa de path traversal,
    FileNotFoundError se arquivo nao existe.
    """
    pasta = _safe_resolve(pasta_str)
    if not pasta.is_dir():
        raise FileNotFoundError(f"Pasta nao existe: {pasta}")
    candidate = (pasta / arq).resolve()
    try:
        candidate.relative_to(pasta)
    except ValueError:
        raise PermissionError(f"path traversal bloqueado: {arq}")
    if not candidate.is_file():
        raise FileNotFoundError(f"Arquivo nao existe: {candidate.name}")
    if not _is_image(candidate):
        raise PermissionError(f"Nao e imagem: {candidate.name}")
    return candidate


def _list_dir_work(target: Path) -> list[dict]:
    """Trabalho bruto de listar subpastas — executado dentro do ThreadPoolExecutor."""
    items: list[dict] = []
    try:
        children = sorted(target.iterdir(), key=lambda p: _natural_key(p.name))
    except (PermissionError, OSError):
        children = []

    for child in children:
        if child.name.startswith(".") or child.name.startswith("$"):
            continue
        try:
            if not child.is_dir():
                continue
            imagens = 0
            subdirs = 0
            try:
                for x in child.iterdir():
                    if x.is_file() and _is_image(x):
                        imagens += 1
                    elif x.is_dir() and not x.name.startswith("."):
                        subdirs += 1
            except (PermissionError, OSError):
                pass
            items.append({
                "name": child.name,
                "path": str(child),
                "imagens": imagens,
                "subdirs": subdirs,
            })
        except (PermissionError, OSError):
            continue
    return items


def list_dir(path_str: str, timeout: float = 3.0) -> dict:
    """Lista subpastas (com contagem de imagens) dentro de `path_str`.

    Sem restricao de raiz: app roda local para operador do evento.
    Protegido por timeout (default 3s) — UNC lento/caido nao trava worker.

    Cada item retorna {name, path, imagens, subdirs}. Se deu timeout,
    retorna {path, items: [], timeout: True}.
    """
    target = _safe_resolve(path_str)
    if not target.is_dir():
        raise FileNotFoundError(f"Nao e uma pasta: {target}")

    future = _LS_EXECUTOR.submit(_list_dir_work, target)
    try:
        items = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return {"path": str(target), "items": [], "timeout": True}
    return {"path": str(target), "items": items}

# -------------------- compute_state --------------------

# Cache curto do XML do vMix. Varios clientes pollam /state a 500ms, mais o
# tray e o monitor de notificacoes — sem cache seriam N conexoes HTTP ao vMix
# por tick. O fetch roda sob lock: chamadas concorrentes serializam e a 2a+
# pega o cache fresco — 1 so conexao ao vMix mesmo se ele estiver lento.
_xml_cache_lock = threading.Lock()
_xml_cache: dict = {"ts": 0.0, "root": None}


def fetch_vmix_xml(max_age: float = 0.4) -> ET.Element:
    """XML da API do vMix, com cache de `max_age` segundos (default 400ms).

    O fetch roda FORA do lock: um fetch lento (vMix offline pode levar segundos)
    nao pode serializar todos os callers — isso travaria o /state pra todos os
    clientes. O lock so protege a leitura/escrita do cache (instantanea). Na
    cache fria pode haver alguns fetches paralelos, mas e bounded e nao bloqueia.

    Levanta excecao (URLError/timeout/ParseError) se o vMix estiver inacessivel
    e nao houver cache utilizavel — os callers ja tratam isso.
    """
    with _xml_cache_lock:
        c = _xml_cache
        if c["root"] is not None and time.time() - c["ts"] <= max_age:
            return c["root"]
    url = f"http://{VMIX_HOST}:{VMIX_PORT}/api"
    with urllib.request.urlopen(url, timeout=3) as resp:
        data = resp.read()
    root = ET.fromstring(data)
    with _xml_cache_lock:
        _xml_cache["root"] = root
        _xml_cache["ts"] = time.time()
    return root


def vmix_control(funcao: str, guid: str, value: str | None = None) -> dict:
    """Chama a API HTTP do vMix para controlar um input (next/prev/goto).

    Usado pelo menu hamburguer do index para o palestrante (ou operador)
    avancar/voltar slides sem precisar tocar no vMix.
    """
    if not guid:
        raise ValueError("guid obrigatorio")
    params = {"Function": funcao, "Input": guid}
    if value is not None:
        params["Value"] = str(value)
    url = f"http://{VMIX_HOST}:{VMIX_PORT}/api/?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return {"ok": True, "status": resp.status}
    except Exception as e:
        return {"ok": False, "erro": str(e)}


def vmix_list_control(guid: str, acao: str) -> dict:
    """next/prev/reset para um input List — traduz tudo pra SelectIndex.

    Input List nao tem NextPicture/PreviousPicture; o passo e calculado lendo
    o indice atual da playlist no XML do vMix. SelectIndex e 1-based.
    Usado pelo menu do index e pelo tray.
    """
    if acao == "reset":
        return vmix_control("SelectIndex", guid, "1")
    try:
        root = fetch_vmix_xml()
    except Exception as e:
        return {"ok": False, "erro": f"vMix inacessivel: {e}"}
    itens, cur = _parse_list_input(_input_by_key(root, guid))
    if cur is None:
        return {"ok": False, "erro": "nao consegui ler o indice atual da List"}
    alvo = cur + 2 if acao == "next" else cur  # cur e 0-based; SelectIndex 1-based
    alvo = max(1, min(len(itens), alvo))
    return vmix_control("SelectIndex", guid, str(alvo))


# -------------------- Thumbnails de video (input List) --------------------

# Itens de video de um List nao tem frame exibivel. O operador clica "gerar
# frames" no /admin → ffmpeg extrai 1 frame representativo de cada video pra
# uma subpasta `_thumbpresentation` ao lado dos arquivos. Depois e so referencia.
def _achar_ffmpeg_bin(nome: str) -> str | None:
    """Localiza ffmpeg/ffprobe.

    Prioridade: embutido no exe (_MEIPASS) → ao lado do app (recursos/ ou
    APP_DIR) → PATH do sistema. Assim o exe unico funciona em qualquer
    maquina sem ffmpeg instalado.
    """
    for base in (_BUNDLE_DIR, _RECURSOS_DIR, APP_DIR):
        cand = base / f"{nome}.exe"
        if cand.is_file():
            return str(cand)
    return shutil.which(nome)


_FFMPEG = _achar_ffmpeg_bin("ffmpeg")
_FFPROBE = _achar_ffmpeg_bin("ffprobe")
THUMB_DIR_NAME = "_thumbpresentation"

# Geracao de thumbs roda em background (pode levar minutos numa List grande).
# Registro de job por guid — o /admin faz polling do progresso. Modelo dict+lock
# como PROJETOR_MANAGER / _CLIENTES. Limitado pelo nº de inputs List (poucos),
# sobrescrito a cada run — sem necessidade de GC.
_thumbs_jobs: dict[str, dict] = {}
_thumbs_jobs_lock = threading.Lock()


def _thumb_path(video_path: Path) -> Path:
    """Caminho do thumbnail de um video: <pasta>/_thumbpresentation/<nome>.jpg."""
    return video_path.parent / THUMB_DIR_NAME / (video_path.name + ".jpg")


def _dur_path(video_path: Path) -> Path:
    """Sidecar com a duracao do video: <pasta>/_thumbpresentation/<nome>.dur."""
    return video_path.parent / THUMB_DIR_NAME / (video_path.name + ".dur")


def probe_duracao_ms(video_path: Path) -> int | None:
    """Duracao do video em ms via ffprobe. None se ffprobe ausente ou falhar."""
    if not _FFPROBE or not video_path.is_file():
        return None
    try:
        out = subprocess.run(
            [_FFPROBE, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(video_path)],
            capture_output=True, text=True, timeout=15,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    try:
        seg = float((out.stdout or "").strip())
    except ValueError:
        return None
    return int(seg * 1000) if seg > 0 else None


def _ler_dur(video_path: Path) -> int | None:
    """Le a duracao (ms) do sidecar .dur, se existir."""
    try:
        txt = _dur_path(video_path).read_text(encoding="ascii").strip()
    except OSError:
        return None
    return int(txt) if txt.isdigit() else None


def _ensure_dur(video_path: Path) -> int | None:
    """Garante o sidecar .dur (gera via ffprobe se faltar). Retorna ms ou None."""
    cached = _ler_dur(video_path)
    if cached is not None:
        return cached
    ms = probe_duracao_ms(video_path)
    if ms is None:
        return None
    dp = _dur_path(video_path)
    try:
        dp.parent.mkdir(exist_ok=True)
        dp.write_text(str(ms), encoding="ascii")
    except OSError:
        pass
    return ms


def gerar_thumb_video(video_path: Path, force: bool = False) -> str:
    """Extrai 1 frame representativo do video via ffmpeg.

    Salva em <pasta>/_thumbpresentation/<nome>.jpg. Retorna status:
    'gerado' | 'existia' | 'sem_ffmpeg' | 'falhou'. Regera se o thumb for
    mais antigo que o video (video recodificado).
    """
    if not _FFMPEG:
        return "sem_ffmpeg"
    if not video_path.is_file():
        return "falhou"
    thumb = _thumb_path(video_path)
    try:
        if not force and thumb.is_file() and \
                thumb.stat().st_mtime >= video_path.stat().st_mtime:
            return "existia"
    except OSError:
        pass
    try:
        thumb.parent.mkdir(exist_ok=True)
    except OSError:
        return "falhou"
    try:
        # filtro `thumbnail` escolhe um frame representativo (evita frame preto)
        subprocess.run(
            [_FFMPEG, "-y", "-i", str(video_path),
             "-vf", "thumbnail,scale=640:-2", "-frames:v", "1", str(thumb)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=30,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
    except (subprocess.SubprocessError, OSError):
        return "falhou"
    try:
        return "gerado" if thumb.is_file() and thumb.stat().st_size > 0 else "falhou"
    except OSError:
        return "falhou"


def _novo_job_thumbs(guid: str) -> dict:
    """Estado inicial de um job de geracao de thumbs."""
    return {
        "guid": guid, "status": "rodando",
        "total": 0, "processados": 0,
        "gerados": 0, "existiam": 0, "falharam": 0, "falhas": [],
        "erro": None, "iniciado_em": time.time(), "concluido_em": None,
    }


def _thumbs_worker(guid: str) -> None:
    """Gera os thumbnails de todos os videos de um input List, em background.

    Roda numa thread daemon dedicada (List grande leva minutos). Atualiza
    _thumbs_jobs[guid] a cada video pra o /admin poder fazer polling do
    progresso. Reusa gerar_thumb_video + _ensure_dur.
    """
    def _set(**kw) -> None:
        with _thumbs_jobs_lock:
            if guid in _thumbs_jobs:
                _thumbs_jobs[guid].update(kw)

    try:
        try:
            root = fetch_vmix_xml()
        except Exception as e:
            _set(status="erro", erro=f"vMix inacessivel: {e}",
                 concluido_em=time.time())
            return
        inp = _input_by_key(root, guid)
        if inp is None:
            _set(status="erro", erro="input List nao encontrado no vMix",
                 concluido_em=time.time())
            return
        itens, _ = _parse_list_input(inp)
        videos = [it for it in itens if it["kind"] == "video"]
        _set(total=len(videos))

        cont = {"gerado": 0, "existia": 0, "falhou": 0, "sem_ffmpeg": 0}
        falhas: list[str] = []
        for it in videos:
            vp = Path(it["path"])
            st = gerar_thumb_video(vp)
            cont[st] = cont.get(st, 0) + 1
            _ensure_dur(vp)  # sidecar de duracao (vale pra atual E proximo)
            if st == "falhou":
                falhas.append(it["nome"])
            _set(processados=sum(cont.values()),
                 gerados=cont["gerado"], existiam=cont["existia"],
                 falharam=cont["falhou"], falhas=falhas[:10])

        logger.info("gerar_thumbs %s: %s video(s) — %s gerados, %s existiam, "
                    "%s falharam", guid, len(videos), cont["gerado"],
                    cont["existia"], cont["falhou"])
        _set(status="concluido", concluido_em=time.time())
    except Exception as e:
        logger.exception("gerar_thumbs worker falhou: %s", guid)
        _set(status="erro", erro=str(e), concluido_em=time.time())


def _input_by_num(root: ET.Element, num: str | None) -> ET.Element | None:
    if num is None:
        return None
    return next(
        (i for i in root.findall("inputs/input") if i.get("number") == str(num)),
        None,
    )


def _input_by_key(root: ET.Element, key: str | None) -> ET.Element | None:
    k = (key or "").lower()
    if not k:
        return None
    return next(
        (i for i in root.findall("inputs/input") if (i.get("key") or "").lower() == k),
        None,
    )


def _find_palestrante_em(root: ET.Element, inp: ET.Element | None,
                          palestrantes: dict) -> tuple[str, ET.Element] | None:
    """Retorna (guid, input_elem_do_palestrante) se `inp` e um palestrante
    diretamente ou envelopa um via overlay interno."""
    if inp is None:
        return None
    k = (inp.get("key") or "").lower()
    if k in palestrantes:
        return (k, inp)
    for ov in inp.findall("overlay"):
        ov_key = (ov.get("key") or "").lower()
        if ov_key in palestrantes:
            target = _input_by_key(root, ov_key)
            if target is not None:
                return (ov_key, target)
    return None


def _basename(caminho: str) -> str:
    """Ultimo componente de um path, tolerante a separador Windows ou POSIX.

    Itens de List vem como path absoluto Windows (`A:\\...\\23.png`); pegar o
    nome com `os.path.basename` so funciona no separador do SO atual, entao
    quebramos manualmente nos dois.
    """
    return re.split(r"[\\/]", caminho.strip())[-1] if caminho else ""


def _parse_list_input(inp: ET.Element | None) -> tuple[list[dict], int | None]:
    """Le um input List (VideoList) do XML do vMix.

    Retorna (itens, indice_atual_0based). Cada item e
    {"path": <path absoluto>, "nome": <filename>, "kind": imagem|video|outro}.

    O item atual e identificado por `<item selected="true">`; se nenhum item
    tiver o atributo, cai pro atributo `selectedIndex` do input (que pode vir
    0-based ou 1-based dependendo da versao do vMix — normalizamos os dois).
    """
    if inp is None:
        return [], None
    lst = inp.find("list")
    if lst is None:
        # Estrutura inesperada — loga pra diagnosticar sem chutar.
        filhos = sorted({c.tag for c in inp})
        logger.warning("input List sem <list> (type=%s) — filhos=%s",
                        inp.get("type"), filhos)
        return [], None

    itens: list[dict] = []
    atual: int | None = None
    for i, it in enumerate(lst.findall("item")):
        caminho = (it.text or "").strip()
        nome = _basename(caminho) or caminho
        itens.append({"path": caminho, "nome": nome, "kind": _kind_de(nome)})
        if (it.get("selected") or "").strip().lower() == "true":
            atual = i

    if atual is None and itens:
        si = (inp.get("selectedIndex") or "").strip()
        if si.lstrip("-").isdigit():
            n = int(si)
            # vMix documenta SelectIndex 1-based pra List (confirmado no
            # preset .vmix), entao 1-based tem prioridade; 0-based e fallback.
            if 1 <= n <= len(itens):
                atual = n - 1
            elif 0 <= n < len(itens):
                atual = n

    return itens, atual


def _preview_palestrante(root: ET.Element, ativo_guid: str | None) -> tuple[str, int] | None:
    """Se o input em Preview do vMix for um palestrante configurado diferente
    do que esta no Program, retorna (nome, total_de_slides). Caso contrario, None.
    """
    preview_num = (root.findtext("preview") or "").strip()
    if not preview_num:
        return None
    preview_inp = _input_by_num(root, preview_num)
    achado = _find_palestrante_em(root, preview_inp, PALESTRANTES)
    if achado is None:
        return None
    guid_prev, inp_prev = achado
    if ativo_guid and guid_prev == ativo_guid:
        return None
    nome, _pasta, imagens, tipo = PALESTRANTES[guid_prev]
    if tipo == "list":
        # List le a playlist do XML — conta os itens do proprio input.
        itens, _ = _parse_list_input(inp_prev)
        return (nome, len(itens))
    return (nome, len(imagens))


def _estado_lista(base: dict, guid: str, nome: str, inp: ET.Element) -> dict:
    """Monta o estado quando o input ativo e um List (VideoList).

    A playlist (mistura de slides e videos) vem do XML. Itens de imagem sao
    servidos via /list-img/<guid>/<indice>. Itens de video, se o operador ja
    gerou os frames (botao no /admin → _thumbpresentation/), sao servidos via
    /list-thumb/<guid>/<indice> com a tag "VIDEO"; sem frame, viram card.
    Duracao/posicao so valem pro item ATUAL — o vMix nao expoe dos proximos.
    """
    itens, idx = _parse_list_input(inp)
    if not itens:
        return {**base, "ok": True, "ativo": False,
                "palestrante": nome, "tipo": "list",
                "mensagem": "Input List sem itens"}
    if idx is None:
        idx = 0

    atual = itens[idx]
    proximo = itens[idx + 1] if idx + 1 < len(itens) else None

    gq = urllib.parse.quote(guid)

    def _img_url(slot_idx: int, item: dict) -> str:
        # ?n=<nome> e so cache-buster (o endpoint ignora) — garante que o
        # browser nao reuse imagem velha se a List for editada no ar.
        return f"/list-img/{gq}/{slot_idx}?n={urllib.parse.quote(item['nome'])}"

    def _thumb_url(slot_idx: int, item: dict) -> str | None:
        # So retorna URL se o thumbnail ja foi gerado no disco.
        if _thumb_path(Path(item["path"])).is_file():
            return f"/list-thumb/{gq}/{slot_idx}?n={urllib.parse.quote(item['nome'])}"
        return None

    estado = {
        **base, "ok": True, "ativo": True,
        "palestrante": nome, "guid": guid, "tipo": "list",
        "indice": idx + 1, "total": len(itens),
        "atual_url": None, "proximo_url": None,
        "atual_video": None, "proximo_video": None,
    }

    if atual["kind"] == "imagem":
        estado["atual_url"] = _img_url(idx, atual)
    else:
        v = {"nome": atual["nome"], "kind": atual["kind"]}
        if atual["kind"] == "video":
            # Duracao: sidecar .dur (gerado pelo botao, vale pra qualquer
            # slot); fallback = atributo `duration` do vMix (so item atual).
            ms = _ler_dur(Path(atual["path"]))
            if ms is None:
                dv = (inp.get("duration") or "").strip()
                ms = int(dv) if dv.isdigit() and int(dv) > 0 else None
            if ms:
                v["duracao_ms"] = ms
            pos = (inp.get("position") or "").strip()
            if pos.isdigit():
                v["posicao_ms"] = int(pos)
            estado["atual_url"] = _thumb_url(idx, atual)
        estado["atual_video"] = v

    if proximo is not None:
        if proximo["kind"] == "imagem":
            estado["proximo_url"] = _img_url(idx + 1, proximo)
        else:
            pv = {"nome": proximo["nome"], "kind": proximo["kind"]}
            if proximo["kind"] == "video":
                ms = _ler_dur(Path(proximo["path"]))  # so do sidecar
                if ms:
                    pv["duracao_ms"] = ms
                estado["proximo_url"] = _thumb_url(idx + 1, proximo)
            estado["proximo_video"] = pv
    return estado


def compute_state() -> dict:
    prefs = get_ui_prefs()
    base = {"ui_prefs": prefs}
    try:
        root = fetch_vmix_xml()
    except Exception as e:
        return {**base, "ok": False,
                "erro": f"vMix inacessivel ({VMIX_HOST}:{VMIX_PORT}): {e}"}

    active_num = root.findtext("active")
    input_program = _input_by_num(root, active_num)

    def _prev_fields(ativo_guid):
        r = _preview_palestrante(root, ativo_guid)
        if r is None:
            return {"preview_palestrante": None, "preview_total": None}
        return {"preview_palestrante": r[0], "preview_total": r[1]}

    if input_program is None:
        return {**base, "ok": True, "ativo": False,
                "mensagem": "Sem input em Program",
                **_prev_fields(None)}

    achado = _find_palestrante_em(root, input_program, PALESTRANTES)

    if achado is None:
        for ov in root.findall("overlays/overlay"):
            inp_num = (ov.text or "").strip()
            if not inp_num:
                continue
            ov_inp = _input_by_num(root, inp_num)
            achado = _find_palestrante_em(root, ov_inp, PALESTRANTES)
            if achado is not None:
                break

    ativo_guid = achado[0] if achado else None

    if achado is None:
        return {**base, "ok": True, "ativo": False,
                "mensagem": "Nenhum slide de palestrante em Program",
                **_prev_fields(None)}

    guid, input_palestrante = achado
    nome, pasta_path, slides, tipo = PALESTRANTES[guid]

    # Input List (VideoList): playlist vem do XML, nao de pasta. Detecta pelo
    # tipo configurado ou pelo `type` do proprio input no vMix.
    input_type = input_palestrante.get("type") or ""
    if tipo == "list" or input_type in ("VideoList", "List"):
        return {**_estado_lista(base, guid, nome, input_palestrante),
                **_prev_fields(ativo_guid)}

    title = input_palestrante.get("title", "")

    idx = match_filename(title, slides)
    if idx is None:
        return {**base, "ok": True, "ativo": False, "palestrante": nome,
                "mensagem": f"Slide atual ('{title}') nao bateu com arquivos da pasta",
                **_prev_fields(ativo_guid)}

    atual = slides[idx]
    proximo = slides[idx + 1] if idx + 1 < len(slides) else None

    def url_img(arq: str) -> str:
        return f"/img/{urllib.parse.quote(guid)}/{urllib.parse.quote(arq)}"

    return {
        **base,
        "ok": True, "ativo": True,
        "palestrante": nome,
        "guid": guid,
        "indice": idx + 1,
        "total": len(slides),
        "atual_url": url_img(atual),
        "proximo_url": url_img(proximo) if proximo else None,
        **_prev_fields(ativo_guid),
    }


# -------------------- Diagnostico por palestrante --------------------

def diagnosticar_palestrante(
    guid: str, nome: str, pasta: str, root: ET.Element
) -> dict:
    """Retorna diagnostico estruturado de um palestrante contra o XML atual.

    Status possiveis:
    - "ok"                — GUID existe, pasta com imagens, filename atual bate
    - "guid_orfao"        — input com esse GUID nao existe mais no vMix
    - "pasta_inacessivel" — pasta nao e um diretorio no disco
    - "sem_imagens"       — pasta existe mas nao tem arquivos de imagem
    - "filename_mismatch" — title do vMix nao bate com nenhum arquivo da pasta
    - "sem_pasta"         — pasta vazia (usado pelo endpoint /validate quando
                            o operador ainda nao escolheu a pasta)
    """
    guid_low = (guid or "").lower().strip()
    out: dict = {
        "guid": guid_low,
        "nome": nome,
        "status": "ok",
        "detalhe": "",
        "num_input_atual": None,
        "shorttitle_atual": None,
        "title_atual": None,
        "total_no_vmix": None,
        "total_na_pasta": None,
    }

    inp = _input_by_key(root, guid_low)
    if inp is None:
        out["status"] = "guid_orfao"
        out["detalhe"] = "input com este GUID nao existe no vMix atual"
        return out

    out["num_input_atual"] = int(inp.get("number") or 0) or None
    out["shorttitle_atual"] = inp.get("shortTitle") or inp.get("title") or ""
    out["title_atual"] = inp.get("title") or ""
    try:
        out["total_no_vmix"] = int(inp.get("duration") or 0) or None
    except ValueError:
        pass

    # Input List: diagnostico le a playlist do XML, nao depende de pasta.
    if (inp.get("type") or "") in ("VideoList", "List"):
        itens, idx = _parse_list_input(inp)
        out["total_na_pasta"] = len(itens)
        if not itens:
            out["status"] = "sem_imagens"
            out["detalhe"] = "input List sem itens"
        else:
            imgs = sum(1 for x in itens if x["kind"] == "imagem")
            vids = sum(1 for x in itens if x["kind"] == "video")
            pos = (idx + 1) if idx is not None else "?"
            out["status"] = "ok"
            out["detalhe"] = (f"List: {len(itens)} itens — {imgs} imagens, "
                              f"{vids} videos (item atual #{pos})")
        return out

    # pasta vazia → so verificou GUID
    pasta_raw = (pasta or "").strip()
    if not pasta_raw:
        out["status"] = "sem_pasta"
        out["detalhe"] = "pasta nao informada — validacao parcial"
        return out

    pasta_path = Path(pasta_raw)
    if not pasta_path.is_absolute():
        pasta_path = (APP_DIR / pasta_raw).resolve()
    if not pasta_path.is_dir():
        out["status"] = "pasta_inacessivel"
        out["detalhe"] = f"pasta nao existe: {pasta_path}"
        return out

    try:
        imagens = sorted(
            (x.name for x in pasta_path.iterdir() if x.is_file() and _is_image(x)),
            key=_natural_key,
        )
    except (PermissionError, OSError) as e:
        out["status"] = "pasta_inacessivel"
        out["detalhe"] = f"erro lendo pasta: {e}"
        return out

    out["total_na_pasta"] = len(imagens)

    if not imagens:
        out["status"] = "sem_imagens"
        out["detalhe"] = (
            f"nenhuma imagem encontrada "
            f"(formatos aceitos: {', '.join(IMAGE_EXTS)})"
        )
        return out

    title = inp.get("title") or ""
    idx = match_filename(title, imagens)
    if idx is None:
        out["status"] = "filename_mismatch"
        out["detalhe"] = (
            f"title do vMix ('{title}') nao bate com nenhum arquivo da pasta"
        )
        return out

    out["status"] = "ok"
    out["detalhe"] = f"arquivo atual: {imagens[idx]} (#{idx + 1} de {len(imagens)})"
    return out


def diagnosticar_todos() -> list[dict]:
    """Roda `diagnosticar_palestrante` para todos os palestrantes do config.

    Se o vMix nao responder, retorna lista de diagnosticos com status 'vmix_offline'.
    """
    try:
        root = fetch_vmix_xml()
    except Exception as e:
        return [{
            "guid": (p.get("guid") or "").lower(),
            "nome": p.get("nome", ""),
            "status": "vmix_offline",
            "detalhe": f"vMix inacessivel: {e}",
        } for p in CFG.get("palestrantes", [])]

    out: list[dict] = []
    for p in CFG.get("palestrantes", []):
        out.append(diagnosticar_palestrante(
            p.get("guid", ""), p.get("nome", ""), p.get("pasta", ""), root
        ))
    return out

# -------------------- HTTP handler --------------------

class Handler(http.server.BaseHTTPRequestHandler):
    # Timeout do socket — sem isso, um cliente que declara Content-Length
    # maior que o corpo real (ou trava no meio) penduraria a thread pra sempre.
    timeout = 30

    def log_message(self, fmt, *args) -> None:
        try:
            msg = fmt % args if args else fmt
        except Exception:
            msg = fmt
        s = str(msg)
        # Silencia ruido: polling a 500ms (/state, /health) e leituras frequentes
        # (/ls, GET /config). POST /config continua visivel porque e escrita.
        if ("/state" in s or "/admin/api/ls" in s
                or "/admin/api/health" in s
                or "/admin/api/clientes" in s
                or "/admin/api/vmix_xml" in s
                or "/admin/api/preview" in s
                or "/admin/api/projetores" in s
                or "GET /admin/api/ui_prefs" in s
                or "GET /admin/api/monitors" in s
                or "GET /admin/api/config" in s
                or "/admin/api/gerar_thumbs/status" in s):
            return
        # Encaminha pro logger (console + arquivo com rotacao)
        if logger.handlers:
            logger.info("%s - %s", self.address_string(), s)
        else:
            super().log_message(fmt, *args)

    def _send_json(self, obj: dict, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str | None = None, cache: bool = True) -> None:
        """Serve arquivo em streaming (64KB chunks) — nao carrega tudo em RAM.

        Fase 5: importante para slides grandes (20-50MB) com multiplos clientes.
        """
        if not path.is_file():
            self.send_error(404)
            return
        try:
            size = path.stat().st_size
        except OSError:
            self.send_error(404)
            return
        if content_type is None:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "public, max-age=300" if cache else "no-store")
        self.end_headers()
        try:
            with open(path, "rb") as f:
                import shutil as _sh
                _sh.copyfileobj(f, self.wfile, length=64 * 1024)
        except (BrokenPipeError, ConnectionResetError):
            # Cliente fechou conexao no meio da transferencia — normal
            return

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path in ("/", "/index.html"):
            self._send_file(INDEX_PATH, "text/html; charset=utf-8", cache=False)
            return

        if path == "/state":
            registrar_cliente(self.client_address[0] if self.client_address else "")
            self._send_json(compute_state())
            return

        if path in ("/admin", "/admin/"):
            self._send_file(ADMIN_PATH, "text/html; charset=utf-8", cache=False)
            return

        if path.startswith("/admin/api/"):
            self._handle_admin_get(path[len("/admin/api/"):], parsed.query)
            return

        if path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return

        if path.startswith("/img/"):
            rel = path[len("/img/"):]
            parts = rel.split("/", 1)
            if len(parts) != 2:
                self.send_error(404)
                return
            guid, arq = parts[0].lower(), parts[1]
            info = PALESTRANTES.get(guid)
            if info is None:
                self.send_error(404)
                return
            pasta_path = info[1]
            if pasta_path is None:
                # palestrante tipo List nao tem pasta — usa /list-img/
                self.send_error(404)
                return
            candidate = (pasta_path / arq).resolve()
            try:
                candidate.relative_to(pasta_path.resolve())
            except ValueError:
                self.send_error(403)
                return
            # Fase 2: se arquivo sumiu depois do load, re-escaneia antes de 404
            if not candidate.is_file():
                rescan_pasta(guid)
                if not candidate.is_file():
                    self._send_json({
                        "error": "arquivo_removido",
                        "detalhe": f"'{arq}' nao existe mais na pasta do palestrante",
                    }, status=410)
                    return
            self._send_file(candidate)
            return

        if path.startswith("/list-img/"):
            # Serve a imagem de um item de um input List, por indice.
            # O path vem da propria playlist do vMix (confiavel); so o indice
            # e input do usuario, e fica preso ao range da lista viva.
            rel = path[len("/list-img/"):]
            parts = rel.split("/", 1)
            if len(parts) != 2:
                self.send_error(404)
                return
            guid = parts[0].lower()
            info = PALESTRANTES.get(guid)
            if info is None or info[3] != "list":
                self.send_error(404)
                return
            try:
                slot = int(parts[1])
            except ValueError:
                self.send_error(404)
                return
            try:
                root = fetch_vmix_xml()
            except Exception:
                self.send_error(502)
                return
            itens, _ = _parse_list_input(_input_by_key(root, guid))
            if slot < 0 or slot >= len(itens):
                self.send_error(404)
                return
            item = itens[slot]
            if item["kind"] != "imagem":
                self.send_error(404)  # item de video nao tem imagem
                return
            candidate = Path(item["path"])
            if not candidate.is_file():
                self.send_error(404)
                return
            # cache=False: arquivo local (mesma maquina do vMix), rapido, e
            # evita servir imagem velha se a List for reordenada no ar.
            self._send_file(candidate, cache=False)
            return

        if path.startswith("/list-thumb/"):
            # Serve o frame pre-gerado de um item de video de um input List.
            # Thumbnail vive em <pasta-do-video>/_thumbpresentation/<nome>.jpg
            # (gerado pelo botao do /admin). 404 se ainda nao foi gerado.
            rel = path[len("/list-thumb/"):]
            parts = rel.split("/", 1)
            if len(parts) != 2:
                self.send_error(404)
                return
            guid = parts[0].lower()
            info = PALESTRANTES.get(guid)
            if info is None or info[3] != "list":
                self.send_error(404)
                return
            try:
                slot = int(parts[1])
            except ValueError:
                self.send_error(404)
                return
            try:
                root = fetch_vmix_xml()
            except Exception:
                self.send_error(502)
                return
            itens, _ = _parse_list_input(_input_by_key(root, guid))
            if slot < 0 or slot >= len(itens):
                self.send_error(404)
                return
            item = itens[slot]
            if item["kind"] != "video":
                self.send_error(404)
                return
            thumb = _thumb_path(Path(item["path"]))
            if not thumb.is_file():
                self.send_error(404)  # frame ainda nao gerado
                return
            self._send_file(thumb, "image/jpeg", cache=False)
            return

        self.send_error(404)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path.startswith("/admin/api/"):
            self._handle_admin_post(path[len("/admin/api/"):])
            return

        self.send_error(404)

    # -------------------- Admin API --------------------

    def _handle_admin_get(self, sub: str, query: str) -> None:
        if sub == "config":
            # Instalacao nova ainda nao tem config.json (ele e criado no 1o
            # save). Nesse caso devolve o CFG em memoria (default) — 200, nao
            # 500 — senao o /admin nem consegue salvar o 1o palestrante.
            try:
                if CONFIG_PATH.is_file():
                    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                        self._send_json(json.load(f))
                else:
                    self._send_json(CFG)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if sub == "roots":
            try:
                self._send_json({"roots": get_roots()})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if sub == "ls":
            qs = urllib.parse.parse_qs(query)
            p = qs.get("path", [""])[0].strip()
            if not p:
                # Tela inicial: drives + atalhos (raizes detectadas)
                self._send_json({
                    "drives": list_drives(),
                    "shortcuts": get_roots(),
                    "items": [],
                })
                return
            try:
                self._send_json(list_dir(p))
            except FileNotFoundError as e:
                self._send_json({"error": str(e)}, status=404)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if sub == "health":
            try:
                self._send_json({"diagnosticos": diagnosticar_todos()})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if sub == "gerar_thumbs/status":
            # Polling do progresso do job de geracao de thumbs (modal /admin).
            qs = urllib.parse.parse_qs(query)
            guid = qs.get("guid", [""])[0].strip().lower()
            if not guid:
                self._send_json({"ok": False, "erro": "guid obrigatorio"}, status=400)
                return
            with _thumbs_jobs_lock:
                job = _thumbs_jobs.get(guid)
                job = dict(job) if job else None
            if job is None:
                self._send_json({"ok": True, "status": "inexistente"})
                return
            self._send_json({"ok": True, **job})
            return

        if sub == "clientes":
            self._send_json({"clientes": clientes_ativos(janela_s=30)})
            return

        if sub == "ui_prefs":
            self._send_json(get_ui_prefs())
            return

        if sub == "monitors":
            try:
                self._send_json({"monitors": list_monitors()})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if sub == "projetores":
            try:
                self._send_json({"abertos": PROJETOR_MANAGER.abertos()})
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if sub == "vmix_xml":
            # Proxy do XML bruto do vMix — fallback pro admin quando CORS
            # direto nao funciona (vMix em outra maquina, rede restrita etc).
            try:
                url = f"http://{VMIX_HOST}:{VMIX_PORT}/api"
                with urllib.request.urlopen(url, timeout=3) as resp:
                    data = resp.read()
            except Exception as e:
                self._send_json({"error": f"vMix inacessivel: {e}"}, status=502)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/xml; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return

        if sub == "preview":
            qs = urllib.parse.parse_qs(query)
            p = qs.get("pasta", [""])[0].strip()
            if not p:
                self._send_json({"error": "parametro 'pasta' obrigatorio"}, status=400)
                return
            try:
                self._send_json(listar_preview(p))
            except FileNotFoundError as e:
                self._send_json({"error": str(e)}, status=404)
            except PermissionError as e:
                self._send_json({"error": str(e)}, status=403)
            except Exception as e:
                self._send_json({"error": str(e)}, status=500)
            return

        if sub == "preview/img":
            qs = urllib.parse.parse_qs(query)
            p = qs.get("pasta", [""])[0].strip()
            arq = qs.get("arq", [""])[0].strip()
            if not p or not arq:
                self.send_error(400)
                return
            try:
                caminho = preview_img_path(p, arq)
            except FileNotFoundError:
                self.send_error(404)
                return
            except PermissionError:
                self.send_error(403)
                return
            self._send_file(caminho)
            return

        if sub == "validate":
            qs = urllib.parse.parse_qs(query)
            guid = qs.get("guid", [""])[0].strip()
            pasta = qs.get("pasta", [""])[0].strip()
            nome = qs.get("nome", [""])[0].strip() or "?"
            if not guid:
                self._send_json({"error": "parametro 'guid' obrigatorio"}, status=400)
                return
            try:
                root = fetch_vmix_xml()
            except Exception as e:
                self._send_json({
                    "status": "vmix_offline",
                    "detalhe": f"vMix inacessivel: {e}",
                }, status=200)
                return
            self._send_json(diagnosticar_palestrante(guid, nome, pasta, root))
            return

        self.send_error(404)

    def _handle_admin_post(self, sub: str) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self._send_json({"ok": False, "error": "Content-Length invalido"}, status=400)
            return
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except Exception as e:
            self._send_json({"ok": False, "error": f"JSON invalido: {e}"}, status=400)
            return
        # Body precisa ser objeto JSON. Lista/string/numero quebrariam o
        # `(payload or {}).get(...)` dos handlers com AttributeError -> 500 cru.
        if payload is not None and not isinstance(payload, dict):
            self._send_json({"ok": False, "error": "payload deve ser um objeto JSON"},
                             status=400)
            return

        if sub == "ui_prefs":
            try:
                salvar_ui_prefs(payload or {})
                self._send_json({"ok": True, "ui_prefs": get_ui_prefs()})
            except ValueError as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
            return

        if sub == "gerar_thumbs":
            # Botao "Gerar frames dos videos" do modal — inicia a geracao em
            # background e retorna na hora; /admin faz polling de gerar_thumbs/status.
            guid = (payload or {}).get("guid", "").strip().lower()
            if not guid:
                self._send_json({"ok": False, "erro": "guid obrigatorio"}, status=400)
                return
            if not _FFMPEG:
                self._send_json({"ok": False, "erro": "ffmpeg nao encontrado",
                                 "sem_ffmpeg": True})
                return
            with _thumbs_jobs_lock:
                atual = _thumbs_jobs.get(guid)
                if atual and atual["status"] == "rodando":
                    # ja ha job rodando pra esse guid — nao duplica
                    self._send_json({"ok": True, "ja_rodando": True, "job": atual})
                    return
                _thumbs_jobs[guid] = _novo_job_thumbs(guid)
            threading.Thread(target=_thumbs_worker, args=(guid,),
                             name=f"thumbs_{guid[:8]}", daemon=True).start()
            self._send_json({"ok": True, "iniciado": True})
            return

        if sub == "projetor_abrir":
            monitor_idx = (payload or {}).get("monitor_idx")
            if monitor_idx is None:
                self._send_json({"ok": False, "error": "monitor_idx obrigatorio"},
                                 status=400)
                return
            try:
                monitores = list_monitors()
                monitor = next((m for m in monitores if m["indice"] == monitor_idx), None)
                if not monitor:
                    self._send_json({"ok": False, "error": f"monitor {monitor_idx} nao encontrado"},
                                     status=404)
                    return
                # URL interna do proprio server — modo kiosk
                url = f"http://localhost:{SERVER_PORT}/?kiosk=1"
                pid = PROJETOR_MANAGER.abrir(monitor, url)
                self._send_json({"ok": True, "pid": pid, "monitor": monitor})
            except (RuntimeError, OSError) as e:
                # RuntimeError = browser nao achado; OSError = falha no Popen
                self._send_json({"ok": False, "error": str(e)}, status=500)
            return

        if sub == "projetor_fechar":
            pid = (payload or {}).get("pid")
            if pid == "todos":
                n = PROJETOR_MANAGER.fechar_todos()
                self._send_json({"ok": True, "fechados": n})
                return
            if not isinstance(pid, int):
                self._send_json({"ok": False, "error": "pid invalido"}, status=400)
                return
            ok = PROJETOR_MANAGER.fechar(pid)
            self._send_json({"ok": ok})
            return

        if sub == "vmix_control":
            # Aceita {action: "next|prev|goto|reset", guid: "...", index: N}
            action = (payload or {}).get("action", "").lower()
            guid = (payload or {}).get("guid", "").strip().lower()
            if guid and guid not in PALESTRANTES:
                self._send_json({"ok": False, "error": "guid nao configurado"}, status=400)
                return
            info = PALESTRANTES.get(guid)
            tipo = info[3] if info else "photos"
            total = len(info[2]) if info else 0

            # Input List nao tem NextPicture/PreviousPicture — vmix_list_control
            # traduz next/prev pra SelectIndex lendo o indice atual no vMix.
            if tipo == "list" and action in ("next", "prev"):
                r = vmix_list_control(guid, action)
                self._send_json(r, status=200 if r.get("ok") else 502)
                return

            # List: total real vem da playlist viva (info[2] e [] pra list) —
            # senao a checagem de range do `goto` ficaria desligada.
            if tipo == "list" and action == "goto":
                try:
                    itens, _ = _parse_list_input(_input_by_key(fetch_vmix_xml(), guid))
                    total = len(itens)
                except Exception:
                    total = 0

            try:
                if action == "next":
                    r = vmix_control("NextPicture", guid)
                elif action == "prev":
                    r = vmix_control("PreviousPicture", guid)
                elif action == "reset":
                    r = vmix_control("SelectIndex", guid, "1")
                elif action == "goto":
                    try:
                        idx = int((payload or {}).get("index", 0))
                    except (TypeError, ValueError):
                        self._send_json({"ok": False, "error": "index invalido"}, status=400)
                        return
                    if idx < 1 or (total and idx > total):
                        self._send_json({
                            "ok": False,
                            "error": f"index fora do range (1 a {total or '?'})",
                        }, status=400)
                        return
                    r = vmix_control("SelectIndex", guid, str(idx))
                else:
                    self._send_json({"ok": False, "error": "acao invalida"}, status=400)
                    return
            except ValueError as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
                return

            status = 200 if r.get("ok") else 502
            self._send_json(r, status=status)
            return

        if sub == "config":
            try:
                salvar_config(payload)
                self._send_json({"ok": True, "palestrantes": len(PALESTRANTES)})
            except ValueError as e:
                # validar_config levantou com ("config_invalida", [erros])
                if len(e.args) >= 2 and e.args[0] == "config_invalida":
                    self._send_json({
                        "ok": False,
                        "error": "config_invalida",
                        "erros": e.args[1],
                    }, status=400)
                else:
                    self._send_json({"ok": False, "error": str(e)}, status=400)
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
            return

        self.send_error(404)


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        """Silencia tracebacks de cliente que desconectou no meio da resposta.

        Browser fechado / F5 durante o polling de 500ms aborta a conexao
        (BrokenPipe / ConnectionReset / ConnectionAborted no Windows). E ruido
        normal — nao e erro do servidor. Demais excecoes seguem logando.
        """
        if isinstance(sys.exc_info()[1], ConnectionError):
            return
        super().handle_error(request, client_address)


# -------------------- Resiliencia: port fallback + single instance --------------------

def bind_com_fallback(porta_preferida: int, max_tentativas: int = 10) -> tuple[int, ThreadingServer]:
    """Tenta fazer bind na porta preferida; se ocupada, tenta as seguintes.

    Retorna (porta_usada, server). Levanta OSError se todas estiverem ocupadas.
    """
    ultimo_erro: Exception | None = None
    for i in range(max_tentativas):
        porta = porta_preferida + i
        try:
            srv = ThreadingServer(("", porta), Handler)
            return porta, srv
        except OSError as e:
            ultimo_erro = e
            continue
    raise OSError(
        f"Todas as portas de {porta_preferida} a "
        f"{porta_preferida + max_tentativas - 1} estao ocupadas"
    ) from ultimo_erro


# -------------------- Multi-monitor + projetores --------------------

def list_monitors() -> list[dict]:
    """Enumera monitores do Windows via EnumDisplayMonitors (ctypes stdlib).

    Retorna lista de dicts com: indice, nome, x, y, width, height, primario.
    Em ambientes nao-Windows, retorna um monitor 'virtual' padrao pro teste
    nao quebrar em CI Linux.
    """
    if sys.platform != "win32":
        return [{"indice": 0, "nome": "DISPLAY1 (virtual)",
                  "x": 0, "y": 0, "width": 1920, "height": 1080,
                  "primario": True}]

    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                     ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD),
                     ("rcMonitor", RECT),
                     ("rcWork", RECT),
                     ("dwFlags", wintypes.DWORD),
                     ("szDevice", wintypes.WCHAR * 32)]

    MONITORINFOF_PRIMARY = 0x00000001
    user32 = ctypes.windll.user32

    monitores: list[dict] = []

    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
        ctypes.POINTER(RECT), wintypes.LPARAM,
    )

    def _cb(hmon, hdc, rect_ptr, lparam):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(info)
        user32.GetMonitorInfoW(hmon, ctypes.byref(info))
        r = info.rcMonitor
        monitores.append({
            "indice": len(monitores),
            "nome": info.szDevice or f"DISPLAY{len(monitores) + 1}",
            "x": r.left,
            "y": r.top,
            "width": r.right - r.left,
            "height": r.bottom - r.top,
            "primario": bool(info.dwFlags & MONITORINFOF_PRIMARY),
        })
        return 1

    user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(_cb), 0)
    return monitores or [{"indice": 0, "nome": "DISPLAY1",
                          "x": 0, "y": 0, "width": 1920, "height": 1080,
                          "primario": True}]


def _achar_browser_kiosk() -> str | None:
    """Localiza executavel do Chrome ou Edge pra abrir em modo kiosk."""
    candidatos = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    ]
    for c in candidatos:
        if os.path.isfile(c):
            return c
    return None


class ProjetorManager:
    """Gerencia projetores (janelas de browser em modo kiosk espalhadas nos
    monitores). Rastreia processos pra permitir fechar remotamente.
    """

    def __init__(self):
        self._abertos: dict[int, dict] = {}  # pid -> {proc, monitor, url, aberto_em}
        self._lock = threading.Lock()

    def abrir(self, monitor: dict, url: str) -> int | None:
        """Lanca browser em modo kiosk no monitor indicado. Retorna pid."""
        browser = _achar_browser_kiosk()
        if not browser:
            raise RuntimeError("Chrome nem Edge encontrado — instale um deles")

        # Um diretorio de usuario temporario por instancia evita reutilizar
        # sessao do Chrome normal e garante que a flag --app funcione fresh.
        user_data = os.path.join(os.environ.get("TEMP", "."),
                                  f"apresentador_kiosk_{monitor['indice']}")
        args = [
            browser,
            "--new-window",
            f"--app={url}",
            f"--window-position={monitor['x']},{monitor['y']}",
            f"--window-size={monitor['width']},{monitor['height']}",
            "--start-fullscreen",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={user_data}",
        ]
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=0x08000000 if sys.platform == "win32" else 0,  # CREATE_NO_WINDOW
        )
        with self._lock:
            self._abertos[proc.pid] = {
                "proc": proc,
                "pid": proc.pid,
                "monitor": monitor,
                "url": url,
                "aberto_em": time.time(),
            }
        return proc.pid

    def fechar(self, pid: int) -> bool:
        with self._lock:
            entry = self._abertos.pop(pid, None)
        if not entry:
            return False
        try:
            entry["proc"].terminate()
            entry["proc"].wait(timeout=3)
        except Exception:
            try:
                entry["proc"].kill()
            except Exception:
                pass
        return True

    def fechar_todos(self) -> int:
        with self._lock:
            pids = list(self._abertos.keys())
        n = 0
        for pid in pids:
            if self.fechar(pid):
                n += 1
        return n

    def gc(self) -> None:
        """Remove do tracking processos que morreram (crash, usuario fechou)."""
        with self._lock:
            mortos = [pid for pid, e in self._abertos.items()
                      if e["proc"].poll() is not None]
            for pid in mortos:
                self._abertos.pop(pid, None)

    def abertos(self) -> list[dict]:
        self.gc()
        with self._lock:
            return [
                {"pid": e["pid"], "monitor": e["monitor"],
                 "url": e["url"], "aberto_em": e["aberto_em"]}
                for e in self._abertos.values()
            ]


PROJETOR_MANAGER = ProjetorManager()


class SingleInstance:
    """Wrapper simples pra CreateMutex do Windows.

    Se o mutex ja existe, `adquirido` e False e o caller deve sair.
    Fora do Windows, sempre retorna True (sem enforcement).
    """

    def __init__(self, nome: str):
        self.nome = nome
        self.handle = None
        self.adquirido = False
        if sys.platform != "win32":
            self.adquirido = True
            return
        try:
            import ctypes
            from ctypes import wintypes
            ERROR_ALREADY_EXISTS = 183
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexW.argtypes = [
                ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR
            ]
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            self.handle = kernel32.CreateMutexW(None, False, nome)
            last = kernel32.GetLastError()
            if last == ERROR_ALREADY_EXISTS:
                self.adquirido = False
            else:
                self.adquirido = True
        except Exception:
            # Em caso de falha do Windows API, nao bloqueia o app
            self.adquirido = True

    def release(self) -> None:
        if self.handle and sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self.handle)
            except Exception:
                pass
            self.handle = None


def aquirir_single_instance(nome: str = "ApresentadorVmixSingleton") -> SingleInstance:
    """Helper que instancia SingleInstance. Exposta pra testes."""
    return SingleInstance(nome)


def http_self_check(porta: int, timeout: float = 1.0) -> bool:
    """Tenta GET http://localhost:porta/state. Retorna True se HTTP 200."""
    url = f"http://localhost:{porta}/state"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


class ConfigWatcher:
    """Poll do mtime do config.json e recarrega se detectar edicao externa.

    Chamadas de salvar_config() atualizam _last_known_mtime logo depois,
    pra evitar loop infinito (nossa propria escrita nao deve ser tratada
    como mudanca externa).
    """

    POLL_S = 1.0

    def __init__(self):
        self._stop = threading.Event()
        self._last_known_mtime: float = 0.0
        self.mudancas_detectadas = 0
        try:
            self._last_known_mtime = CONFIG_PATH.stat().st_mtime
        except OSError:
            pass

    def marcar_escrita_nossa(self) -> None:
        """Chamar logo apos salvar_config()/salvar_ui_prefs() pra nao
        interpretar a propria escrita como edicao externa."""
        try:
            self._last_known_mtime = CONFIG_PATH.stat().st_mtime
        except OSError:
            pass

    def start(self) -> None:
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        global CFG, VMIX_HOST, VMIX_PORT, PALESTRANTES
        while not self._stop.wait(self.POLL_S):
            try:
                mtime = CONFIG_PATH.stat().st_mtime
            except OSError:
                continue
            if mtime != self._last_known_mtime and self._last_known_mtime > 0:
                logger.info("config.json modificado externamente — recarregando")
                try:
                    with _cfg_lock:
                        novo = carregar_config()
                        CFG = novo
                        VMIX_HOST = CFG.get("vmix", {}).get("host", "localhost")
                        VMIX_PORT = int(CFG.get("vmix", {}).get("port", 8088))
                        PALESTRANTES = carregar_palestrantes(CFG)
                    self.mudancas_detectadas += 1
                except Exception as e:
                    logger.error("erro recarregando config: %s", e)
                self._last_known_mtime = mtime
            elif self._last_known_mtime == 0:
                self._last_known_mtime = mtime


def _ip_lan() -> str | None:
    """Descobre IP da maquina na rede local (pro URL que o palestrante acessa).

    Truque classico: abre socket UDP para um IP publico qualquer, nao envia nada,
    e le o endereco local escolhido pelo SO.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


_server_ref: "ThreadingServer | None" = None


def _shutdown_server() -> None:
    """Para o HTTP server limpo + fecha projetores abertos. Chamado pelo tray."""
    global _server_ref
    try:
        PROJETOR_MANAGER.fechar_todos()
    except Exception:
        pass
    if _server_ref is not None:
        try:
            _server_ref.shutdown()
            _server_ref.server_close()
        except Exception:
            pass
        _server_ref = None


_single_instance: "SingleInstance | None" = None


def main() -> None:
    setup_logging(verbose=True)

    # Single-instance: evita 2 copias do app rodando simultaneamente.
    global _single_instance
    _single_instance = aquirir_single_instance()
    if not _single_instance.adquirido:
        print("=" * 68)
        print("  Apresentador vMix ja esta rodando.")
        print("  Procure o icone na bandeja do Windows (perto do relogio).")
        print("  Se nao aparecer, mate o processo no Gerenciador de Tarefas.")
        print("=" * 68)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                "O Apresentador vMix já está rodando.\n\n"
                "Procure o ícone na bandeja do Windows (perto do relógio).",
                "Apresentador vMix",
                0x40,  # MB_ICONINFORMATION
            )
        except Exception:
            pass
        return

    global _server_ref, SERVER_PORT

    # Tenta bindar porta com fallback antes de imprimir banner,
    # pra que o banner mostre a porta real.
    try:
        porta_real, srv = bind_com_fallback(SERVER_PORT, max_tentativas=10)
    except OSError as e:
        logger.error("Nao consegui bindar porta: %s", e)
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Não foi possível iniciar — todas as portas de {SERVER_PORT} a "
                f"{SERVER_PORT + 9} estão ocupadas.\n\n"
                "Feche outras instâncias ou altere 'server_port' no config.json.",
                "Apresentador vMix",
                0x10,
            )
        except Exception:
            pass
        return

    if porta_real != SERVER_PORT:
        logger.warning("Porta %s ocupada — usando %s", SERVER_PORT, porta_real)
        SERVER_PORT = porta_real
    _server_ref = srv

    ip_lan = _ip_lan()
    print("=" * 68)
    print("  Modo Apresentador - app-presentation-png-vmix")
    print("=" * 68)
    print(f"  vMix:         http://{VMIX_HOST}:{VMIX_PORT}/api")
    print(f"  Admin:        http://localhost:{SERVER_PORT}/admin")
    if ip_lan:
        print(f"  Palestrante:  http://{ip_lan}:{SERVER_PORT}/")
        print(f"                (use esta URL no tablet do palestrante)")
    else:
        print(f"  Palestrante:  http://localhost:{SERVER_PORT}/")
    print(f"  Logs:         {LOG_DIR}")
    print("=" * 68)
    if PALESTRANTES:
        print("  Palestrantes carregados:")
        for guid, (nome, pasta, slides, tipo) in PALESTRANTES.items():
            if tipo == "list":
                print(f"    {nome}: List (playlist vem do vMix em runtime)")
            else:
                print(f"    {nome}: {pasta.name} ({len(slides)} imagens)")
    else:
        print("  Nenhum palestrante configurado — abrindo o Dashboard admin")
        print("  pra voce configurar. Depois, recarregue no navegador.")
    print("=" * 68)

    # Sem auto-abrir browser — app roda discreto no tray.
    # Operador abre manualmente via "Abrir Dashboard" / "Abrir Modo Apresentador"
    # no menu do tray, ou pela URL mostrada no banner.

    def _run_srv() -> None:
        try:
            srv.serve_forever()
        except Exception as e:
            logger.error("HTTP server parou: %s", e)

    server_thread = threading.Thread(target=_run_srv, daemon=True)
    server_thread.start()

    # File watcher do config.json — recarrega se alguem editar externamente
    global _config_watcher
    _config_watcher = ConfigWatcher()
    _config_watcher.start()

    # Tray: tenta subir o icone na bandeja. Se falhar (sem display, lib ausente
    # em dev), cai em modo "bloqueia na main thread" como antes.
    try:
        import tray as _tray
        _tray.rodar_tray(sys.modules[__name__], shutdown_fn=_shutdown_server)
    except ImportError:
        logger.info("pystray nao disponivel — rodando sem tray icon (Ctrl+C pra sair)")
        try:
            server_thread.join()
        except KeyboardInterrupt:
            print("\nEncerrando.")
            _shutdown_server()
    except Exception as e:
        logger.error("tray falhou: %s — rodando sem tray", e)
        try:
            server_thread.join()
        except KeyboardInterrupt:
            print("\nEncerrando.")
            _shutdown_server()


if __name__ == "__main__":
    main()
