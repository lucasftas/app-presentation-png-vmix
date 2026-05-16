"""Testes do suporte a input List (VideoList) do vMix.

Cobre _kind_de, _basename, _parse_list_input, _estado_lista e a integracao
com compute_state quando o input ativo e um List misto (slides + videos).
"""
from __future__ import annotations

import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

from tests.conftest_helpers import fake_vmix_xml  # noqa: E402,F401

import server  # noqa: E402


LIST_GUID = "bbbbbbbb-0000-0000-0000-000000000001"


def _list_input(key, num, items, *, selected_idx=None, selected_attr=None,
                duration=None, position=None, itype="VideoList"):
    """Monta o XML de um input List com <list><item> filhos.

    `items`: lista de paths. `selected_attr`: indice (0-based) que recebe
    selected="true". `selected_idx`: valor do atributo selectedIndex do input.
    """
    attrs = f'key="{key}" number="{num}" type="{itype}" title="t"'
    if selected_idx is not None:
        attrs += f' selectedIndex="{selected_idx}"'
    if duration is not None:
        attrs += f' duration="{duration}"'
    if position is not None:
        attrs += f' position="{position}"'
    parts = [f"<input {attrs}><list>"]
    for i, path in enumerate(items):
        sel = ' selected="true"' if i == selected_attr else ""
        parts.append(f"<item{sel}>{path}</item>")
    parts.append("</list></input>")
    return "".join(parts)


def _vmix_com(input_xml, active_num):
    """vMix XML minimo com um unico input e ele em Program."""
    overlays = "".join(f'<overlay number="{n}" />' for n in range(1, 17))
    return (f"<vmix><version>29</version><inputs>{input_xml}</inputs>"
            f"<overlays>{overlays}</overlays>"
            f"<active>{active_num}</active></vmix>")


# Playlist mista tipica (espelha o preset real do usuario): PNG + MP4/MOV
ITENS_MISTOS = [
    r"A:\Editor - vMix\Slides\10.png",
    r"A:\Editor - vMix\Slides\11.png",
    r"A:\Editor - vMix\Slides\12.png",
    r"A:\Editor - vMix\Slides\13 - Video Abertura.mov",
    r"A:\Editor - vMix\Slides\14.png",
]


class KindDeTests(unittest.TestCase):
    def test_imagem(self):
        for n in ("10.png", "foto.JPG", "x.jpeg", "y.webp", "z.bmp"):
            self.assertEqual(server._kind_de(n), "imagem", n)

    def test_video(self):
        for n in ("a.mp4", "b.MOV", "c.mkv", "d.avi", "e.wmv", "f.ts", "g.m4v"):
            self.assertEqual(server._kind_de(n), "video", n)

    def test_outro(self):
        for n in ("x.txt", "y.mp3", "z", "audio.wav"):
            self.assertEqual(server._kind_de(n), "outro", n)


class BasenameTests(unittest.TestCase):
    def test_path_windows(self):
        self.assertEqual(server._basename(r"A:\pasta\sub\23.png"), "23.png")

    def test_path_posix(self):
        self.assertEqual(server._basename("/mnt/a/b/video.mp4"), "video.mp4")

    def test_vazio(self):
        self.assertEqual(server._basename(""), "")


class ParseListInputTests(unittest.TestCase):
    def test_selected_attr_define_atual(self):
        xml = _list_input(LIST_GUID, 5, ITENS_MISTOS, selected_attr=3)
        itens, idx = server._parse_list_input(ET.fromstring(xml))
        self.assertEqual(len(itens), 5)
        self.assertEqual(idx, 3)
        self.assertEqual(itens[3]["kind"], "video")
        self.assertEqual(itens[3]["nome"], "13 - Video Abertura.mov")
        self.assertEqual(itens[0]["kind"], "imagem")

    def test_selected_index_1based(self):
        # selectedIndex="4" com 5 itens -> 1-based -> item[3]
        xml = _list_input(LIST_GUID, 5, ITENS_MISTOS, selected_idx=4)
        _itens, idx = server._parse_list_input(ET.fromstring(xml))
        self.assertEqual(idx, 3)

    def test_selected_index_0based_fallback(self):
        # selectedIndex="0" so faz sentido como 0-based -> item[0]
        xml = _list_input(LIST_GUID, 5, ITENS_MISTOS, selected_idx=0)
        _itens, idx = server._parse_list_input(ET.fromstring(xml))
        self.assertEqual(idx, 0)

    def test_selected_attr_tem_prioridade_sobre_index(self):
        xml = _list_input(LIST_GUID, 5, ITENS_MISTOS,
                          selected_attr=2, selected_idx=99)
        _itens, idx = server._parse_list_input(ET.fromstring(xml))
        self.assertEqual(idx, 2)

    def test_sem_list_retorna_vazio(self):
        xml = f'<input key="{LIST_GUID}" number="5" type="VideoList" title="t"></input>'
        itens, idx = server._parse_list_input(ET.fromstring(xml))
        self.assertEqual(itens, [])
        self.assertIsNone(idx)

    def test_input_none(self):
        self.assertEqual(server._parse_list_input(None), ([], None))


