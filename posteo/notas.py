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


def nota_por_url(url: str):
    """Busca una nota por su enlace (o por palabras del titular)."""
    url = url.strip()
    if url.startswith("http"):
        slug = [p for p in url.split("?")[0].split("/") if p][-1]
        encontradas = ultimas_notas(1, slug=slug)
    else:
        encontradas = ultimas_notas(1, search=url)
    return encontradas[0] if encontradas else None


def ultimas_notas(cantidad: int = 10, **filtros):
    r = requests.get(
        f"{config.SITIO}/wp-json/wp/v2/posts",
        params={"per_page": cantidad, "_embed": "wp:featuredmedia,wp:term", **filtros},
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
    """Marca con *asteriscos* la parte que va en amarillo: el sujeto del titular.

    - Dos puntos al inicio: hasta los dos puntos ("*Efecto FOMO:* el 78%…").
    - Cita o pregunta inicial: la cita o la pregunta completa.
    - Si no: todo lo que va antes del verbo principal
      ("*Turismo del café en Loja* apunta…", "*Best Western* se transforma…").
    - Si no se reconoce el verbo: la sigla o nombre propio inicial, o la frase de arranque.
    """
    if "*" in titulo:
        return titulo
    t = titulo.strip()
    pos = t.find(":")
    if 0 < pos <= len(t) * 0.7:
        return f"*{t[:pos + 1]}*{t[pos + 1:]}"
    for abre, cierra in (("“", "”"), ('"', '"'), ("¿", "?"), ("¡", "!")):
        if t.startswith(abre) and cierra in t[1:]:
            fin = t.index(cierra, 1) + 1
            if fin < len(t):
                return f"*{t[:fin]}*{t[fin:]}"

    palabras = t.split(" ")
    n = sujeto(palabras)
    if n and len(" ".join(palabras[:n])) > len(t) * 0.7:
        n = 0
    if not n:
        n = entidad_inicial(palabras)
    if not n:
        n = frase_inicial(palabras)
    if n == 0 or n >= len(palabras):
        return titulo
    return "*" + " ".join(palabras[:n]) + "*" + " " + " ".join(palabras[n:])


VERBOS = set("""es son fue fueron sera seran esta estan estara estaran hay ha han habra puso pusieron hizo
hicieron dijo dijeron tuvo tuvieron dio dieron vio va van sigue siguen tiene tienen preve preven mira miran
llega llegan abre abren crece crecen cae caen gana ganan suma suman une unen amplia amplian guia rie
publica publican indica indican aplica aplican explica comunica modifica duplica triplica multiplica unifica
certifica identifica intensifica diversifica notifica califica clasifica verifica justifica fabrica ubica
dedica dedican replica replican aterriza aterrizan despega despegan""".split())
CORTE = {"se"}
NO_VERBO_FIN = ("ana", "anas", "ica", "icas", "ble", "bles", "ante", "antes", "ente", "entes", "ista",
                "istas", "aria", "arias", "ense", "enses", "ada", "adas", "ida", "idas", "osa", "osas",
                "iva", "ivas", "eña", "eñas", "ina", "inas", "ura")
VERBO_FIN = ("a", "an", "e", "en", "o", "ó", "io", "aron", "ieron", "ara", "era", "ira", "aran", "eran",
             "iran", "aba", "aban", "an")


def _norm(w):
    return sin_tildes(re.sub(r"[^\wÁÉÍÓÚÑÜáéíóúñü]", "", w)).lower()


def sujeto(palabras) -> int:
    """Cuántas palabras forman el sujeto (lo que va antes del verbo principal). 0 si no se halla."""
    for i in range(1, len(palabras)):
        w = palabras[i]
        n = _norm(w)
        if not n:
            continue
        if n == "que" and i >= 2:
            return i  # "La alianza que busca…": el sujeto termina antes de la oración de relativo
        if n in CONECTORES and n not in CORTE:
            continue
        if n in CORTE or n in VERBOS:
            return i if i <= len(palabras) - 1 else 0
        previa = _norm(palabras[i - 1])
        limpia = re.sub(r"[^\wÁÉÍÓÚÑÜáéíóúñü]", "", w)
        if previa in CONECTORES or not limpia or limpia[0].isupper() or any(c.isdigit() for c in limpia):
            continue
        sin = sin_tildes(limpia).lower()
        termina_o_tilde = limpia.lower().endswith(("ó", "ió", "é"))
        if termina_o_tilde or (sin.endswith(("a", "an", "e", "en")) and not sin.endswith(NO_VERBO_FIN)) \
                or sin.endswith(("aran", "eran", "iran", "ara", "era", "ira", "aron", "ieron")):
            if i == 1 and _norm(palabras[0]) in CONECTORES:
                continue
            return i
    return 0


def entidad_inicial(palabras) -> int:
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
        if not (unica.isupper() and len(unica) >= 2) and not any(ch.isdigit() for ch in unica):
            n = 0
    return n


CONECTORES = {"de", "del", "la", "el", "los", "las", "en", "y", "e", "o", "u", "a", "al", "con",
              "por", "para", "que", "se", "su", "sus", "un", "una", "lo", "como", "sin", "sobre", "entre"}


def frase_inicial(palabras) -> int:
    """Todo post lleva una parte en amarillo. Si no hay nombre propio ni dos puntos,
    se resalta la frase con que arranca el titular (cerca del 40% del largo),
    sin terminar en una palabra de enlace ("*Turismo del café en Loja* apunta…")."""
    total = len(" ".join(palabras))
    limite = max(14, total * 0.4)
    n, largo = 0, 0
    for i, w in enumerate(palabras):
        nuevo = largo + (1 if i else 0) + len(w)
        if i >= 1 and nuevo > limite:
            break
        largo, n = nuevo, i + 1
    while n > 1 and sin_tildes(re.sub(r"[^\w]", "", palabras[n - 1])).lower() in CONECTORES:
        n -= 1
    return n


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
    # El titular ya va en la imagen: el caption arranca con el lead.
    partes = [] if resumen else [titulo_plano]
    if resumen:
        # El lead va completo; solo se recorta si superara el límite de Instagram (2.200 caracteres).
        partes.append(recortar_resumen(resumen, 1900))
    partes.append(f"Lee la nota completa en {config.DOMINIO_POST}")
    partes.append(" ".join(dict.fromkeys(tags)))
    return "\n\n".join(partes)
