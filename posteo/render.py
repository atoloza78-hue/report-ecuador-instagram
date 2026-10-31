"""Dibuja el post de Instagram con la línea gráfica de Report Ecuador.

Medidas tomadas de los posts originales (1295 × 1600 px):
foto arriba (alto 1030), bloque rojo abajo con degradado, cuadritos y mapamundi,
línea amarilla arriba a la izquierda, línea roja sobre la foto, logo arriba a la
derecha, categoría con subrayado amarillo, titular con parte resaltada en
amarillo y el dominio centrado abajo.
"""
import io
import os
import re
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import config

RAIZ = Path(__file__).resolve().parent.parent
ASSETS = RAIZ / "assets"

W, H, FOTO_H, MARGEN = 1295, 1600, 1030, 64
AMARILLO_LINEA = (255, 213, 4)
ROJO_LINEA = (211, 12, 26)
AMARILLO_SUBRAYADO = (242, 201, 15)
AMARILLO_TEXTO = (255, 213, 7)
BLANCO = (255, 255, 255)
SOMBRA = (40, 0, 0, 140)
ANCHO_TITULAR = 1000

_FUENTE = None


def ruta_fuente() -> Path:
    """Bitter ExtraBold (800). Se descarga de Google Fonts la primera vez."""
    global _FUENTE
    if _FUENTE:
        return _FUENTE
    env = os.environ.get("FONT_PATH")
    if env and Path(env).exists():
        _FUENTE = Path(env)
        return _FUENTE
    destino = ASSETS / "Bitter-ExtraBold.ttf"
    if not destino.exists():
        css = requests.get(
            "https://fonts.googleapis.com/css2?family=Bitter:wght@800",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=30,
        ).text
        url = re.findall(r"url\((https://[^)]+)\)", css)[-1]
        destino.write_bytes(requests.get(url, timeout=60).content)
    _FUENTE = destino
    return _FUENTE


def fuente(tam: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(ruta_fuente()), tam)


def ancho(texto: str, f, espaciado: float) -> float:
    total = sum(f.getlength(c) + espaciado for c in texto)
    return total - espaciado if texto else 0


def partir_resaltado(titulo: str):
    """Convierte '*Parte amarilla* resto' en [(palabra, resaltada), ...]."""
    palabras, resaltar = [], False
    for w in re.sub(r"\s+", " ", titulo).strip().split(" "):
        cerrar = False
        if w.startswith("*"):
            resaltar, w = True, w[1:]
        if w.endswith("*"):
            w, cerrar = w[:-1], True
        if w:
            palabras.append((w, resaltar))
        if cerrar:
            resaltar = False
    return palabras


def maquetar(palabras, tam):
    f = fuente(tam)
    esp = tam * 0.026
    sp = f.getlength(" ") + esp * 2
    lineas, actual, w_linea, demasiado_ancha = [[]], 0, 0.0, False
    for texto, res in palabras:
        ww = ancho(texto, f, esp)
        if ww > ANCHO_TITULAR:
            demasiado_ancha = True
        if lineas[-1] and w_linea + sp + ww > ANCHO_TITULAR:
            lineas.append([])
            w_linea = 0.0
        w_linea += (sp if lineas[-1] else 0) + ww
        lineas[-1].append((texto, res, ww))
    return lineas, sp, esp, demasiado_ancha


def recortar_foto(foto: Image.Image, enfoque_x=0.5, enfoque_y=0.5) -> Image.Image:
    foto = foto.convert("RGB")
    escala = max(W / foto.width, FOTO_H / foto.height)
    nw, nh = round(foto.width * escala), round(foto.height * escala)
    foto = foto.resize((nw, nh), Image.LANCZOS)
    x = round((nw - W) * enfoque_x)
    y = round((nh - FOTO_H) * enfoque_y)
    return foto.crop((x, y, x + W, y + FOTO_H))


