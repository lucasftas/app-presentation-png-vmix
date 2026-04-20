"""Testes do ProjetorManager + list_monitors (v0.8.0)."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.conftest_helpers import make_images  # noqa: F401 (ajusta sys.path)

import server  # noqa: E402


class ListMonitorsTests(unittest.TestCase):
    """list_monitors() retorna lista no formato esperado em qualquer SO."""

    def test_retorna_lista_nao_vazia_em_ambiente_normal(self):
        monitores = server.list_monitors()
        # Em CI/Linux pode devolver fallback mas sempre pelo menos 1 item
        self.assertIsInstance(monitores, list)
        self.assertGreaterEqual(len(monitores), 1)

    def test_cada_monitor_tem_campos_esperados(self):
        monitores = server.list_monitors()
        for m in monitores:
            self.assertIn("indice", m)
            self.assertIn("nome", m)
            self.assertIn("x", m)
            self.assertIn("y", m)
            self.assertIn("width", m)
            self.assertIn("height", m)
            self.assertIn("primario", m)


class ProjetorManagerTests(unittest.TestCase):
    """Abrir/fechar projetores via subprocess, com tracking."""

    def setUp(self):
        self.mgr = server.ProjetorManager()

    def tearDown(self):
        self.mgr.fechar_todos()

    def _fake_popen(self):
        """Retorna MagicMock que imita subprocess.Popen."""
        p = mock.MagicMock()
        p.pid = 12345
        p.poll.return_value = None
        return p

    def test_abrir_registra_projetor(self):
        monitor = {"indice": 0, "nome": "DISPLAY1", "x": 0, "y": 0,
                    "width": 1920, "height": 1080, "primario": True}
        with mock.patch("subprocess.Popen", return_value=self._fake_popen()) as mo:
            pid = self.mgr.abrir(monitor, "http://localhost:5000/?kiosk=1")
        self.assertIsNotNone(pid)
        self.assertEqual(len(self.mgr.abertos()), 1)
        self.assertIn(pid, {p["pid"] for p in self.mgr.abertos()})
        # Confirma que a URL e flags estao certas
        args = mo.call_args[0][0]
        self.assertIn("--window-position=0,0", args)
        self.assertIn("--window-size=1920,1080", args)

    def test_fechar_remove_do_tracking(self):
        monitor = {"indice": 0, "nome": "DISPLAY1", "x": 0, "y": 0,
                    "width": 1920, "height": 1080, "primario": True}
        with mock.patch("subprocess.Popen", return_value=self._fake_popen()):
            pid = self.mgr.abrir(monitor, "http://localhost:5000/?kiosk=1")
        self.mgr.fechar(pid)
        self.assertEqual(len(self.mgr.abertos()), 0)

    def test_fechar_todos(self):
        m1 = {"indice": 0, "nome": "DISPLAY1", "x": 0, "y": 0,
              "width": 1920, "height": 1080, "primario": True}
        m2 = {"indice": 1, "nome": "DISPLAY2", "x": 1920, "y": 0,
              "width": 1920, "height": 1080, "primario": False}
        with mock.patch("subprocess.Popen", side_effect=[self._fake_popen(),
                                                          self._fake_popen()]):
            self.mgr.abrir(m1, "http://x")
            self.mgr.abrir(m2, "http://x")
        self.mgr.fechar_todos()
        self.assertEqual(len(self.mgr.abertos()), 0)

    def test_abertos_inclui_monitor_nome(self):
        monitor = {"indice": 0, "nome": "DISPLAY1", "x": 0, "y": 0,
                    "width": 1920, "height": 1080, "primario": True}
        with mock.patch("subprocess.Popen", return_value=self._fake_popen()):
            self.mgr.abrir(monitor, "http://localhost:5000/?kiosk=1")
        ab = self.mgr.abertos()
        self.assertEqual(ab[0]["monitor"]["nome"], "DISPLAY1")

    def test_gc_remove_morto_do_tracking(self):
        monitor = {"indice": 0, "nome": "DISPLAY1", "x": 0, "y": 0,
                    "width": 1920, "height": 1080, "primario": True}
        p = self._fake_popen()
        with mock.patch("subprocess.Popen", return_value=p):
            pid = self.mgr.abrir(monitor, "http://x")
        # Simula processo morto
        p.poll.return_value = 0
        self.mgr.gc()
        self.assertEqual(len(self.mgr.abertos()), 0)


if __name__ == "__main__":
    unittest.main()
