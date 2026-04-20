"""Tray icon do Apresentador vMix — menu nativo do Windows via pystray.

Responsabilidades:
- Exibir icone na bandeja do sistema
- Montar menu contextual dinamico com status do vMix, palestrantes e acoes
- Despachar callbacks (editar IP, abrir telas, controlar slides, etc)
- Notificar em eventos criticos (vMix offline, palestrante no ar)

Este modulo importa `server` lazy para ler/escrever CFG e chamar `vmix_control`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import simpledialog
from typing import Callable

import pystray
from PIL import Image

# -------------------- Paths --------------------

def _icon_path(alerta: bool = False) -> Path:
    """Procura icon.ico (ou icon_alert.ico) em recursos/ (portable) ou assets/ (dev)."""
    nome = "icon_alert.ico" if alerta else "icon.ico"
    app_dir = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    for cand in (app_dir / "recursos" / nome,
                 app_dir / nome,
                 app_dir.parent / "assets" / nome):
        if cand.is_file():
            return cand
    # fallback: se icon_alert nao existe, usa o normal
    if alerta:
        return _icon_path(False)
    raise FileNotFoundError(f"{nome} nao encontrado")


def carregar_icone(alerta: bool = False) -> Image.Image:
    """Carrega icon.ico em objeto PIL.Image pro pystray."""
    return Image.open(_icon_path(alerta))


# -------------------- Helpers de formatacao --------------------

def posicao_do_palestrante(guid: str, server_module) -> str:
    """Retorna 'X / Y' do palestrante se estiver ativo, ou '— / Y'."""
    info = server_module.PALESTRANTES.get((guid or "").lower())
    total = len(info[2]) if info else 0
    state = server_module.compute_state()
    if state.get("ok") and state.get("ativo") and state.get("guid") == guid:
        return f"{state['indice']} / {state['total']}"
    return f"— / {total}"


def vmix_host_port(server_module) -> str:
    cfg = server_module.CFG
    host = cfg.get("vmix", {}).get("host", "localhost")
    port = cfg.get("vmix", {}).get("port", 8088)
    return f"{host}:{port}"


def url_lan(server_module) -> str:
    ip = server_module._ip_lan() or "localhost"
    return f"http://{ip}:{server_module.SERVER_PORT}/"


# -------------------- Clipboard (Windows) --------------------

def copiar_para_clipboard(texto: str) -> None:
    """Copia texto pro clipboard usando tkinter (stdlib)."""
    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(texto)
    root.update()
    root.after(200, root.destroy)
    root.mainloop()


# -------------------- Dialog pra editar IP --------------------

def perguntar_vmix_host(atual: str) -> str | None:
    """Abre dialog tkinter pra o user informar novo host:port do vMix.

    Se tkinter falhar (runtime Tcl ausente, etc), retorna None e o caller
    deve mostrar fallback (ex: notificar pra usar o Dashboard web).
    """
    try:
        root = tk.Tk()
        root.withdraw()
        try:
            root.iconbitmap(str(_icon_path()))
        except Exception:
            pass
        try:
            novo = simpledialog.askstring(
                "vMix — alterar endereço",
                f"Informe o novo host:port do vMix:\n(atual: {atual})",
                initialvalue=atual,
                parent=root,
            )
        finally:
            root.destroy()
    except Exception:
        return None
    if novo:
        return novo.strip()
    return None


def parse_host_port(raw: str, default_port: int = 8088) -> tuple[str, int] | None:
    """Interpreta 'host', 'host:port' ou 'http://host:port'. Retorna (host, port) ou None."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for prefix in ("http://", "https://"):
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    raw = raw.rstrip("/")
    if ":" in raw:
        host, _, port_s = raw.rpartition(":")
        try:
            port = int(port_s)
        except ValueError:
            return None
    else:
        host = raw
        port = default_port
    host = host.strip()
    if not host:
        return None
    return host, port


# -------------------- Acoes de sistema --------------------

def abrir_pasta_logs(server_module) -> None:
    """Abre a pasta de logs no Explorer."""
    path = server_module.LOG_DIR
    path.mkdir(exist_ok=True)
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except AttributeError:
        subprocess.Popen(["xdg-open", str(path)])


# -------------------- Callbacks do menu --------------------

def _abrir_apresentador(server_module):
    def _cb(icon=None, item=None):
        webbrowser.open(f"http://localhost:{server_module.SERVER_PORT}/")
    return _cb


def _abrir_admin(server_module):
    def _cb(icon=None, item=None):
        webbrowser.open(f"http://localhost:{server_module.SERVER_PORT}/admin")
    return _cb


def _abrir_logs(server_module):
    def _cb(icon=None, item=None):
        abrir_pasta_logs(server_module)
    return _cb


