"""Testes da validacao do POST /admin/api/config."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.conftest_helpers import make_images  # noqa: E402

import server  # noqa: E402


def _cfg_base(palestrantes: list[dict]) -> dict:
    return {
        "vmix": {"host": "localhost", "port": 8088},
        "server_port": 5000,
        "palestrantes": palestrantes,
    }


class ValidarConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pasta_ok = self.root / "pasta_ok"
        make_images(self.pasta_ok, ["a.png", "b.png"])
        self.pasta_sem_imgs = self.root / "sem_imgs"
        self.pasta_sem_imgs.mkdir()
        (self.pasta_sem_imgs / "leiame.txt").write_text("x")

    def tearDown(self):
        self.tmp.cleanup()

    def test_aceita_config_vazia_bem_formada(self):
        erros = server.validar_config(_cfg_base([]))
        self.assertEqual(erros, [])

    def test_aceita_palestrante_valido(self):
        erros = server.validar_config(_cfg_base([
            {"nome": "Wagner", "guid": "abc-123", "pasta": str(self.pasta_ok)},
        ]))
        self.assertEqual(erros, [])

    def test_rejeita_nao_dict(self):
        erros = server.validar_config([])
        self.assertTrue(any("objeto" in e.lower() for e in erros))

    def test_rejeita_palestrantes_nao_lista(self):
        erros = server.validar_config({"palestrantes": "foo"})
        self.assertTrue(any("palestrantes" in e for e in erros))

    def test_rejeita_sem_nome(self):
        erros = server.validar_config(_cfg_base([
            {"nome": "", "guid": "abc-123", "pasta": str(self.pasta_ok)},
        ]))
        self.assertTrue(any("nome" in e for e in erros))

    def test_rejeita_sem_guid(self):
        erros = server.validar_config(_cfg_base([
            {"nome": "X", "guid": "", "pasta": str(self.pasta_ok)},
        ]))
        self.assertTrue(any("guid" in e for e in erros))

    def test_rejeita_pasta_vazia(self):
        erros = server.validar_config(_cfg_base([
            {"nome": "X", "guid": "abc", "pasta": ""},
        ]))
        self.assertTrue(any("pasta" in e for e in erros))

    def test_rejeita_guid_duplicado(self):
        erros = server.validar_config(_cfg_base([
            {"nome": "A", "guid": "same-guid", "pasta": str(self.pasta_ok)},
            {"nome": "B", "guid": "SAME-GUID", "pasta": str(self.pasta_ok)},
        ]))
        self.assertTrue(any("duplicado" in e.lower() for e in erros))

    def test_rejeita_pasta_inexistente(self):
        erros = server.validar_config(_cfg_base([
            {"nome": "X", "guid": "abc", "pasta": str(self.root / "nao_existe")},
        ]))
        self.assertTrue(any("nao existe" in e.lower() or "não existe" in e.lower() for e in erros))

    def test_rejeita_pasta_sem_imagens(self):
        erros = server.validar_config(_cfg_base([
            {"nome": "X", "guid": "abc", "pasta": str(self.pasta_sem_imgs)},
        ]))
        self.assertTrue(any("imagens" in e.lower() or "imagem" in e.lower() for e in erros))


class SalvarConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.pasta_ok = self.root / "slides"
        make_images(self.pasta_ok, ["slide 01.png"])
        self.config_path = self.root / "config.json"
        self.config_path.write_text(json.dumps({
            "vmix": {"host": "localhost", "port": 8088},
            "server_port": 5000,
            "palestrantes": [],
        }, ensure_ascii=False), encoding="utf-8")

        self._orig_cfg_path = server.CONFIG_PATH
        self._orig_cfg = server.CFG
        self._orig_pal = server.PALESTRANTES
        server.CONFIG_PATH = self.config_path

    def tearDown(self):
        server.CONFIG_PATH = self._orig_cfg_path
        server.CFG = self._orig_cfg
        server.PALESTRANTES = self._orig_pal
        self.tmp.cleanup()

    def test_salva_config_valida(self):
        novo = _cfg_base([
            {"nome": "Wagner", "guid": "guid-wagner", "pasta": str(self.pasta_ok)},
        ])
        server.salvar_config(novo)
        lido = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(len(lido["palestrantes"]), 1)
        self.assertIn("guid-wagner", server.PALESTRANTES)

    def test_nao_sobrescreve_quando_invalido(self):
        antes = self.config_path.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            server.salvar_config(_cfg_base([
                {"nome": "X", "guid": "g", "pasta": str(self.root / "fake")},
            ]))
        depois = self.config_path.read_text(encoding="utf-8")
        self.assertEqual(antes, depois)

    def test_value_error_carrega_lista_de_erros(self):
        try:
            server.salvar_config(_cfg_base([
                {"nome": "", "guid": "g", "pasta": ""},
            ]))
            self.fail("deveria ter levantado ValueError")
        except ValueError as e:
            self.assertEqual(e.args[0], "config_invalida")
            erros = e.args[1]
            self.assertIsInstance(erros, list)
            self.assertTrue(len(erros) >= 2)


if __name__ == "__main__":
    unittest.main()