class EstadoListaTests(unittest.TestCase):
    def _estado(self, **kw):
        xml = _list_input(LIST_GUID, 5, ITENS_MISTOS, **kw)
        return server._estado_lista({}, LIST_GUID, "Pitch", ET.fromstring(xml))

    def test_atual_imagem(self):
        e = self._estado(selected_attr=0)
        self.assertTrue(e["ativo"])
        self.assertEqual(e["tipo"], "list")
        self.assertEqual(e["indice"], 1)
        self.assertEqual(e["total"], 5)
        self.assertIsNotNone(e["atual_url"])
        self.assertIsNone(e["atual_video"])
        self.assertIn("/list-img/", e["atual_url"])

    def test_atual_video_com_duracao(self):
        e = self._estado(selected_attr=3, duration=125000, position=4200)
        self.assertIsNone(e["atual_url"])
        self.assertEqual(e["atual_video"]["kind"], "video")
        self.assertEqual(e["atual_video"]["nome"], "13 - Video Abertura.mov")
        self.assertEqual(e["atual_video"]["duracao_ms"], 125000)
        self.assertEqual(e["atual_video"]["posicao_ms"], 4200)

    def test_proximo_video(self):
        # atual = item[2] (imagem), proximo = item[3] (video)
        e = self._estado(selected_attr=2)
        self.assertIsNotNone(e["atual_url"])
        self.assertIsNone(e["proximo_url"])
        self.assertEqual(e["proximo_video"]["kind"], "video")
        # duracao NAO vem pro proximo (vMix nao expoe)
        self.assertNotIn("duracao_ms", e["proximo_video"])

    def test_fim_da_lista(self):
        e = self._estado(selected_attr=4)
        self.assertEqual(e["indice"], 5)
        self.assertIsNone(e["proximo_url"])
        self.assertIsNone(e["proximo_video"])

    def test_lista_vazia(self):
        xml = _list_input(LIST_GUID, 5, [])
        e = server._estado_lista({}, LIST_GUID, "Pitch", ET.fromstring(xml))
        self.assertFalse(e["ativo"])
        self.assertEqual(e["tipo"], "list")


class ComputeStateListTests(unittest.TestCase):
    def setUp(self):
        self._pal_orig = server.PALESTRANTES
        server.PALESTRANTES = {LIST_GUID: ("Pitch", None, [], "list")}

    def tearDown(self):
        server.PALESTRANTES = self._pal_orig

    def _patch(self, xml_str):
        return mock.patch.object(server, "fetch_vmix_xml",
                                 return_value=ET.fromstring(xml_str))

    def test_list_em_program_video_atual(self):
        inp = _list_input(LIST_GUID, 7, ITENS_MISTOS,
                          selected_attr=3, duration=90000)
        with self._patch(_vmix_com(inp, 7)):
            s = server.compute_state()
        self.assertTrue(s["ok"])
        self.assertTrue(s["ativo"])
        self.assertEqual(s["tipo"], "list")
        self.assertEqual(s["palestrante"], "Pitch")
        self.assertEqual(s["indice"], 4)
        self.assertEqual(s["total"], 5)
        self.assertEqual(s["atual_video"]["nome"], "13 - Video Abertura.mov")
        self.assertEqual(s["atual_video"]["duracao_ms"], 90000)

    def test_list_detecta_por_type_mesmo_sem_tipo_configurado(self):
        # palestrante configurado como photos, mas input e VideoList no vMix
        server.PALESTRANTES = {LIST_GUID: ("Pitch", None, [], "photos")}
        inp = _list_input(LIST_GUID, 7, ITENS_MISTOS, selected_attr=0)
        with self._patch(_vmix_com(inp, 7)):
            s = server.compute_state()
        self.assertEqual(s["tipo"], "list")
        self.assertTrue(s["ativo"])

    def test_list_aceita_type_List(self):
        inp = _list_input(LIST_GUID, 7, ITENS_MISTOS,
                          selected_attr=1, itype="List")
        with self._patch(_vmix_com(inp, 7)):
            s = server.compute_state()
        self.assertEqual(s["tipo"], "list")
        self.assertEqual(s["indice"], 2)


