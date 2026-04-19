"""Testes de compute_state, diagnosticar_palestrante e endpoints /health /validate."""
from __future__ import annotations

import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from tests.conftest_helpers import fake_vmix_xml, make_images  # noqa: E402

import server  # noqa: E402


WAGNER_GUID = "51f89804-b46f-4716-8914-4f692c63c38c"
VINI_GUID = "1cb3e57a-b400-4751-8c16-a5d5a88dfe03"
BLANK_WAGNER_GUID = "8ce11bad-a75a-42fa-9299-2d220b822a82"


def _inputs_basicos():
    """Cenario tipico: 1 Photos Wagner + 1 Colour que envelopa Wagner."""
    return [
        {
            "key": WAGNER_GUID, "num": 60, "type": "Photos",
            "title": "PNG SLIDE Wagner - slide 07.png",
            "shortTitle": "PNG SLIDE Wagner",
            "selectedIndex": 7, "duration": 49,
        },
        {
            "key": BLANK_WAGNER_GUID, "num": 61, "type": "Colour",
            "title": "B      SLIDES WAGNER + CAM",
            "shortTitle": "B SLIDES WAGNER + CAM",
            "overlays": [{"index": 1, "key": WAGNER_GUID}],
        },
    ]


def _xml_to_element(xml_str: str) -> ET.Element:
    return ET.fromstring(xml_str)


class MatchFilenameTests(unittest.TestCase):
    """Fase 1: match ancorado resolve ambiguidade slide 1 vs slide 10."""

    def test_match_exato_vence_substring(self):
        imagens = ["slide 1.png", "slide 10.png"]
        title = "PNG SLIDE Wagner - slide 10.png"
        idx = server.match_filename(title, imagens)
        self.assertEqual(idx, 1)  # slide 10

    def test_match_slide_1_quando_title_tem_slide_1(self):
        imagens = ["slide 1.png", "slide 10.png"]
        title = "PNG SLIDE Wagner - slide 1.png"
        idx = server.match_filename(title, imagens)
        self.assertEqual(idx, 0)  # slide 1

    def test_match_acento(self):
        imagens = ["introdução 01.jpg", "demonstração 02.jpg"]
        title = "PRESET - introdução 01.jpg"
        idx = server.match_filename(title, imagens)
        self.assertEqual(idx, 0)

    def test_match_suffix_case_insensitive(self):
        imagens = ["slide 05.png"]
        title = "foo - SLIDE 05.PNG"
        idx = server.match_filename(title, imagens)
        self.assertEqual(idx, 0)

    def test_match_nenhum_retorna_none(self):
        imagens = ["slide 01.png", "slide 02.png"]
        title = "completamente fora do padrao"
        self.assertIsNone(server.match_filename(title, imagens))

    def test_match_escolhe_mais_longo_em_caso_de_empate(self):
        imagens = ["a.png", "longo-a.png"]
        title = "prefix - longo-a.png"
        idx = server.match_filename(title, imagens)
        self.assertEqual(idx, 1)  # longo-a.png (mais especifico)


class ComputeStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name) / "wagner"
        make_images(self.pasta, [f"slide {i:02d}.png" for i in range(1, 50)])
        self._pal_orig = server.PALESTRANTES
        server.PALESTRANTES = {WAGNER_GUID: ("Wagner", self.pasta, sorted(p.name for p in self.pasta.iterdir()))}

    def tearDown(self):
        server.PALESTRANTES = self._pal_orig
        self.tmp.cleanup()

    def _patch_xml(self, xml_str: str):
        return mock.patch.object(server, "fetch_vmix_xml", return_value=_xml_to_element(xml_str))

    def test_program_direto_photos_detecta(self):
        xml = fake_vmix_xml(_inputs_basicos(), active_num=60)
        with self._patch_xml(xml):
            r = server.compute_state()
        self.assertTrue(r["ok"])
        self.assertTrue(r["ativo"])
        self.assertEqual(r["palestrante"], "Wagner")

    def test_program_blank_com_photos_em_overlay_detecta(self):
        xml = fake_vmix_xml(_inputs_basicos(), active_num=61)
        with self._patch_xml(xml):
            r = server.compute_state()
        self.assertTrue(r["ativo"])
        self.assertEqual(r["palestrante"], "Wagner")

    def test_overlay_global_com_blank_detecta(self):
        """Blank composto em overlay global 2, Program em outro input."""
        inputs = _inputs_basicos() + [
            {"key": "aaaaaaaa-0000", "num": 10, "type": "Camera", "title": "CAM 1"}
        ]
        xml = fake_vmix_xml(inputs, active_num=10, overlays_global=[(2, 61)])
        with self._patch_xml(xml):
            r = server.compute_state()
        self.assertTrue(r["ativo"])
        self.assertEqual(r["palestrante"], "Wagner")

    def test_nenhum_palestrante_em_nada(self):
        inputs = [{"key": "xx-00", "num": 1, "type": "Camera", "title": "CAM"}]
        xml = fake_vmix_xml(inputs, active_num=1)
        with self._patch_xml(xml):
            r = server.compute_state()
        self.assertTrue(r["ok"])
        self.assertFalse(r["ativo"])


class DiagnosticarPalestranteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name) / "wagner"
        make_images(self.pasta, [f"slide {i:02d}.png" for i in range(1, 50)])

    def tearDown(self):
        self.tmp.cleanup()

    def _diag(self, guid, nome, pasta, xml_str):
        root = _xml_to_element(xml_str)
        return server.diagnosticar_palestrante(guid, nome, str(pasta), root)

    def test_ok_quando_tudo_bate(self):
        xml = fake_vmix_xml(_inputs_basicos(), active_num=60)
        d = self._diag(WAGNER_GUID, "Wagner", self.pasta, xml)
        self.assertEqual(d["status"], "ok")
        self.assertEqual(d["total_no_vmix"], 49)
        self.assertEqual(d["total_na_pasta"], 49)

    def test_guid_orfao_quando_nao_existe(self):
        xml = fake_vmix_xml(_inputs_basicos(), active_num=60)
        d = self._diag("guid-que-nao-existe", "Fantasma", self.pasta, xml)
        self.assertEqual(d["status"], "guid_orfao")

    def test_pasta_inacessivel(self):
        xml = fake_vmix_xml(_inputs_basicos(), active_num=60)
        d = self._diag(WAGNER_GUID, "Wagner", "Z:\\nao\\existe\\nada", xml)
        self.assertEqual(d["status"], "pasta_inacessivel")

    def test_sem_imagens(self):
        with tempfile.TemporaryDirectory() as td:
            pasta_vazia = Path(td)
            (pasta_vazia / "leiame.txt").write_text("x")
            xml = fake_vmix_xml(_inputs_basicos(), active_num=60)
            d = self._diag(WAGNER_GUID, "Wagner", pasta_vazia, xml)
            self.assertEqual(d["status"], "sem_imagens")

    def test_filename_mismatch(self):
        inputs = _inputs_basicos()
        inputs[0]["title"] = "totalmente fora do padrao.png"
        xml = fake_vmix_xml(inputs, active_num=60)
        d = self._diag(WAGNER_GUID, "Wagner", self.pasta, xml)
        self.assertEqual(d["status"], "filename_mismatch")

    def test_pasta_vazia_string_pula_check_de_pasta(self):
        """Caso do /validate: pasta nao informada — so valida GUID."""
        xml = fake_vmix_xml(_inputs_basicos(), active_num=60)
        d = self._diag(WAGNER_GUID, "Wagner", "", xml)
        # Sem pasta: status 'ok' porque GUID existe; total_na_pasta = None
        self.assertIn(d["status"], ("ok", "sem_pasta"))


class HealthEndpointTests(unittest.TestCase):
    """Testa a logica interna que alimenta /admin/api/health."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name) / "wagner"
        make_images(self.pasta, [f"slide {i:02d}.png" for i in range(1, 50)])
        self._cfg_orig = server.CFG
        server.CFG = {
            "palestrantes": [
                {"nome": "Wagner", "guid": WAGNER_GUID, "pasta": str(self.pasta)},
                {"nome": "Fantasma", "guid": "guid-fantasma", "pasta": str(self.pasta)},
            ]
        }

    def tearDown(self):
        server.CFG = self._cfg_orig
        self.tmp.cleanup()

    def test_health_retorna_todos_com_status(self):
        xml = fake_vmix_xml(_inputs_basicos(), active_num=60)
        with mock.patch.object(server, "fetch_vmix_xml", return_value=_xml_to_element(xml)):
            resultado = server.diagnosticar_todos()
        self.assertEqual(len(resultado), 2)
        guids = {d["guid"] for d in resultado}
        self.assertEqual(guids, {WAGNER_GUID, "guid-fantasma"})
        por_guid = {d["guid"]: d["status"] for d in resultado}
        self.assertEqual(por_guid[WAGNER_GUID], "ok")
        self.assertEqual(por_guid["guid-fantasma"], "guid_orfao")


class ClientesConectadosTests(unittest.TestCase):
    """Fase 4: rastrear IPs que fizeram GET /state recentemente."""

    def setUp(self):
        # Limpa estado global entre testes
        server._CLIENTES.clear()

    def test_registrar_cliente_adiciona_com_timestamp(self):
        server.registrar_cliente("192.168.1.10")
        self.assertIn("192.168.1.10", server._CLIENTES)
        self.assertGreater(server._CLIENTES["192.168.1.10"], 0)

    def test_clientes_ativos_retorna_dentro_da_janela(self):
        import time
        server.registrar_cliente("10.0.0.1")
        server.registrar_cliente("10.0.0.2")
        ativos = server.clientes_ativos(janela_s=30)
        self.assertEqual(len(ativos), 2)
        ips = {c["ip"] for c in ativos}
        self.assertEqual(ips, {"10.0.0.1", "10.0.0.2"})

    def test_clientes_ativos_expira_apos_janela(self):
        import time
        server._CLIENTES["antigo"] = time.time() - 60  # 60s atras
        ativos = server.clientes_ativos(janela_s=30)
        self.assertNotIn("antigo", [c["ip"] for c in ativos])


if __name__ == "__main__":
    unittest.main()
