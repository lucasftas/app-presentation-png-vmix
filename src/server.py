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
    input_program = next(
        (i for i in root.findall("inputs/input") if i.get("number") == active_num),
        None,
    )
    if input_program is None:
        return {"ok": True, "ativo": False, "mensagem": "Sem input em Program"}

    # Caso 1: input em Program é diretamente um palestrante
    # Caso 2: input composto com palestrante em overlay
    guid = (input_program.get("key") or "").lower()
    input_palestrante = input_program if guid in PALESTRANTES else None

    if input_palestrante is None:
        for ov in input_program.findall("overlay"):
            ov_key = (ov.get("key") or "").lower()
            if ov_key in PALESTRANTES:
                guid = ov_key
                input_palestrante = next(
                    (i for i in root.findall("inputs/input")
                     if (i.get("key") or "").lower() == ov_key),
                    None,
                )
                break

    if input_palestrante is None:
        return {"ok": True, "ativo": False, "mensagem": "Nenhum slide de palestrante em Program"}

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
        if "/state" in str(msg):
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


class ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def main() -> None:
    print("=" * 60)
    print("  Modo Apresentador - app-presentation-png-vmix")
    print(f"  vMix: http://{VMIX_HOST}:{VMIX_PORT}/api")
    print(f"  URL:  http://localhost:{SERVER_PORT}")
    print(f"  App:  {APP_DIR}")
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
