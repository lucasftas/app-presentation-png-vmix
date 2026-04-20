"""Testes dos helpers do tray (parse de host, URLs, posicao de palestrante)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.conftest_helpers import make_images  # noqa: E402

import server  # noqa: E402
import tray  # noqa: E402


class ParseHostPortTests(unittest.TestCase):
    def test_host_sem_porta_usa_default(self):
        self.assertEqual(tray.parse_host_port("192.168.1.10"), ("192.168.1.10", 8088))

    def test_host_com_porta(self):
        self.assertEqual(tray.parse_host_port("10.0.0.1:8090"), ("10.0.0.1", 8090))

    def test_ignora_esquema_http(self):
        self.assertEqual(tray.parse_host_port("http://vmix:8088"), ("vmix", 8088))

    def test_ignora_barra_final(self):
        self.assertEqual(tray.parse_host_port("10.0.0.1:8090/"), ("10.0.0.1", 8090))

    def test_string_vazia_retorna_none(self):
        self.assertIsNone(tray.parse_host_port(""))

    def test_porta_invalida_retorna_none(self):
        self.assertIsNone(tray.parse_host_port("host:abc"))


class VmixHostPortTests(unittest.TestCase):
    def test_monta_string_do_cfg(self):
        fake = type("F", (), {"CFG": {"vmix": {"host": "1.2.3.4", "port": 9000}}})()
        self.assertEqual(tray.vmix_host_port(fake), "1.2.3.4:9000")

    def test_default_quando_nao_configurado(self):
        fake = type("F", (), {"CFG": {}})()
        self.assertEqual(tray.vmix_host_port(fake), "localhost:8088")


class UrlLanTests(unittest.TestCase):
    def test_usa_ip_da_lan(self):
        fake = mock.MagicMock()
        fake._ip_lan.return_value = "192.168.1.50"
        fake.SERVER_PORT = 5000
        self.assertEqual(tray.url_lan(fake), "http://192.168.1.50:5000/")

    def test_fallback_localhost_se_ip_ausente(self):
        fake = mock.MagicMock()
        fake._ip_lan.return_value = None
        fake.SERVER_PORT = 5000
        self.assertEqual(tray.url_lan(fake), "http://localhost:5000/")


class PosicaoPalestranteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        make_images(self.pasta, [f"slide {i:02d}.png" for i in range(1, 50)])
        self.guid = "abc-123"
        self._pal_orig = server.PALESTRANTES
        server.PALESTRANTES = {
            self.guid: ("Wagner", self.pasta,
                        sorted(p.name for p in self.pasta.iterdir())),
        }

    def tearDown(self):
        server.PALESTRANTES = self._pal_orig
        self.tmp.cleanup()

    def test_ativo_retorna_indice_slash_total(self):
        with mock.patch.object(server, "compute_state", return_value={
            "ok": True, "ativo": True, "guid": self.guid,
            "indice": 17, "total": 49,
        }):
            pos = tray.posicao_do_palestrante(self.guid, server)
        self.assertEqual(pos, "17 / 49")

    def test_inativo_mostra_tracinho(self):
        with mock.patch.object(server, "compute_state", return_value={
            "ok": True, "ativo": False,
        }):
            pos = tray.posicao_do_palestrante(self.guid, server)
        self.assertEqual(pos, "— / 49")

    def test_palestrante_desconhecido(self):
        with mock.patch.object(server, "compute_state", return_value={
            "ok": True, "ativo": False,
        }):
            pos = tray.posicao_do_palestrante("nao-existe", server)
        self.assertEqual(pos, "— / 0")


class MontarMenuItemsTests(unittest.TestCase):
    """Testa se o menu dinamico inclui os items esperados conforme estado."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)
        make_images(self.pasta, ["a.png", "b.png"])
        self._cfg_orig = server.CFG
        self._pal_orig = server.PALESTRANTES
        server.CFG = {
            "vmix": {"host": "localhost", "port": 8088},
            "server_port": 5000,
            "palestrantes": [
                {"nome": "Wagner", "guid": "g1", "pasta": str(self.pasta)},
                {"nome": "Vini", "guid": "g2", "pasta": str(self.pasta)},
            ],
        }
        server.PALESTRANTES = {
            "g1": ("Wagner", self.pasta, ["a.png", "b.png"]),
            "g2": ("Vini", self.pasta, ["a.png", "b.png"]),
        }

    def tearDown(self):
        server.CFG = self._cfg_orig
        server.PALESTRANTES = self._pal_orig
        self.tmp.cleanup()

    def _labels(self, items):
        """Extrai labels de texto dos MenuItems (ignora SEPARATOR)."""
        out = []
        for it in items:
            if it is tray.pystray.Menu.SEPARATOR:
                continue
            out.append(getattr(it, "text", str(it)))
        return out

    def test_menu_tem_status_vmix_e_rede(self):
        with mock.patch.object(server, "compute_state",
                                return_value={"ok": True, "ativo": False}):
            items = tray.montar_menu_items(server)
        labels = self._labels(items)
        self.assertTrue(any("vMix" in l for l in labels))
        self.assertTrue(any("Rede" in l for l in labels))

    def test_menu_inclui_palestrantes(self):
        with mock.patch.object(server, "compute_state",
                                return_value={"ok": True, "ativo": False}):
            items = tray.montar_menu_items(server)
        labels = self._labels(items)
        # Cada palestrante tem 4 items (label + 3 acoes)
        self.assertTrue(any("Wagner" in l and "— / 2" in l for l in labels))
        self.assertTrue(any("Avançar Wagner" in l for l in labels))
        self.assertTrue(any("Voltar Vini" in l for l in labels))
        self.assertTrue(any("Reset Vini" in l for l in labels))

    def test_menu_marca_palestrante_ao_vivo(self):
        with mock.patch.object(server, "compute_state",
                                return_value={"ok": True, "ativo": True,
                                              "guid": "g1", "indice": 1, "total": 2}):
            items = tray.montar_menu_items(server)
        labels = self._labels(items)
        # Wagner ao vivo → prefixo "● "
        self.assertTrue(any("● Wagner" in l and "1 / 2" in l for l in labels))
        # Vini não ativo → prefix neutro
        self.assertTrue(any(l.startswith("  Vini") or "  Vini " in l for l in labels))

    def test_menu_tem_abrir_apresentador_admin_e_configs(self):
        with mock.patch.object(server, "compute_state",
                                return_value={"ok": False}):
            items = tray.montar_menu_items(server)
        labels = self._labels(items)
        self.assertTrue(any("Apresentador" in l for l in labels))
        self.assertTrue(any("Dashboard" in l for l in labels))
        self.assertTrue(any("Configs" in l for l in labels))

    def test_menu_mostra_nenhum_palestrante_quando_vazio(self):
        server.CFG["palestrantes"] = []
        with mock.patch.object(server, "compute_state",
                                return_value={"ok": True, "ativo": False}):
            items = tray.montar_menu_items(server)
        labels = self._labels(items)
        self.assertTrue(any("nenhum palestrante" in l.lower() for l in labels))


if __name__ == "__main__":
    unittest.main()
