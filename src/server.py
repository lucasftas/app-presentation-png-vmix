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
import re
import socket
import socketserver
import string
import sys
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import xml.etree.ElementTree as ET
from pathlib import Path

# -------------------- Constantes globais --------------------

# Formatos de imagem aceitos pelo vMix (Photos/ImageList).
# Fonte: dialogo de arquivos do vMix — "*.JPG;*.BMP;*.PNG;*.GIF;*.JPEG;*.WEBP".
IMAGE_EXTS: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")

_NAT_RE = re.compile(r"(\d+)")


def _natural_key(s: str) -> list:
    """Chave de sort natural: `slide 2.png` antes de `slide 10.png`.

    Quebra a string em tokens alternados texto/numero e converte os numericos
    para int para comparacao correta.
    """
    return [int(t) if t.isdigit() else t.lower() for t in _NAT_RE.split(s)]


def _is_image(p: Path) -> bool:
    return p.suffix.lower() in IMAGE_EXTS


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
    """Pasta onde o .exe/script esta (onde config.json e index.html ficam)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

APP_DIR = app_dir()
_RECURSOS_DIR = APP_DIR / "recursos"


def _asset_path(name: str) -> Path:
    """Busca asset em recursos/ (pasta portable) ou APP_DIR (dev mode)."""
    candidato = _RECURSOS_DIR / name
    return candidato if candidato.is_file() else APP_DIR / name


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
            return json.load(f)
    except json.JSONDecodeError as e:
        backup = CONFIG_PATH.with_suffix(".bak.json")
        try:
            CONFIG_PATH.replace(backup)
            print(f"[ERRO] config.json corrompido ({e}) — "
                  f"movido para {backup.name}, iniciando com config vazia.",
                  file=sys.stderr)
        except OSError as move_err:
            print(f"[ERRO] config.json corrompido e nao consegui fazer backup: {move_err}",
                  file=sys.stderr)
        return _config_default()
    except OSError as e:
        print(f"[ERRO] falha lendo config.json: {e} — usando config vazia",
              file=sys.stderr)
        return _config_default()


def carregar_palestrantes(cfg: dict) -> dict:
    """Retorna {guid: (nome, pasta_path, [imagens_ordenadas_natural])}.

    Aceita PNG, JPG, JPEG, BMP, GIF, WEBP. Ordenacao natural (slide 2 < slide 10).
    """
    out: dict = {}
    for p in cfg.get("palestrantes", []):
        nome = p.get("nome", "").strip()
        guid = p.get("guid", "").strip().lower()
        pasta_raw = p.get("pasta", "").strip()
        if not (nome and guid and pasta_raw):
            print(f"[aviso] entrada invalida de palestrante: {p}", file=sys.stderr)
            continue
        pasta_path = Path(pasta_raw)
        if not pasta_path.is_absolute():
            pasta_path = (APP_DIR / pasta_raw).resolve()
        if not pasta_path.is_dir():
            print(f"[aviso] pasta nao encontrada para {nome}: {pasta_path}", file=sys.stderr)
            continue
        imagens = sorted(
            (x.name for x in pasta_path.iterdir() if x.is_file() and _is_image(x)),
            key=_natural_key,
        )
        if not imagens:
            print(f"[aviso] pasta sem imagens para {nome}: {pasta_path}", file=sys.stderr)
            continue
        out[guid] = (nome, pasta_path, imagens)
    return out


CFG = carregar_config()
VMIX_HOST = CFG.get("vmix", {}).get("host", "localhost")
VMIX_PORT = int(CFG.get("vmix", {}).get("port", 8088))
SERVER_PORT = int(CFG.get("server_port", 5000))
PALESTRANTES = carregar_palestrantes(CFG)


def validar_config(new_cfg: dict) -> list[str]:
    """Retorna lista de erros encontrados no payload. Vazia = OK.

    Valida:
    - payload e dict
    - 'palestrantes' e lista (se presente)
    - cada palestrante tem nome, guid, pasta nao-vazios
    - GUIDs unicos (case-insensitive)
    - pasta existe no disco e contem >= 1 arquivo de imagem aceita
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
        pasta_raw = (p.get("pasta") or "").strip()

        if not nome:
            erros.append(f"{base}.nome: obrigatorio")
        if not guid:
            erros.append(f"{base}.guid: obrigatorio")
        if not pasta_raw:
            erros.append(f"{base}.pasta: obrigatorio")

        if guid:
            if guid in guids_vistos:
                erros.append(
                    f"{base}.guid: duplicado — ja usado em palestrantes[{guids_vistos[guid]}]"
                )
            else:
                guids_vistos[guid] = i

        if pasta_raw:
            pasta_path = Path(pasta_raw)
            if not pasta_path.is_absolute():
                pasta_path = (APP_DIR / pasta_raw).resolve()
            if not pasta_path.is_dir():
                erros.append(f"{base}.pasta: pasta nao existe: {pasta_path}")
            else:
                try:
                    tem_imagem = any(
                        x.is_file() and _is_image(x) for x in pasta_path.iterdir()
                    )
                except (PermissionError, OSError) as e:
                    erros.append(f"{base}.pasta: erro lendo pasta: {e}")
                    tem_imagem = False
                if not tem_imagem:
                    erros.append(
                        f"{base}.pasta: nenhuma imagem encontrada "
                        f"(formatos aceitos: {', '.join(IMAGE_EXTS)})"
                    )

    return erros


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
    nome, pasta_path, _ = info
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
        PALESTRANTES[g] = (nome, pasta_path, imagens)
    return imagens


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


