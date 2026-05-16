"""Testes do endpoint /img/<guid>/<arquivo> e streaming de imagens."""
from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.conftest_helpers import make_images  # noqa: E402

import server  # noqa: E402


WAGNER_GUID = "aaaaaaaa-0000-0000-0000-000000000001"


class RescanImgTests(unittest.TestCase):
    """Fase 2: quando arquivo some da pasta apos carregar_palestrantes,
    /img deve re-escanear antes de desistir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name) / "slides"
        make_images(self.pasta, ["slide 01.png", "slide 02.png", "slide 03.png"])
        self._orig_pal = server.PALESTRANTES
        server.PALESTRANTES = {
            WAGNER_GUID: ("Wagner", self.pasta, ["slide 01.png", "slide 02.png", "slide 03.png"], "photos"),
        }

    def tearDown(self):
        server.PALESTRANTES = self._orig_pal
        self.tmp.cleanup()

    def test_rescan_detecta_arquivo_novo(self):
        """Arquivo novo adicionado depois do load deve aparecer apos rescan."""
        (self.pasta / "slide 04.png").write_bytes(b"")
        novo_slides = server.rescan_pasta(WAGNER_GUID)
        self.assertIn("slide 04.png", novo_slides)

    def test_rescan_remove_arquivo_ausente(self):
        """Arquivo que sumiu no disco nao aparece mais apos rescan."""
        (self.pasta / "slide 02.png").unlink()
        novo_slides = server.rescan_pasta(WAGNER_GUID)
        self.assertNotIn("slide 02.png", novo_slides)
        self.assertIn("slide 01.png", novo_slides)
        self.assertIn("slide 03.png", novo_slides)

    def test_rescan_retorna_vazio_se_guid_desconhecido(self):
        self.assertEqual(server.rescan_pasta("nao-existe"), [])

    def test_rescan_retorna_vazio_se_pasta_sumiu(self):
        import shutil
        shutil.rmtree(self.pasta)
        self.assertEqual(server.rescan_pasta(WAGNER_GUID), [])


class PreviewTests(unittest.TestCase):
    """Fase 6: endpoint /admin/api/preview lista imagens de uma pasta
    (nao precisa estar configurada como palestrante)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name) / "galeria"
        make_images(self.pasta, [
            "slide 1.png", "slide 2.png", "slide 10.png", "ignora.txt",
        ])

    def tearDown(self):
        self.tmp.cleanup()

    def test_listar_preview_retorna_imagens_em_ordem_natural(self):
        r = server.listar_preview(str(self.pasta))
        nomes = [it["name"] for it in r["items"]]
        self.assertEqual(nomes, ["slide 1.png", "slide 2.png", "slide 10.png"])
        self.assertEqual(r["total"], 3)

    def test_listar_preview_nao_lista_nao_imagens(self):
        r = server.listar_preview(str(self.pasta))
        nomes = [it["name"] for it in r["items"]]
        self.assertNotIn("ignora.txt", nomes)

    def test_listar_preview_inclui_url(self):
        r = server.listar_preview(str(self.pasta))
        for it in r["items"]:
            self.assertIn("url", it)
            self.assertIn("/admin/api/preview/img", it["url"])

    def test_listar_preview_pasta_inexistente_levanta_filenotfounderror(self):
        with self.assertRaises(FileNotFoundError):
            server.listar_preview(str(Path(self.tmp.name) / "fake"))

    def test_serve_preview_img_detecta_path_traversal(self):
        # tenta escapar da pasta com ..
        with self.assertRaises(PermissionError):
            server.preview_img_path(str(self.pasta), "..\\..\\etc\\passwd")

    def test_serve_preview_img_caminho_normal_ok(self):
        p = server.preview_img_path(str(self.pasta), "slide 1.png")
        self.assertTrue(p.is_file())
        self.assertEqual(p.name, "slide 1.png")


class SendFileStreamingTests(unittest.TestCase):
    """Fase 5: _send_file usa streaming (nao carrega tudo em RAM)."""

    def test_stream_escreve_bytes_identicos_ao_arquivo(self):
        # Arquivo grande: 2MB de bytes aleatorios (padrao reproduzivel)
        import os
        dados = os.urandom(2 * 1024 * 1024)
        with tempfile.TemporaryDirectory() as td:
            arq = Path(td) / "teste.png"
            arq.write_bytes(dados)

            # Handler minimal capturando headers + wfile
            from http.server import BaseHTTPRequestHandler

            class _FakeHandler(server.Handler):
                def __init__(self):
                    self.wfile = io.BytesIO()
                    self._headers = {}
                    self._status = None
                def send_response(self, code):
                    self._status = code
                def send_header(self, k, v):
                    self._headers[k] = v
                def end_headers(self):
                    pass

            h = _FakeHandler()
            h._send_file(arq)
            self.assertEqual(h._status, 200)
            self.assertEqual(int(h._headers.get("Content-Length", 0)), len(dados))
            self.assertEqual(h.wfile.getvalue(), dados)


if __name__ == "__main__":
    unittest.main()
