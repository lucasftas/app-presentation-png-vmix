"""Testes de extensoes multiplas + natural sort + list_dir."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.conftest_helpers import make_images  # noqa: E402

import server  # noqa: E402


class ImageExtsTests(unittest.TestCase):
    def test_image_exts_cobre_formatos_do_vmix(self):
        for ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"):
            self.assertIn(ext, server.IMAGE_EXTS, f"{ext} deveria estar em IMAGE_EXTS")


class CarregarPalestrantesTests(unittest.TestCase):
    def _carregar_com_pasta(self, pasta: Path, nome="X", guid="abc-123"):
        cfg = {"palestrantes": [{"nome": nome, "guid": guid, "pasta": str(pasta)}]}
        return server.carregar_palestrantes(cfg)

    def test_carrega_com_jpg_so(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td) / "slides"
            make_images(pasta, ["slide 01.jpg", "slide 02.jpg", "slide 03.jpg"])
            out = self._carregar_com_pasta(pasta)
            self.assertEqual(len(out), 1)
            (_nome, _path, imagens) = next(iter(out.values()))
            self.assertEqual(imagens, ["slide 01.jpg", "slide 02.jpg", "slide 03.jpg"])

    def test_carrega_com_extensoes_mistas(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td) / "slides"
            make_images(pasta, [
                "a.png", "b.jpg", "c.jpeg", "d.bmp", "e.gif", "f.webp",
            ])
            out = self._carregar_com_pasta(pasta)
            (_nome, _path, imagens) = next(iter(out.values()))
            self.assertEqual(len(imagens), 6)

    def test_ignora_nao_imagens(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td) / "slides"
            make_images(pasta, ["ok.png", "ignora.txt", "config.ini", "video.mp4"])
            out = self._carregar_com_pasta(pasta)
            (_nome, _path, imagens) = next(iter(out.values()))
            self.assertEqual(imagens, ["ok.png"])

    def test_pasta_sem_imagens_nao_carrega(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td) / "vazia"
            pasta.mkdir()
            (pasta / "leiame.txt").write_text("sem imagens")
            out = self._carregar_com_pasta(pasta)
            self.assertEqual(out, {})


class NaturalSortTests(unittest.TestCase):
    def test_slide_2_antes_de_slide_10(self):
        nomes = ["slide 10.png", "slide 2.png", "slide 1.png"]
        ordenado = sorted(nomes, key=server._natural_key)
        self.assertEqual(ordenado, ["slide 1.png", "slide 2.png", "slide 10.png"])

    def test_zero_padding_mantem_ordem(self):
        nomes = ["slide 01.png", "slide 02.png", "slide 10.png"]
        ordenado = sorted(nomes, key=server._natural_key)
        self.assertEqual(ordenado, ["slide 01.png", "slide 02.png", "slide 10.png"])

    def test_prefixo_textual_ordena_antes_do_numero(self):
        nomes = ["B slide 2.png", "A slide 5.png", "A slide 10.png"]
        ordenado = sorted(nomes, key=server._natural_key)
        self.assertEqual(ordenado, ["A slide 5.png", "A slide 10.png", "B slide 2.png"])

    def test_case_insensitive(self):
        nomes = ["Slide 10.png", "slide 2.png"]
        ordenado = sorted(nomes, key=server._natural_key)
        self.assertEqual(ordenado, ["slide 2.png", "Slide 10.png"])

    def test_carregar_palestrantes_usa_natural_sort(self):
        with tempfile.TemporaryDirectory() as td:
            pasta = Path(td) / "slides"
            make_images(pasta, ["slide 10.png", "slide 2.png", "slide 1.png"])
            cfg = {"palestrantes": [{"nome": "X", "guid": "g", "pasta": str(pasta)}]}
            out = server.carregar_palestrantes(cfg)
            (_nome, _path, imagens) = next(iter(out.values()))
            self.assertEqual(imagens, ["slide 1.png", "slide 2.png", "slide 10.png"])


class ListDirTests(unittest.TestCase):
    def test_conta_todas_extensoes_como_imagens(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sub = root / "album"
            make_images(sub, ["a.png", "b.jpg", "c.webp", "d.txt"])
            resultado = server.list_dir(str(root))
            self.assertEqual(len(resultado["items"]), 1)
            album = resultado["items"][0]
            self.assertEqual(album["name"], "album")
            self.assertEqual(album["imagens"], 3)
            self.assertNotIn("pngs", album, "campo antigo 'pngs' nao deve mais existir")

    def test_ordena_subpastas_natural(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for n in ["slide 10", "slide 2", "slide 1"]:
                (root / n).mkdir()
            resultado = server.list_dir(str(root))
            nomes = [x["name"] for x in resultado["items"]]
            self.assertEqual(nomes, ["slide 1", "slide 2", "slide 10"])


class ListDirTimeoutTests(unittest.TestCase):
    """Fase 3: list_dir nao pode bloquear worker indefinidamente em UNC lento."""

    def test_timeout_retorna_parcial_com_flag(self):
        import threading
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Cria uma funcao que simula iterdir lento
            real_iterdir = Path.iterdir
            bloqueio = threading.Event()

            def slow_iterdir(self_path):
                if self_path == root:
                    bloqueio.wait(timeout=5)  # bloqueia 5s
                return real_iterdir(self_path)

            original = server.list_dir
            # Simulamos via monkey patch mais simples: passa timeout curto
            from unittest import mock
            with mock.patch.object(Path, "iterdir", new=slow_iterdir):
                resultado = server.list_dir(str(root), timeout=0.5)
            self.assertTrue(resultado.get("timeout"), "esperava timeout=True no resultado")
            self.assertEqual(resultado.get("items"), [])

    def test_sem_timeout_retorna_normal(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "sub").mkdir()
            resultado = server.list_dir(str(root), timeout=2.0)
            self.assertFalse(resultado.get("timeout", False))
            self.assertEqual(len(resultado["items"]), 1)


if __name__ == "__main__":
    unittest.main()
