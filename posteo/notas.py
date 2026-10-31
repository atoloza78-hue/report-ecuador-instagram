"""Lee las notas de WordPress y prepara titular resaltado, categoría y caption."""
import html
import re
import unicodedata

import requests

from . import config

ARRANQUES_COMUNES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "nuevo", "nueva", "nuevos",
    "nuevas", "mas", "como", "que", "por", "para", "con", "en", "de", "del", "este",
    "esta", "estos", "estas", "asi", "cual", "cuales", "donde", "cuando", "gran",
    "grandes", "mejor", "mejores", "primer", "primera", "primeros", "primeras", "hay",
    "se", "su", "sus", "al", "a", "y", "sin", "tras", "ante", "hasta", "desde", "entre",
    "segun", "otro", "otra", "todo", "toda", "todos", "todas", "cinco", "tres", "dos",
    "cuatro", "seis", "siete", "ocho", "nueve", "diez", "aumenta", "crece", "llega",
    "llegan", "conoce", "descubre",
}


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def limpiar_html(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    s = re.sub(r"\[\s*(…|\.\.\.)\s*\]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def extraer_lead(contenido_html: str) -> str:
    """El lead es el primer párrafo de la nota en la web (la bajada en negrita)."""
    for parrafo in re.findall(r"<p\b[^>]*>(.*?)</p>", contenido_html or "", re.S | re.I):
        texto = limpiar_html(parrafo)
        if texto:
            return texto
    return ""


def ultimas_notas(cantidad: int = 10):
    r = requests.get(
        f"{config.SITIO}/wp-json/wp/v2/posts",
        params={"per_page": cantidad, "_embed": "wp:featuredmedia,wp:term"},
        headers={"User-Agent": "ReportEcuadorBot/1.0"}, timeout=60,
    )
    r.raise_for_status()
    notas = []
    for p in r.json():
        emb = p.get("_embedded", {})
        categorias = [t["name"] for grupo in emb.get("wp:term", []) for t in grupo
                      if t.get("taxonomy") == "category"]
        media = (emb.get("wp:featuredmedia") or [{}])[0]
        notas.append({
            "id": p["id"],
            "fecha": p["date"],
            "enlace": p["link"],
            "titulo": limpiar_html(p["title"]["rendered"]),
            "resumen": extraer_lead(p["content"]["rendered"]) or limpiar_html(p["excerpt"]["rendered"]),
            "categorias_wp": [html.unescape(c) for c in categorias],
            "foto": media.get("source_url"),
        })
    return notas


def elegir_categoria(categorias_wp):
    """Primera categoría que no sea de ubicación (Latam…). Devuelve (categoría, asumida)."""
    for c in categorias_wp:
        if not sin_tildes(c).lower().startswith(config.PREFIJO_IGNORADO):
            return c, False
    return config.CATEGORIA_POR_DEFECTO, True


def auto_resaltar(titulo: str) -> str:
    """Marca con *asteriscos* la parte que va en amarillo.

    - Si hay dos puntos al inicio del titular, se resalta hasta los dos puntos
      ("*Efecto FOMO:* el 78%…").
    - Si no, se resalta el nombre propio o sigla con que arranca
      ("*MPCEI* prevé…", "*WTE Miami 2026* puso…").
    """
    if "*" in titulo:
        return titulo
    pos = titulo.find(":")
    if 0 < pos <= len(titulo) * 0.7:
        return f"*{titulo[:pos + 1]}*{titulo[pos + 1:]}"

    palabras = titulo.split(" ")

    def es_entidad(w, primera):
        limpio = re.sub(r"[^\wÁÉÍÓÚÑáéíóúñ]", "", w)
        if not limpio:
            return False
        if any(ch.isdigit() for ch in limpio):
            return True
        if len(limpio) >= 2 and limpio.isupper():
            return True
        if limpio[0].isupper():
            return not (primera and sin_tildes(limpio).lower() in ARRANQUES_COMUNES)
        return False

    n = 0
    for i, w in enumerate(palabras):
        if es_entidad(w, i == 0) and n < 5:
            n += 1
        else:
            break
    if n == 1:
        unica = re.sub(r"[^\wÁÉÍÓÚÑáéíóúñ]", "", palabras[0])
        # Una sola palabra con mayúscula inicial suele ser el inicio de frase
        # ("Turismo del café…"), no un nombre: solo se resalta si es sigla o número.
        if not (unica.isupper() and len(unica) >= 2) and not any(ch.isdigit() for ch in unica):
            n = 0
    if n == 0:
        return titulo
    return "*" + " ".join(palabras[:n]) + "*" + ("" if n == len(palabras) else " " + " ".join(palabras[n:]))


def recortar_resumen(texto: str, maximo: int = 320) -> str:
    if len(texto) <= maximo:
        return texto
    frases = re.split(r"(?<=[.!?])\s+", texto)
    salida = ""
    for f in frases:
        if len(salida) + len(f) + 1 > maximo:
            break
        salida = (salida + " " + f).strip()
    return salida or texto[:maximo].rsplit(" ", 1)[0] + "…"


def hashtag(texto: str) -> str:
    palabras = re.findall(r"[A-Za-z0-9]+", sin_tildes(texto))
    return "#" + "".join(p[:1].upper() + p[1:] for p in palabras)


def armar_caption(titulo_plano: str, resumen: str, categoria: str) -> str:
    tags = [config.HASHTAGS_FIJOS[0], config.HASHTAGS_FIJOS[1], hashtag(categoria)] + config.HASHTAGS_FIJOS[2:]
    partes = [titulo_plano]
    if resumen:
        # El lead va completo; solo se recorta si superara el límite de Instagram (2.200 caracteres).
        partes.append(recortar_resumen(resumen, 1900))
    partes.append(f"Lee la nota completa en {config.DOMINIO_POST}")
    partes.append(" ".join(dict.fromkeys(tags)))
    return "\n\n".join(partes)
