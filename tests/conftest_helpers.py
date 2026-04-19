"""Helpers reutilizaveis pelos testes unitarios (stdlib only).

Nao depende de pytest — usado dentro de unittest.TestCase via import.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable


# Garante que `import server` funcione em qualquer teste do pacote
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def make_images(dir_path: Path, nomes: Iterable[str]) -> list[Path]:
    """Cria arquivos vazios com os nomes dados em `dir_path`.

    `nomes` pode conter extensoes misturadas (png, jpg, txt, etc).
    Retorna lista de Paths criados.
    """
    dir_path.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for nome in nomes:
        p = dir_path / nome
        p.write_bytes(b"")  # conteudo vazio — testes so checam listagem
        created.append(p)
    return created


def fake_vmix_xml(inputs: list[dict], active_num: int = 1,
                  overlays_global: list[tuple[int, int]] | None = None,
                  preset: str = "") -> str:
    """Monta XML minimo que `compute_state` entende.

    `inputs`: lista de dicts com chaves: num, key, type, title, shortTitle,
              selectedIndex, duration, overlays (lista de {index, key})
    `overlays_global`: lista de (overlay_num, input_num) para <overlays>
    """
    parts = ["<vmix>", "<version>29.0.0.0</version>"]
    if preset:
        parts.append(f"<preset>{preset}</preset>")
    parts.append("<inputs>")
    for inp in inputs:
        attrs = (
            f'key="{inp["key"]}" number="{inp["num"]}" '
            f'type="{inp["type"]}" title="{inp.get("title","")}" '
            f'shortTitle="{inp.get("shortTitle","")}"'
        )
        if "selectedIndex" in inp:
            attrs += f' selectedIndex="{inp["selectedIndex"]}"'
        if "duration" in inp:
            attrs += f' duration="{inp["duration"]}"'
        parts.append(f"<input {attrs}>")
        parts.append(inp.get("title", ""))
        for ov in inp.get("overlays", []) or []:
            parts.append(f'<overlay index="{ov["index"]}" key="{ov["key"]}" />')
        parts.append("</input>")
    parts.append("</inputs>")

    parts.append("<overlays>")
    if overlays_global:
        taken = {n for n, _ in overlays_global}
        for n, input_num in overlays_global:
            parts.append(f'<overlay number="{n}">{input_num}</overlay>')
        for n in range(1, 17):
            if n not in taken:
                parts.append(f'<overlay number="{n}" />')
    else:
        for n in range(1, 17):
            parts.append(f'<overlay number="{n}" />')
    parts.append("</overlays>")

    parts.append(f"<active>{active_num}</active>")
    parts.append("</vmix>")
    return "".join(parts)
