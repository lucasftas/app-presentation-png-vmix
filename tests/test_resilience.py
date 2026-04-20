"""Testes de resiliencia v0.7.0: port fallback, single-instance, health check, watcher."""
from __future__ import annotations

import socket
import threading
import time
import unittest
from unittest import mock

from tests.conftest_helpers import make_images  # noqa: F401 (ajusta sys.path)

import server  # noqa: E402


class PortFallbackTests(unittest.TestCase):
    """Fase 1: encontra proxima porta livre se a preferida estiver ocupada."""

    def test_encontra_porta_livre_na_primeira_tentativa(self):
        # Porta alta improvavel de estar ocupada
        porta, srv = server.bind_com_fallback(60001, max_tentativas=3)
        self.assertEqual(porta, 60001)
        srv.server_close()

    def test_faz_fallback_se_porta_ocupada(self):
        # Ocupa 60010 primeiro
        s_dummy = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s_dummy.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        s_dummy.bind(("", 60010))
        s_dummy.listen(1)
        try:
            porta, srv = server.bind_com_fallback(60010, max_tentativas=5)
            self.assertNotEqual(porta, 60010)
            self.assertGreater(porta, 60010)
            srv.server_close()
        finally:
            s_dummy.close()

    def test_levanta_se_todas_portas_ocupadas(self):
        # Ocupa 60020, 60021
        dummies = []
        try:
            for p in (60020, 60021):
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
                s.bind(("", p))
                s.listen(1)
                dummies.append(s)
            with self.assertRaises(OSError):
                server.bind_com_fallback(60020, max_tentativas=2)
        finally:
            for s in dummies:
                s.close()


class SingleInstanceTests(unittest.TestCase):
    """Fase 1: segunda instancia deve detectar mutex e falhar graciosamente."""

    def test_primeira_aquisicao_retorna_true(self):
        nome = f"TestMutex_{time.time_ns()}"
        handle = server.aquirir_single_instance(nome)
        self.assertIsNotNone(handle)
        self.assertTrue(handle.adquirido)
        handle.release()

    def test_segunda_aquisicao_retorna_false(self):
        nome = f"TestMutex_{time.time_ns()}"
        primeira = server.aquirir_single_instance(nome)
        self.assertTrue(primeira.adquirido)
        try:
            segunda = server.aquirir_single_instance(nome)
            self.assertFalse(segunda.adquirido)
            segunda.release()
        finally:
            primeira.release()


class HealthCheckInternoTests(unittest.TestCase):
    """Fase 2: thread daemon verifica se o HTTP server ainda responde."""

    def test_health_check_retorna_true_com_server_ok(self):
        # Mock urlopen retornando 200
        m = mock.MagicMock()
        m.__enter__.return_value.status = 200
        m.__exit__.return_value = None
        with mock.patch("urllib.request.urlopen", return_value=m):
            self.assertTrue(server.http_self_check(porta=5000, timeout=0.5))

    def test_health_check_retorna_false_com_server_morto(self):
        with mock.patch("urllib.request.urlopen", side_effect=ConnectionRefusedError()):
            self.assertFalse(server.http_self_check(porta=5000, timeout=0.5))

    def test_health_check_retorna_false_com_timeout(self):
        import urllib.error
        with mock.patch("urllib.request.urlopen",
                        side_effect=urllib.error.URLError("timeout")):
            self.assertFalse(server.http_self_check(porta=5000, timeout=0.5))


class ConfigWatcherTests(unittest.TestCase):
    """Fase 3: detecta edicao externa do config.json e recarrega."""

    def setUp(self):
        import tempfile, json
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg_path = Path(self.tmp.name) / "config.json"
        self.cfg_path.write_text(json.dumps({
            "vmix": {"host": "localhost", "port": 8088},
            "server_port": 5000,
            "palestrantes": [],
        }, ensure_ascii=False), encoding="utf-8")
        self._orig = server.CONFIG_PATH
        server.CONFIG_PATH = self.cfg_path

    def tearDown(self):
        server.CONFIG_PATH = self._orig
        self.tmp.cleanup()

    def test_detecta_mudanca_externa_no_mtime(self):
        watcher = server.ConfigWatcher()
        watcher.start()
        time.sleep(0.1)
        # Primeiro tick: sem mudanca
        self.assertEqual(watcher.mudancas_detectadas, 0)

        # Simula edicao externa
        time.sleep(0.1)
        import json
        self.cfg_path.write_text(json.dumps({
            "vmix": {"host": "10.0.0.5", "port": 8088},
            "server_port": 5000,
            "palestrantes": [],
        }, ensure_ascii=False), encoding="utf-8")

        # Aguarda detectar (poll a cada 1s)
        for _ in range(30):
            time.sleep(0.1)
            if watcher.mudancas_detectadas > 0:
                break

        self.assertGreaterEqual(watcher.mudancas_detectadas, 1)
        watcher.stop()


if __name__ == "__main__":
    unittest.main()
