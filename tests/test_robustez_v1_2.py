"""Regressao v1.2.0: blindagem anti-crash/DoS (auditoria pre-evento).

Cobre os achados criticos/altos corrigidos: int(port) invalido no boot,
ParseError do XML do vMix, timeout de filesystem, snapshot de estado sob lock,
e limite de Content-Length no POST do /admin.
"""
from __future__ import annotations

import socket
import tempfile
import threading
import time
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from tests.conftest_helpers import make_images  # noqa: F401 (ajusta sys.path)

import server  # noqa: E402


def _mock_resp(data: bytes):
    """Context manager que finge uma resposta HTTP com .read() -> data."""
    m = mock.MagicMock()
    m.__enter__.return_value.read.return_value = data
    m.__exit__.return_value = None
    return m


class SafeIntTests(unittest.TestCase):
    """int(port) no import-time nao pode crashar o exe --noconsole."""

    def test_int_valido(self):
        self.assertEqual(server._safe_int("8088", 5000), 8088)
        self.assertEqual(server._safe_int(8088, 5000), 8088)

    def test_string_invalida_usa_default(self):
        self.assertEqual(server._safe_int("porta8088", 8088), 8088)

    def test_vazio_e_none_usam_default(self):
        self.assertEqual(server._safe_int("", 5000), 5000)
        self.assertEqual(server._safe_int(None, 5000), 5000)
        self.assertEqual(server._safe_int("   ", 5000), 5000)

    def test_boot_com_port_invalido_nao_levanta(self):
        """Simula o caminho do boot: config com port lixo -> _safe_int salva."""
        cfg = {"vmix": {"host": "x", "port": "abc"}, "server_port": ""}
        # Nao deve levantar — exatamente o que roda no import do modulo.
        porta_vmix = server._safe_int(cfg.get("vmix", {}).get("port", 8088), 8088)
        porta_srv = server._safe_int(cfg.get("server_port", 5000), 5000)
        self.assertEqual(porta_vmix, 8088)
        self.assertEqual(porta_srv, 5000)


class FetchXmlParseTests(unittest.TestCase):
    """fetch_vmix_xml nao pode propagar ParseError cru se o vMix devolve HTML."""

    def setUp(self):
        # Zera o cache pra forcar o fetch real (mockado).
        server._xml_cache = {"ts": 0.0, "root": None}

    def test_html_404_vira_valueerror(self):
        # HTML malformado (sem </html>, <br> nao-fechado) — comeca com '<' mas
        # ET.fromstring rejeita. Tipico de pagina de erro de servidor web.
        html = b"<html><body>404 Not Found<br></body>"
        with mock.patch("urllib.request.urlopen", return_value=_mock_resp(html)):
            with self.assertRaises(ValueError):
                server.fetch_vmix_xml(max_age=0.0)

    def test_corpo_nao_xml_vira_valueerror(self):
        with mock.patch("urllib.request.urlopen",
                        return_value=_mock_resp(b"Not Found")):
            with self.assertRaises(ValueError):
                server.fetch_vmix_xml(max_age=0.0)

    def test_xml_valido_retorna_element(self):
        xml = b"<vmix><inputs></inputs></vmix>"
        with mock.patch("urllib.request.urlopen", return_value=_mock_resp(xml)):
            root = server.fetch_vmix_xml(max_age=0.0)
        self.assertIsInstance(root, ET.Element)
        self.assertEqual(root.tag, "vmix")

    def test_compute_state_offline_quando_html(self):
        """O caller (compute_state) trata como vMix offline, sem crashar."""
        server._xml_cache = {"ts": 0.0, "root": None}
        with mock.patch("urllib.request.urlopen",
                        return_value=_mock_resp(b"<html><body>erro<br></body>")):
            st = server.compute_state()
        self.assertFalse(st["ok"])
        self.assertIn("inacessivel", st["erro"])


