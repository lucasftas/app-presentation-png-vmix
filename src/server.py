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

import http.server
import json
import mimetypes
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

# -------------------- Localizacao --------------------

def app_dir() -> Path:
    """Pasta onde o .exe/script esta (onde config.json e index.html ficam)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent

APP_DIR = app_dir()
CONFIG_PATH = APP_DIR / "config.json"
INDEX_PATH = APP_DIR / "index.html"
ADMIN_PATH = APP_DIR / "admin.html"

_cfg_lock = threading.Lock()

# -------------------- Config --------------------

def carregar_config() -> dict:
    if not CONFIG_PATH.is_file():
        exemplo = APP_DIR / "config.example.json"
        print(f"[ERRO] config.json nao encontrado em: {CONFIG_PATH}", file=sys.stderr)
        if exemplo.is_file():
            print(f"       Copie '{exemplo.name}' para 'config.json' e edite com seus dados.",
                  file=sys.stderr)
        input("\nPressione ENTER para sair...")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def carregar_palestrantes(cfg: dict) -> dict:
    """Retorna {guid: (nome, pasta_path, [pngs_ordenados])}."""
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
        pngs = sorted(x.name for x in pasta_path.iterdir() if x.suffix.lower() == ".png")
        if not pngs:
            print(f"[aviso] pasta sem PNGs para {nome}: {pasta_path}", file=sys.stderr)
            continue
        out[guid] = (nome, pasta_path, pngs)
    return out


CFG = carregar_config()
VMIX_HOST = CFG.get("vmix", {}).get("host", "localhost")
VMIX_PORT = int(CFG.get("vmix", {}).get("port", 8088))
SERVER_PORT = int(CFG.get("server_port", 5000))
PALESTRANTES = carregar_palestrantes(CFG)


def salvar_config(new_cfg: dict) -> None:
    """Escreve config.json atomicamente e recarrega estado em memoria."""
    global CFG, VMIX_HOST, VMIX_PORT, PALESTRANTES
    if not isinstance(new_cfg, dict):
        raise ValueError("payload deve ser um objeto JSON")
    if not isinstance(new_cfg.get("palestrantes", []), list):
        raise ValueError("'palestrantes' deve ser uma lista")
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


def list_dir(path_str: str) -> dict:
    """Lista subpastas (com contagem de PNGs) dentro de `path_str`.
    Sem restricao de raiz: app roda local para operador do evento.
    """
    target = _safe_resolve(path_str)
    if not target.is_dir():
        raise FileNotFoundError(f"Nao e uma pasta: {target}")

    items: list[dict] = []
    try:
        children = sorted(target.iterdir(), key=lambda p: p.name.lower())
    except PermissionError:
        children = []

    for child in children:
        if child.name.startswith(".") or child.name.startswith("$"):
            continue
        try:
            if not child.is_dir():
                continue
            pngs = 0
            subdirs = 0
            try:
                for x in child.iterdir():
                    if x.is_file() and x.suffix.lower() == ".png":
                        pngs += 1
                    elif x.is_dir() and not x.name.startswith("."):
                        subdirs += 1
            except (PermissionError, OSError):
                pass
            items.append({
                "name": child.name,
                "path": str(child),
                "pngs": pngs,
                "subdirs": subdirs,
            })
        except (PermissionError, OSError):
            continue

    return {"path": str(target), "items": items}

# -------------------- compute_state --------------------

def fetch_vmix_xml() -> ET.Element:
    url = f"http://{VMIX_HOST}:{VMIX_PORT}/api"
    with urllib.request.urlopen(url, timeout=3) as resp:
        data = resp.read()
    return ET.fromstring(data)


def compute_state() -> dict:
    try:
        root = fetch_vmix_xml()
    except Exception as e:
        return {"ok": False, "erro": f"vMix inacessivel ({VMIX_HOST}:{VMIX_PORT}): {e}"}

    active_num = root.findtext("active")
    all_inputs = root.findall("inputs/input")

    def input_by_num(num: str) -> ET.Element | None:
        return next((i for i in all_inputs if i.get("number") == num), None)

    def input_by_key(key: str) -> ET.Element | None:
        k = (key or "").lower()
        return next((i for i in all_inputs if (i.get("key") or "").lower() == k), None)

    def find_palestrante_em(inp: ET.Element | None) -> tuple[str, ET.Element] | None:
        """Retorna (guid, elemento_do_palestrante) se `inp` e um palestrante
        diretamente ou envelopa um via overlay."""
        if inp is None:
            return None
        k = (inp.get("key") or "").lower()
        if k in PALESTRANTES:
            return (k, inp)
        for ov in inp.findall("overlay"):
            ov_key = (ov.get("key") or "").lower()
            if ov_key in PALESTRANTES:
                target = input_by_key(ov_key)
                if target is not None:
                    return (ov_key, target)
        return None

    input_program = input_by_num(active_num)
    if input_program is None:
        return {"ok": True, "ativo": False, "mensagem": "Sem input em Program"}

    # Prioridade: Program (direto ou via overlay interno)
    # depois overlays globais (Overlay1-16) que estejam ativas
    achado = find_palestrante_em(input_program)

    if achado is None:
        for ov in root.findall("overlays/overlay"):
            inp_num = (ov.text or "").strip()
            if not inp_num:
                continue
            ov_inp = input_by_num(inp_num)
            achado = find_palestrante_em(ov_inp)
            if achado is not None:
                break

    if achado is None:
        return {"ok": True, "ativo": False, "mensagem": "Nenhum slide de palestrante em Program"}

    guid, input_palestrante = achado

    nome, pasta_path, slides = PALESTRANTES[guid]
    title = input_palestrante.get("title", "")

    # title do vMix contem o nome do arquivo atual (ex: "... slide 26.png")
    idx = next((i for i, s in enumerate(slides) if s in title), None)
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

# -------------------- HTTP handler --------------------

class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args) -> None:
        try:
            msg = fmt % args if args else fmt
        except Exception:
            msg = fmt
        s = str(msg)
        # Silencia ruido: polling de /state do modo apresentador, ls do file
        # browser e GET do config (chamado ao abrir o admin). POST do config
        # aparece no log porque e uma acao de escrita.
        if "/state" in s or "/admin/api/ls" in s or ("GET /admin/api/config" in s):
            return
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
        if not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        if content_type is None:
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "public, max-age=300" if cache else "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = urllib.parse.unquote(parsed.path)

        if path in ("/", "/index.html"):
            self._send_file(INDEX_PATH, "text/html; charset=utf-8", cache=False)
            return

        if path == "/state":
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
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
            return

        self.send_error(404)


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main() -> None:
    print("=" * 60)
    print("  Modo Apresentador - app-presentation-png-vmix")
    print(f"  vMix:   http://{VMIX_HOST}:{VMIX_PORT}/api")
    print(f"  Live:   http://localhost:{SERVER_PORT}/")
    print(f"  Admin:  http://localhost:{SERVER_PORT}/admin")
    print(f"  App:    {APP_DIR}")
    print("=" * 60)
    if PALESTRANTES:
        print("  Palestrantes carregados:")
        for guid, (nome, pasta, slides) in PALESTRANTES.items():
            print(f"    {nome}: {pasta.name} ({len(slides)} slides)")
    else:
        print("  [aviso] Nenhum palestrante valido carregado - confira o config.json")
    print("=" * 60)

    def _abrir_browser() -> None:
        time.sleep(0.8)
        webbrowser.open(f"http://localhost:{SERVER_PORT}/")

    threading.Thread(target=_abrir_browser, daemon=True).start()

    with ThreadingServer(("", SERVER_PORT), Handler) as srv:
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nEncerrando.")


if __name__ == "__main__":
    main()