_LS_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="list_dir"
)


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

def fetch_vmix_xml() -> ET.Element:
    url = f"http://{VMIX_HOST}:{VMIX_PORT}/api"
    with urllib.request.urlopen(url, timeout=3) as resp:
        data = resp.read()
    return ET.fromstring(data)


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


def compute_state() -> dict:
    try:
        root = fetch_vmix_xml()
    except Exception as e:
        return {"ok": False, "erro": f"vMix inacessivel ({VMIX_HOST}:{VMIX_PORT}): {e}"}

    active_num = root.findtext("active")
    input_program = _input_by_num(root, active_num)
    if input_program is None:
        return {"ok": True, "ativo": False, "mensagem": "Sem input em Program"}

    # Prioridade: Program direto ou via overlay interno, depois overlays globais
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

    if achado is None:
        return {"ok": True, "ativo": False, "mensagem": "Nenhum slide de palestrante em Program"}

    guid, input_palestrante = achado

    nome, pasta_path, slides = PALESTRANTES[guid]
    title = input_palestrante.get("title", "")

    # Match ancorado: filename exato dentro do title, desempate pelo mais longo
    idx = match_filename(title, slides)
    if idx is None:
        return {
            "ok": True, "ativo": False, "palestrante": nome,
            "mensagem": f"Slide atual ('{title}') nao bateu com arquivos da pasta",
        }

    atual = slides[idx]
    proximo = slides[idx + 1] if idx + 1 < len(slides) else None

    def url_img(arq: str) -> str:
        return f"/img/{urllib.parse.quote(guid)}/{urllib.parse.quote(arq)}"

    return {
        "ok": True, "ativo": True,
        "palestrante": nome,
        "indice": idx + 1,
        "total": len(slides),
        "atual_url": url_img(atual),
        "proximo_url": url_img(proximo) if proximo else None,
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
                or "GET /admin/api/config" in s):
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
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self._send_json(json.load(f))
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

        if sub == "clientes":
            self._send_json({"clientes": clientes_ativos(janela_s=30)})
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
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except Exception as e:
            self._send_json({"ok": False, "error": f"JSON invalido: {e}"}, status=400)
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


def main() -> None:
    setup_logging(verbose=True)
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
        for guid, (nome, pasta, slides) in PALESTRANTES.items():
            print(f"    {nome}: {pasta.name} ({len(slides)} imagens)")
    else:
        print("  Nenhum palestrante configurado — abrindo o Dashboard admin")
        print("  pra voce configurar. Depois, recarregue no navegador.")
    print("=" * 68)

    # Onboarding: se ainda nao ha palestrantes, abre direto o /admin
    abrir_path = "/admin" if not PALESTRANTES else "/"

    def _abrir_browser() -> None:
        time.sleep(0.8)
        webbrowser.open(f"http://localhost:{SERVER_PORT}{abrir_path}")

    threading.Thread(target=_abrir_browser, daemon=True).start()

    with ThreadingServer(("", SERVER_PORT), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nEncerrando.")


if __name__ == "__main__":
    main()