def _copiar_url(server_module):
    def _cb(icon=None, item=None):
        url = url_lan(server_module)
        copiar_para_clipboard(url)
        try:
            icon.notify(f"URL copiada:\n{url}", "Apresentador vMix")
        except Exception:
            pass
    return _cb


def _editar_vmix_host(server_module):
    def _cb(icon=None, item=None):
        atual = vmix_host_port(server_module)
        novo = perguntar_vmix_host(atual)
        if novo is None:
            # Dialog tkinter falhou OU user cancelou — sugere o Dashboard
            try:
                icon.notify(
                    "Não foi possível abrir o diálogo. "
                    "Use o Dashboard (admin) pra editar o IP do vMix.",
                    "Apresentador vMix",
                )
            except Exception:
                pass
            return
        if not novo:
            return
        parsed = parse_host_port(novo, default_port=8088)
        if not parsed:
            try:
                icon.notify("Formato inválido (use host ou host:port)", "Apresentador vMix")
            except Exception:
                pass
            return
        host, port = parsed
        novo_cfg = dict(server_module.CFG)
        novo_cfg["vmix"] = {"host": host, "port": port}
        try:
            server_module.salvar_config(novo_cfg)
            try:
                icon.notify(f"vMix agora em {host}:{port}", "Apresentador vMix")
            except Exception:
                pass
        except ValueError as e:
            try:
                icon.notify(f"Erro: {e}", "Apresentador vMix")
            except Exception:
                pass
    return _cb


def _liberar_firewall(server_module):
    def _cb(icon=None, item=None):
        ok, msg = liberar_firewall(server_module.SERVER_PORT)
        try:
            icon.notify(msg, "Apresentador vMix")
        except Exception:
            pass
    return _cb


def _reiniciar(server_module, shutdown_fn):
    def _cb(icon=None, item=None):
        # Relanca o proprio exe/python antes de sair
        import subprocess as _sp
        try:
            if getattr(sys, "frozen", False):
                _sp.Popen([sys.executable])
            else:
                _sp.Popen([sys.executable, *sys.argv])
        except Exception as e:
            print(f"[erro] reiniciar: {e}", file=sys.stderr)
        if shutdown_fn:
            shutdown_fn()
        icon.stop()
    return _cb


def _sair(shutdown_fn):
    def _cb(icon=None, item=None):
        if shutdown_fn:
            shutdown_fn()
        icon.stop()
    return _cb


def _slide_action(server_module, guid: str, acao: str):
    """Devolve callback que chama vmix_control('NextPicture'|'PreviousPicture'|'SelectIndex 1')."""
    def _cb(icon=None, item=None):
        if acao == "next":
            server_module.vmix_control("NextPicture", guid)
        elif acao == "prev":
            server_module.vmix_control("PreviousPicture", guid)
        elif acao == "reset":
            server_module.vmix_control("SelectIndex", guid, "1")
    return _cb


def _abrir_projetor(server_module, monitor_idx: int):
    def _cb(icon=None, item=None):
        try:
            monitores = server_module.list_monitors()
            monitor = next((m for m in monitores if m["indice"] == monitor_idx), None)
            if not monitor:
                return
            url = f"http://localhost:{server_module.SERVER_PORT}/?kiosk=1"
            server_module.PROJETOR_MANAGER.abrir(monitor, url)
            try:
                icon.notify(f"Projetor aberto em {monitor['nome']}", "Apresentador vMix")
            except Exception:
                pass
        except Exception as e:
            try:
                icon.notify(f"Erro: {e}", "Apresentador vMix")
            except Exception:
                pass
    return _cb


def _fechar_projetor(server_module, pid: int):
    def _cb(icon=None, item=None):
        server_module.PROJETOR_MANAGER.fechar(pid)
    return _cb


def _fechar_todos_projetores(server_module):
    def _cb(icon=None, item=None):
        n = server_module.PROJETOR_MANAGER.fechar_todos()
        try:
            icon.notify(f"{n} projetor{'es' if n != 1 else ''} fechado{'s' if n != 1 else ''}",
                         "Apresentador vMix")
        except Exception:
            pass
    return _cb


# -------------------- Montagem do menu --------------------

def _status_label(server_module) -> str:
    """Primeira linha de status: 'vMix  192.168.X.X:8088 ✓' ou '✕ offline'."""
    state = server_module.compute_state()
    host = vmix_host_port(server_module)
    ok = state.get("ok", False)
    return f"{'✓' if ok else '✕'}  vMix  {host}"