class IsFileTimeoutTests(unittest.TestCase):
    """is_file protegido por timeout — UNC caido nao pode travar a thread."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.f = Path(self.tmp.name) / "x.png"
        self.f.write_bytes(b"\x89PNG")

    def tearDown(self):
        self.tmp.cleanup()

    def test_arquivo_existente_true(self):
        self.assertTrue(server._is_file_timeout(self.f))

    def test_arquivo_inexistente_false(self):
        self.assertFalse(server._is_file_timeout(Path(self.tmp.name) / "nao.png"))


class SnapshotEstadoTests(unittest.TestCase):
    """Leitura de PALESTRANTES sob lock retorna copia consistente."""

    def setUp(self):
        self._orig = server.PALESTRANTES
        server.PALESTRANTES = {
            "g1": ("Wagner", None, [], "list"),
        }

    def tearDown(self):
        server.PALESTRANTES = self._orig

    def test_snapshot_e_copia(self):
        snap = server._palestrantes_snapshot()
        self.assertIn("g1", snap)
        snap["g2"] = ("X", None, [], "list")
        # Mutar a copia nao afeta o global.
        self.assertNotIn("g2", server.PALESTRANTES)

    def test_info_case_insensitive(self):
        self.assertIsNotNone(server._palestrante_info("G1"))
        self.assertIsNone(server._palestrante_info("desconhecido"))

    def test_vmix_target_retorna_host_port(self):
        host, port = server._vmix_target()
        self.assertEqual(host, server.VMIX_HOST)
        self.assertEqual(port, server.VMIX_PORT)


class RescanDoubleCheckTests(unittest.TestCase):
    """rescan_pasta nao re-adiciona um guid removido durante o IO."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name) / "slides"
        make_images(self.pasta, ["a.png", "b.png"])
        self._orig = server.PALESTRANTES
        server.PALESTRANTES = {"g1": ("W", self.pasta, ["a.png"], "photos")}

    def tearDown(self):
        server.PALESTRANTES = self._orig
        self.tmp.cleanup()

    def test_remove_durante_io_nao_readiciona(self):
        real_listar = server._listar_imagens_em

        def listar_e_remover(p):
            # Simula a config sendo recarregada (guid sai) enquanto listamos.
            server.PALESTRANTES.pop("g1", None)
            return real_listar(p)

        with mock.patch.object(server, "_listar_imagens_em", side_effect=listar_e_remover):
            server.rescan_pasta("g1")
        # O double-check 'if g in PALESTRANTES' impede a re-adicao.
        self.assertNotIn("g1", server.PALESTRANTES)


class ContentLengthLimitTests(unittest.TestCase):
    """POST com Content-Length gigante deve ser rejeitado (413) antes do read,
    sem alocar memoria — protege contra OOM."""

    @classmethod
    def setUpClass(cls):
        cls.porta, cls.srv = server.bind_com_fallback(60111, max_tentativas=20)
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def _post_headers_only(self, content_length: int) -> str:
        """Envia POST com Content-Length declarado mas SEM corpo. Le a status line."""
        s = socket.create_connection(("127.0.0.1", self.porta), timeout=3)
        try:
            req = (
                f"POST /admin/api/config HTTP/1.1\r\n"
                f"Host: 127.0.0.1\r\n"
                f"Content-Type: application/json\r\n"
                f"Content-Length: {content_length}\r\n"
                f"Connection: close\r\n\r\n"
            )
            s.sendall(req.encode("ascii"))
            data = s.recv(256)
            return data.decode("latin-1", "replace")
        finally:
            s.close()

    def test_content_length_gigante_retorna_413(self):
        resp = self._post_headers_only(2_000_000_000)  # ~2 GB
        self.assertIn("413", resp.split("\r\n", 1)[0])

    def test_acima_do_max_retorna_413(self):
        resp = self._post_headers_only(server.MAX_BODY_BYTES + 1)
        self.assertIn("413", resp.split("\r\n", 1)[0])


if __name__ == "__main__":
    unittest.main()