class VmixListControlTests(unittest.TestCase):
    """next/prev/reset de input List traduzidos pra SelectIndex (1-based)."""

    def _patch(self, selected_attr):
        inp = _list_input(LIST_GUID, 7, ITENS_MISTOS, selected_attr=selected_attr)
        return (
            mock.patch.object(server, "fetch_vmix_xml",
                              return_value=ET.fromstring(_vmix_com(inp, 7))),
            mock.patch.object(server, "vmix_control", return_value={"ok": True}),
        )

    def test_next_avanca_um(self):
        p_xml, p_ctl = self._patch(selected_attr=1)
        with p_xml, p_ctl as mc:
            r = server.vmix_list_control(LIST_GUID, "next")
        self.assertTrue(r["ok"])
        mc.assert_called_once_with("SelectIndex", LIST_GUID, "3")

    def test_prev_volta_um(self):
        p_xml, p_ctl = self._patch(selected_attr=2)
        with p_xml, p_ctl as mc:
            server.vmix_list_control(LIST_GUID, "prev")
        mc.assert_called_once_with("SelectIndex", LIST_GUID, "2")

    def test_next_no_fim_clampa(self):
        p_xml, p_ctl = self._patch(selected_attr=4)  # ultimo item
        with p_xml, p_ctl as mc:
            server.vmix_list_control(LIST_GUID, "next")
        mc.assert_called_once_with("SelectIndex", LIST_GUID, "5")

    def test_reset_vai_pro_primeiro(self):
        with mock.patch.object(server, "vmix_control",
                               return_value={"ok": True}) as mc:
            server.vmix_list_control(LIST_GUID, "reset")
        mc.assert_called_once_with("SelectIndex", LIST_GUID, "1")


class ThumbTests(unittest.TestCase):
    """Geracao de thumbnails de video (botao "Gerar frames dos videos")."""

    def test_thumb_path(self):
        p = server._thumb_path(Path(r"A:\vids\B - Pitch\13.mov"))
        self.assertEqual(p.name, "13.mov.jpg")
        self.assertEqual(p.parent.name, "_thumbpresentation")
        self.assertEqual(p.parent.parent.name, "B - Pitch")

    def test_gerar_thumb_arquivo_inexistente(self):
        st = server.gerar_thumb_video(Path("nao_existe_xyz_zzz.mov"))
        self.assertIn(st, ("falhou", "sem_ffmpeg"))

    @unittest.skipUnless(server._FFMPEG, "ffmpeg nao instalado")
    def test_gerar_thumb_video_real(self):
        with tempfile.TemporaryDirectory() as d:
            vid = Path(d) / "clip.mp4"
            subprocess.run(
                [server._FFMPEG, "-y", "-f", "lavfi",
                 "-i", "testsrc=size=320x240:rate=10", "-t", "1", str(vid)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            self.assertTrue(vid.is_file())
            self.assertEqual(server.gerar_thumb_video(vid), "gerado")
            thumb = server._thumb_path(vid)
            self.assertTrue(thumb.is_file())
            self.assertGreater(thumb.stat().st_size, 0)
            # segunda chamada nao regenera (thumb mais novo que o video)
            self.assertEqual(server.gerar_thumb_video(vid), "existia")

class ThumbsWorkerTests(unittest.TestCase):
    """_thumbs_worker — geracao de thumbs em background com registro de job."""

    def tearDown(self):
        server._thumbs_jobs.pop(LIST_GUID, None)

    def test_processa_so_videos_e_atualiza_job(self):
        xml = _list_input(LIST_GUID, 7,
                          [r"X:\v\a.png", r"X:\v\b.mp4", r"X:\v\c.mov"],
                          selected_attr=0)
        server._thumbs_jobs[LIST_GUID] = server._novo_job_thumbs(LIST_GUID)
        with mock.patch.object(server, "fetch_vmix_xml",
                               return_value=ET.fromstring(_vmix_com(xml, 7))), \
             mock.patch.object(server, "gerar_thumb_video", return_value="gerado"), \
             mock.patch.object(server, "_ensure_dur", return_value=1000):
            server._thumbs_worker(LIST_GUID)
        job = server._thumbs_jobs[LIST_GUID]
        self.assertEqual(job["status"], "concluido")
        self.assertEqual(job["total"], 2)        # b.mp4 + c.mov, ignora a.png
        self.assertEqual(job["processados"], 2)
        self.assertEqual(job["gerados"], 2)
        self.assertEqual(job["falharam"], 0)
        self.assertIsNotNone(job["concluido_em"])

    def test_conta_falhas(self):
        xml = _list_input(LIST_GUID, 7, [r"X:\v\b.mp4", r"X:\v\c.mov"],
                          selected_attr=0)
        server._thumbs_jobs[LIST_GUID] = server._novo_job_thumbs(LIST_GUID)
        with mock.patch.object(server, "fetch_vmix_xml",
                               return_value=ET.fromstring(_vmix_com(xml, 7))), \
             mock.patch.object(server, "gerar_thumb_video", return_value="falhou"), \
             mock.patch.object(server, "_ensure_dur", return_value=None):
            server._thumbs_worker(LIST_GUID)
        job = server._thumbs_jobs[LIST_GUID]
        self.assertEqual(job["status"], "concluido")
        self.assertEqual(job["falharam"], 2)
        self.assertEqual(len(job["falhas"]), 2)

    def test_vmix_offline_marca_erro(self):
        server._thumbs_jobs[LIST_GUID] = server._novo_job_thumbs(LIST_GUID)
        with mock.patch.object(server, "fetch_vmix_xml",
                               side_effect=OSError("vmix down")):
            server._thumbs_worker(LIST_GUID)
        job = server._thumbs_jobs[LIST_GUID]
        self.assertEqual(job["status"], "erro")
        self.assertIn("vMix", job["erro"])


if __name__ == "__main__":
    unittest.main()