def montar_menu_items(server_module, icon=None, shutdown_fn=None):
    """Monta os MenuItems dinamicamente. Chamado toda vez que o menu abre."""
    state = server_module.compute_state()

    items: list = []

    # ===== Status =====
    items.append(pystray.MenuItem(_status_label(server_module),
                                   _editar_vmix_host(server_module)))
    items.append(pystray.MenuItem(
        f"🌐  Rede: {url_lan(server_module)}    (clique copia)",
        _copiar_url(server_module),
    ))
    items.append(pystray.Menu.SEPARATOR)

    # ===== Slides por palestrante =====
    pals = server_module.CFG.get("palestrantes", []) or []
    if not pals:
        items.append(pystray.MenuItem("(nenhum palestrante configurado)",
                                       None, enabled=False))
    else:
        for p in pals:
            guid = (p.get("guid") or "").lower()
            nome = p.get("nome", "?")
            pos = posicao_do_palestrante(guid, server_module)
            ao_vivo = state.get("ativo") and state.get("guid") == guid
            prefix = "● " if ao_vivo else "  "
            label = f"{prefix}{nome}    {pos}"
            items.append(pystray.MenuItem(label, None, enabled=False))
            items.append(pystray.MenuItem(f"     ▶  Avançar {nome}",
                                           _slide_action(server_module, guid, "next")))
            items.append(pystray.MenuItem(f"     ◀  Voltar {nome}",
                                           _slide_action(server_module, guid, "prev")))
            items.append(pystray.MenuItem(f"     ↺  Reset {nome} (slide 1)",
                                           _slide_action(server_module, guid, "reset")))
    items.append(pystray.Menu.SEPARATOR)

    # ===== Abrir telas =====
    # Default (click simples/duplo no icone) = abrir o Dashboard (admin).
    items.append(pystray.MenuItem("⚙️  Abrir Dashboard (admin)",
                                   _abrir_admin(server_module),
                                   default=True))
    items.append(pystray.MenuItem("🖼️  Abrir Modo Apresentador",
                                   _abrir_apresentador(server_module)))

    # ===== Submenu Projetar em monitor =====
    try:
        monitores = server_module.list_monitors()
    except Exception:
        monitores = []
    try:
        abertos = server_module.PROJETOR_MANAGER.abertos()
    except Exception:
        abertos = []
    aberto_por_monitor = {p["monitor"]["indice"]: p for p in abertos}

    proj_items = []
    for m in monitores:
        nome = m["nome"]
        dim = f"{m['width']}×{m['height']}"
        primario = " (primário)" if m["primario"] else ""
        ja = aberto_por_monitor.get(m["indice"])
        if ja:
            # Ja aberto — clicar fecha
            proj_items.append(pystray.MenuItem(
                f"● {nome}{primario} — {dim}  (fechar)",
                _fechar_projetor(server_module, ja["pid"]),
            ))
        else:
            proj_items.append(pystray.MenuItem(
                f"▶ {nome}{primario} — {dim}",
                _abrir_projetor(server_module, m["indice"]),
            ))
    if abertos:
        proj_items.append(pystray.Menu.SEPARATOR)
        proj_items.append(pystray.MenuItem(
            f"✕ Fechar todos ({len(abertos)})",
            _fechar_todos_projetores(server_module),
        ))
    if not proj_items:
        proj_items.append(pystray.MenuItem("(nenhum monitor detectado)",
                                             None, enabled=False))

    items.append(pystray.MenuItem("📺  Projetar em monitor",
                                    pystray.Menu(*proj_items)))

    # ===== Submenu Configs =====
    configs = pystray.Menu(
        pystray.MenuItem("📂  Abrir pasta de logs", _abrir_logs(server_module)),
        pystray.MenuItem(f"🔓  Liberar porta {server_module.SERVER_PORT} no firewall",
                          _liberar_firewall(server_module)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("🔄  Reiniciar servidor",
                          _reiniciar(server_module, shutdown_fn)),
        pystray.MenuItem("✕  Sair", _sair(shutdown_fn)),
    )
    items.append(pystray.Menu.SEPARATOR)
    items.append(pystray.MenuItem("🛠️  Configs", configs))

    return items


def liberar_firewall(porta: int) -> tuple[bool, str]:
    """Cria regra no Windows Firewall liberando a porta (requer UAC).

    Retorna (ok, mensagem). ok=False pode significar:
    - user cancelou UAC (ShellExecuteW retorna <= 32)
    - erro chamando a API
    """
    cmd = (
        f'netsh advfirewall firewall add rule '
        f'name="Apresentador vMix" dir=in action=allow '
        f'protocol=TCP localport={porta}'
    )
    try:
        import ctypes
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "cmd.exe", f"/c {cmd}", None, 0
        )
        # ShellExecuteW retorna > 32 em sucesso. <= 32 são códigos de erro.
        # SE_ERR_ACCESSDENIED = 5 → user cancelou UAC
        if ret > 32:
            return True, f"Porta {porta} liberada no firewall"
        elif ret == 5:
            return False, "Permissão negada (UAC cancelado)"
        else:
            return False, f"Erro ShellExecute (código {ret})"
    except Exception as e:
        return False, f"Erro: {e}"