def generar_post(foto: Image.Image, categoria: str, titulo: str,
                 enfoque_x=0.5, enfoque_y=0.5) -> Image.Image:
    lienzo = Image.new("RGB", (W, H), (142, 16, 24))
    lienzo.paste(recortar_foto(foto, enfoque_x, enfoque_y), (0, 0))
    lienzo.paste(Image.open(ASSETS / "fondo-bloque.jpg").convert("RGB").resize((W, H - FOTO_H)), (0, FOTO_H))

    d = ImageDraw.Draw(lienzo)
    d.rectangle([0, 44, 795 - 1, 44 + 8 - 1], fill=AMARILLO_LINEA)
    d.rectangle([505, 967, W - 1, 967 + 8 - 1], fill=ROJO_LINEA)

    logo = Image.open(ASSETS / "logo.png").convert("RGBA")
    lw = 163
    logo = logo.resize((lw, round(lw * logo.height / logo.width)), Image.LANCZOS)
    lienzo.paste(logo, (1074, 22), logo)

    # Textos: (texto, x, y_base, tamaño, espaciado, color)
    textos = []
    cat = categoria.upper()
    textos.append((cat, MARGEN, 1135, 58, 1.1, BLANCO))
    ancho_cat = ancho(cat, fuente(58), 1.1)

    palabras = partir_resaltado(titulo)
    tam = 76
    while tam >= 56:
        lineas, sp, esp, ancha = maquetar(palabras, tam)
        if len(lineas) <= 3 and not ancha:
            break
        tam -= 2
    else:
        tam = 56
        lineas, sp, esp, ancha = maquetar(palabras, tam)
    interlineado = round(tam * 81 / 76)
    y = 1238 - (76 - tam) * 0.6
    for linea in lineas:
        x = MARGEN
        for texto, res, ww in linea:
            textos.append((texto, x, y, tam, esp, AMARILLO_TEXTO if res else BLANCO))
            x += ww + sp
        y += interlineado

    dom_f = fuente(41)
    dom_w = ancho(config.DOMINIO_POST, dom_f, 3.9)
    textos.append((config.DOMINIO_POST, W / 2 - dom_w / 2, 1546, 41, 3.9, BLANCO))

    # Sombra (desplazada 4,5 y desenfocada), luego el texto encima.
    mascara = Image.new("L", (W, H), 0)
    dm = ImageDraw.Draw(mascara)
    for texto, x, yb, tam_t, esp_t, _ in textos:
        f = fuente(tam_t)
        cx = x
        for c in texto:
            dm.text((cx + 4, yb + 5), c, font=f, fill=255, anchor="ls")
            cx += f.getlength(c) + esp_t
    mascara = mascara.filter(ImageFilter.GaussianBlur(2.5))
    capa_sombra = Image.new("RGBA", (W, H), SOMBRA[:3] + (0,))
    capa_sombra.putalpha(mascara.point(lambda v: v * SOMBRA[3] // 255))
    lienzo = Image.alpha_composite(lienzo.convert("RGBA"), capa_sombra)

    d = ImageDraw.Draw(lienzo)
    d.rectangle([MARGEN - 3, 1156, MARGEN - 3 + ancho_cat + 6, 1156 + 4 - 1], fill=AMARILLO_SUBRAYADO)
    for texto, x, yb, tam_t, esp_t, color in textos:
        f = fuente(tam_t)
        cx = x
        for c in texto:
            d.text((cx, yb), c, font=f, fill=color, anchor="ls")
            cx += f.getlength(c) + esp_t

    return lienzo.convert("RGB")


def guardar_jpg(img: Image.Image, ruta: Path):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    img.save(ruta, "JPEG", quality=92, optimize=True)


def foto_desde_url(url: str) -> Image.Image:
    r = requests.get(url, timeout=60, headers={"User-Agent": "ReportEcuadorBot/1.0"})
    r.raise_for_status()
    return Image.open(io.BytesIO(r.content))
