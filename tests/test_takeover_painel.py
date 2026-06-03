"""Regressao v1.3.0: relaunch-takeover + Painel (fallback de controle sem tray).

- `_matar_outras_instancias`: SEGURANCA — em dev (nao-frozen) NUNCA mata nada
  (taskkill por nome derrubaria python.exe); so age no exe frozen no Windows.
- `_escrever_painel_url`: grava o .url do Dashboard com o porto real.
- `_abrir_dashboard`: abre /admin e nunca propaga excecao.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.conftest_helpers import make_images  # noqa: F401 (ajusta sys.path)

import server  # noqa: E402


class MatarOutrasInstanciasTests(unittest.TestCase):
    def test_dev_nao_mata_nada(self):
        # Em dev (sys.frozen ausente/False) NUNCA chamar taskkill — mataria
        # outros python.exe da maquina.
        with mock.patch.object(server.sys, "frozen", False, create=True), \
             mock.patch("subprocess.run") as run:
            server._matar_outras_instancias()
        run.assert_not_called()

    def test_frozen_win32_chama_taskkill_excluindo_self(self):
        with mock.patch.object(server.sys, "frozen", True, create=True), \
             mock.patch.object(server.sys, "platform", "win32"), \
             mock.patch("subprocess.run") as run:
            server._matar_outras_instancias()
        run.assert_called_once()
        argv = run.call_args[0][0]
        self.assertEqual(argv[0], "taskkill")
        self.assertIn("/IM", argv)
        self.assertIn("/F", argv)
        # exclui o proprio PID pra nao se matar
        self.assertTrue(any(a.startswith("PID ne ") for a in argv))


class EscreverPainelUrlTests(unittest.TestCase):
    def test_grava_url_com_porto_real(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(server, "APP_DIR", Path(d)):
                server._escrever_painel_url(5003)
                txt = (Path(d) / server.PAINEL_URL_NAME).read_text(encoding="ascii")
        self.assertIn("[InternetShortcut]", txt)
        self.assertIn("URL=http://localhost:5003/admin", txt)

    def test_porto_diferente_reescreve(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(server, "APP_DIR", Path(d)):
                server._escrever_painel_url(5000)
                server._escrever_painel_url(5007)
                txt = (Path(d) / server.PAINEL_URL_NAME).read_text(encoding="ascii")
        self.assertIn("5007", txt)
        self.assertNotIn("5000", txt)


class AbrirDashboardTests(unittest.TestCase):
    def test_abre_url_admin(self):
        with mock.patch("webbrowser.open") as wb:
            server._abrir_dashboard(5001)
        wb.assert_called_once_with("http://localhost:5001/admin")

    def test_nao_propaga_excecao(self):
        with mock.patch("webbrowser.open", side_effect=RuntimeError("falha")):
            server._abrir_dashboard(5000)  # nao deve levantar


if __name__ == "__main__":
    unittest.main()