# -------------------- Notificacoes (toast Windows) --------------------

class MonitorNotificacoes:
    """Monitora compute_state() e dispara notificacoes em transicoes.

    Eventos:
    - vMix offline há > 10s (1 notificação, reseta quando volta)
    - Palestrante diferente entrou no ar (por mudança de guid)
    - Palestrante voltou pra offline → notifica "Wagner saiu do ar"
    - Servidor HTTP interno nao responde 3 ticks seguidos (self-check)
    """

    def __init__(self, icon: pystray.Icon, server_module):
        self.icon = icon
        self.server = server_module
        self._ultimo_guid_ao_vivo: str | None = None
        self._ultimo_nome_ao_vivo: str | None = None
        self._vmix_offline_desde: float | None = None
        self._ja_notificou_offline = False
        self._self_check_falhas = 0
        self._ja_notificou_servidor_morto = False
        self._em_estado_alerta = False
        self._stop = threading.Event()

    def start(self) -> None:
        t = threading.Thread(target=self._loop, daemon=True)
        t.start()

    def stop(self) -> None:
        self._stop.set()

    def _notify(self, msg: str, title: str = "Apresentador vMix") -> None:
        try:
            self.icon.notify(msg, title)
        except Exception:
            pass

    def _setar_estado_alerta(self, alerta: bool) -> None:
        """Troca o icone conforme saude (normal/alerta)."""
        if alerta == self._em_estado_alerta:
            return
        try:
            self.icon.icon = carregar_icone(alerta=alerta)
            self._em_estado_alerta = alerta
        except Exception:
            pass

    def _loop(self) -> None:
        while not self._stop.wait(1.5):
            # 1. Self-check do HTTP server interno (detecta thread zumbi)
            ok_self = self.server.http_self_check(self.server.SERVER_PORT, timeout=0.8)
            if not ok_self:
                self._self_check_falhas += 1
                if self._self_check_falhas >= 3 and not self._ja_notificou_servidor_morto:
                    self._notify(
                        "🔴 Servidor interno parou de responder.\n"
                        "Clique no tray → Configs → Reiniciar servidor."
                    )
                    self._ja_notificou_servidor_morto = True
            else:
                if self._ja_notificou_servidor_morto:
                    self._notify("🟢 Servidor interno voltou")
                self._self_check_falhas = 0
                self._ja_notificou_servidor_morto = False

            try:
                s = self.server.compute_state()
            except Exception:
                continue

            # 2. vMix offline >10s
            if not s.get("ok"):
                if self._vmix_offline_desde is None:
                    self._vmix_offline_desde = time.time()
                elif (time.time() - self._vmix_offline_desde > 10
                      and not self._ja_notificou_offline):
                    self._notify("🔴 vMix offline há 10+ segundos")
                    self._ja_notificou_offline = True
                    self._setar_estado_alerta(True)
                continue

            # vMix voltou — reset flags
            if self._ja_notificou_offline:
                self._notify("🟢 vMix voltou online")
                self._setar_estado_alerta(False)
            self._vmix_offline_desde = None
            self._ja_notificou_offline = False

            # 3. Mudanca de palestrante ao vivo
            guid_atual = s.get("guid") if s.get("ativo") else None
            nome_atual = s.get("palestrante") if s.get("ativo") else None
            if guid_atual != self._ultimo_guid_ao_vivo:
                if guid_atual:
                    self._notify(f"🟢 {nome_atual} entrou no ar")
                elif self._ultimo_guid_ao_vivo and self._ultimo_nome_ao_vivo:
                    self._notify(f"⚪ {self._ultimo_nome_ao_vivo} saiu do ar")
                self._ultimo_guid_ao_vivo = guid_atual
                if nome_atual:
                    self._ultimo_nome_ao_vivo = nome_atual


# -------------------- Entry point --------------------

def rodar_tray(server_module, shutdown_fn: Callable | None = None) -> None:
    """Cria o icone, monta menu dinamico e roda (BLOQUEANTE).

    `server_module` é o módulo `server` (passado como arg pra facilitar testes).
    `shutdown_fn` é chamado no Sair/Reiniciar pra parar o HTTP server limpo.
    """
    img = carregar_icone()
    icon_ref: list = [None]  # pra permitir referência circular na closure

    def montar():
        return tuple(montar_menu_items(server_module, icon_ref[0], shutdown_fn))

    icon = pystray.Icon(
        "apresentador-vmix", img, "Apresentador vMix",
        menu=pystray.Menu(montar),
    )
    icon_ref[0] = icon

    # Notificacoes em eventos criticos (vMix offline/online, palestrante no ar)
    monitor = MonitorNotificacoes(icon, server_module)

    def _on_setup(ic):
        ic.visible = True
        monitor.start()

    icon.run(setup=_on_setup)
