"""Gera o icone .ico do apresentador.

Design: representacao do layout do modo apresentador em si —
slide atual (menor, borda vermelha) a esquerda + slide proximo
(maior, borda amarela) a direita. Fundo escuro do dashboard.
Exporta multi-tamanho (16/32/48/64/128/256) em assets/icon.ico.

Uso:
    pip install Pillow
    python scripts/gerar_icone.py
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


OUT = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
OUT_ALERT = Path(__file__).resolve().parent.parent / "assets" / "icon_alert.ico"
PNG_PREVIEW = OUT.with_suffix(".png")
PNG_PREVIEW_ALERT = OUT_ALERT.with_suffix(".png")

# Paleta (mesmas do index.html + admin.html)
# v0.5.0: vermelho reservado pra alerta; atual = verde; progresso = azul.
BG_DARK = (0x1A, 0x1D, 0x23, 255)       # fundo de card do admin
SLIDE_BG = (0xE8, 0xEA, 0xED, 255)       # cinza claro (miolo do slide)
GREEN = (0x2E, 0xA0, 0x43, 255)          # borda slide atual (verde saturado)
YELLOW = (0xF2, 0xB7, 0x05, 255)          # borda slide proximo
BLUE_A = (0x3B, 0x82, 0xF6, 255)          # inicio do gradient da progress
BLUE_B = (0x0E, 0xA5, 0xE9, 255)          # fim do gradient da progress


def make_icon(size: int = 512) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fundo escuro com bordas arredondadas (estilo card)
    radius_bg = int(size * 0.18)
    draw.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=radius_bg,
        fill=BG_DARK,
    )

    # Layout dos 2 slides (proporcao 38/62 igual ao modo apresentador)
    pad = int(size * 0.12)
    gap = int(size * 0.04)
    avail_w = size - 2 * pad - gap

    w_left = int(avail_w * 38 / 100)
    w_right = int(avail_w * 62 / 100)
    h_left = int(w_left * 9 / 16)
    h_right = int(w_right * 9 / 16)

    y_left = (size - h_left) // 2
    y_right = (size - h_right) // 2

    x_left = pad
    x_right = x_left + w_left + gap

    border = max(6, int(size * 0.022))
    corner = max(2, int(size * 0.015))

    # Slide ATUAL (esquerda, menor, borda verde)
    draw.rounded_rectangle(
        [(x_left, y_left), (x_left + w_left, y_left + h_left)],
        radius=corner,
        fill=SLIDE_BG,
        outline=GREEN,
        width=border,
    )

    # Slide PROXIMO (direita, maior, borda amarela)
    draw.rounded_rectangle(
        [(x_right, y_right), (x_right + w_right, y_right + h_right)],
        radius=corner,
        fill=SLIDE_BG,
        outline=YELLOW,
        width=border,
    )

    # Barra de progresso embaixo (gradiente azul claro -> azul)
    bar_y = int(size * 0.82)
    bar_x0 = pad
    bar_x1 = size - pad
    bar_h = max(3, int(size * 0.015))
    steps = 40
    for i in range(steps):
        t = i / (steps - 1)
        r = int(BLUE_A[0] + (BLUE_B[0] - BLUE_A[0]) * t)
        g = int(BLUE_A[1] + (BLUE_B[1] - BLUE_A[1]) * t)
        b = int(BLUE_A[2] + (BLUE_B[2] - BLUE_A[2]) * t)
        x0 = int(bar_x0 + (bar_x1 - bar_x0) * i / steps)
        x1 = int(bar_x0 + (bar_x1 - bar_x0) * (i + 1) / steps)
        draw.rectangle([(x0, bar_y), (x1, bar_y + bar_h)], fill=(r, g, b, 255))

    # Aplica mascara arredondada final pra cortar tudo o que saiu do quadrado arredondado
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=radius_bg,
        fill=255,
    )
    img.putalpha(mask)
    return img


def make_icon_alert(size: int = 512) -> Image.Image:
    """Variante com badge de alerta vermelho no canto — indica problema."""
    img = make_icon(size)
    draw = ImageDraw.Draw(img)
    RED_ALERT = (0xDC, 0x26, 0x26, 255)   # red-600
    WHITE = (0xFF, 0xFF, 0xFF, 255)

    # Circulo vermelho no canto superior direito (~30% do tamanho)
    r = int(size * 0.32)
    cx = size - r // 2 - int(size * 0.04)
    cy = r // 2 + int(size * 0.04)
    draw.ellipse([(cx - r // 2, cy - r // 2),
                   (cx + r // 2, cy + r // 2)],
                  fill=RED_ALERT,
                  outline=WHITE,
                  width=max(3, int(size * 0.012)))

    # "!" branco no centro do circulo
    try:
        font = ImageFont.truetype("arialbd.ttf", int(r * 0.7))
    except (OSError, IOError):
        font = ImageFont.load_default()
    bbox = draw.textbbox((0, 0), "!", font=font)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    draw.text((cx - w // 2 - bbox[0], cy - h // 2 - bbox[1]),
               "!", fill=WHITE, font=font)
    return img


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)

    master = make_icon(512)
    master.save(PNG_PREVIEW, format="PNG")
    master.save(OUT, format="ICO",
                sizes=[(16, 16), (32, 32), (48, 48),
                       (64, 64), (128, 128), (256, 256)])
    print(f"Normal:  {OUT}")

    alerta = make_icon_alert(512)
    alerta.save(PNG_PREVIEW_ALERT, format="PNG")
    alerta.save(OUT_ALERT, format="ICO",
                 sizes=[(16, 16), (32, 32), (48, 48),
                         (64, 64), (128, 128), (256, 256)])
    print(f"Alerta:  {OUT_ALERT}")


if __name__ == "__main__":
    main()
