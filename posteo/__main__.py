"""Sistema de posteo de Report Ecuador en Instagram.

Uso:
  python -m posteo generar [--ultimas N]   Busca notas nuevas, genera los posts y abre la revisión.
  python -m posteo revisar                 Procesa una respuesta a la revisión (aprobar, descartar, cambios).
  python -m posteo publicar                Publica los posts programados cuya hora ya llegó.
  python -m posteo verificar               Comprueba que el token de Instagram funciona.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, github, instagram, notas, render

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "estado.json"
POSTS = RAIZ / "posts"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
EN_GITHUB = bool(os.environ.get("GITHUB_ACTIONS"))
TZ = ZoneInfo("America/Guayaquil")


# ---------- datos ----------

def leer_json(ruta: Path, defecto):
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else defecto


def escribir_json(ruta: Path, datos):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ruta_post(pid) -> str:
    return f"posts/{pid}/post.jpg"


def datos_post(pid) -> dict:
    return leer_json(POSTS / str(pid) / "datos.json", None)


def guardar_datos(d: dict):
    escribir_json(POSTS / str(d["id"]) / "datos.json", d)


def dibujar(d: dict):
    foto = render.foto_desde_url(d["foto"])
    img = render.generar_post(foto, d["categoria"], d["titulo"])
    render.guardar_jpg(img, RAIZ / ruta_post(d["id"]))


def ahora_texto() -> str:
    t = datetime.now(TZ)
    return f"{t.day} {MESES[t.month - 1]} {t.year}, {t:%H:%M}"


# ---------- revisión ----------

AYUDA = """**Para revisar, responde a este correo** (o comenta aquí) con una orden por línea:

| Escribe | Qué hace |
|---|---|
| `aprobado` | Publica todos los posts |
| `aprobado 1 3` | Publica solo esos |
| `descartar 2` | No publica ese post |
| `categoria 2: Destinos` | Cambia la categoría y regenera el post |
| `titular 2: *WTE Miami 2026* puso la IA en el centro` | Cambia el titular (lo que va entre `*` sale en amarillo) |
| `caption 2: texto nuevo` | Reemplaza el caption |

Puedes combinar cambios y aprobación en la misma respuesta. Los posts aprobados se publican **con una hora de diferencia**, el primero de inmediato."""


def bloque_post(n: int, d: dict, sha: str) -> str:
    url = github.url_publica(sha, ruta_post(d["id"]))
    caption = "\n".join("> " + (l or " ") for l in d["caption"].split("\n"))
    aviso = ""
    if d.get("categoria_asumida"):
        aviso = (f"\n\n⚠️ La nota solo tenía categorías Latam en la web; puse **{d['categoria']}**. "
                 f"Cámbiala con `categoria {n}: Nombre` si no es correcta.")
    return (f"### {n} · {d['categoria'].upper()}\n**{d['titulo_plano']}**\n\n"
            f'<img src="{url}" width="420" alt="Post {n}">\n\n'
            f"**Caption**\n{caption}\n\n[Ver la nota en la web]({d['enlace']}){aviso}")


# ---------- generar ----------

def cmd_generar(ultimas: int, nota: str = ""):
    estado = leer_json(ESTADO, None)
    primera_vez = estado is None
    estado = estado or {"procesadas": []}
    recientes = notas.ultimas_notas(10)

    if nota:
        encontrada = notas.nota_por_url(nota)
        if not encontrada:
            print(f"No encontré la nota: {nota}")
            sys.exit(1)
        seleccion = [encontrada]
    elif ultimas:
        seleccion = recientes[:ultimas]
    else:
        seleccion = [n for n in recientes if n["id"] not in estado["procesadas"]]
        if primera_vez:
            seleccion = seleccion[:config.MAX_PRIMERA_VEZ]

    generados, sin_foto = [], []
    for nota in seleccion:
        if not nota["foto"]:
            sin_foto.append(nota)
            continue
        categoria, asumida = notas.elegir_categoria(nota["categorias_wp"])
        d = {
            "id": nota["id"], "enlace": nota["enlace"], "fecha": nota["fecha"],
            "titulo": notas.auto_resaltar(nota["titulo"]), "titulo_plano": nota["titulo"],
            "categoria": categoria, "categoria_asumida": asumida,
            "categorias_wp": nota["categorias_wp"], "resumen": nota["resumen"],
            "caption": notas.armar_caption(nota["titulo"], nota["resumen"], categoria),
            "foto": nota["foto"], "estado": "pendiente",
        }
        dibujar(d)
        guardar_datos(d)
        generados.append(d)
        print(f"Post generado: [{categoria}] {nota['titulo']}")

    vistos = recientes if primera_vez else seleccion
    for n in vistos:
        if n["id"] not in estado["procesadas"]:
            estado["procesadas"].append(n["id"])
    estado["procesadas"] = estado["procesadas"][-500:]
    escribir_json(ESTADO, estado)

    if not EN_GITHUB:
        print("Prueba local: no se sube nada ni se abre revisión.")
        return
    if not generados and not sin_foto:
        github.guardar_cambios("Revisión de notas: sin notas nuevas")
        print("No hay notas nuevas.")
        return

    sha = github.guardar_cambios(f"Posts para revisión ({len(generados)})")
    dueno = os.environ.get("GITHUB_REPOSITORY_OWNER", "")
    aviso = f"@{dueno} " if dueno else ""
    partes = [f"{aviso}Se generaron **{len(generados)} posts** de las últimas notas de {config.DOMINIO_POST}.", AYUDA]
    for i, d in enumerate(generados, 1):
        partes.append(bloque_post(i, d, sha))
    if sin_foto:
        partes.append("**Notas sin foto destacada (no se generó post):**\n" +
                      "\n".join(f"- [{n['titulo']}]({n['enlace']})" for n in sin_foto))
    partes.append(f"<!-- lote: {','.join(str(d['id']) for d in generados)} -->")
    titulo = f"Revisión Report Ecuador · {ahora_texto()} · {len(generados)} post{'s' if len(generados) != 1 else ''}"
    numero = github.crear_issue(titulo, "\n\n---\n\n".join(partes))
    for d in generados:
        d["issue"] = numero
        guardar_datos(d)
    github.guardar_cambios(f"Revisión #{numero} abierta")
    print(f"Revisión abierta: #{numero}")


# ---------- revisar ----------

RE_ORDEN = re.compile(
    r"^\s*(?P<orden>aprobad[oa]s?|aprobar|aprueb[oa]|publicar|descartar|descarta|rechazar|"
    r"categoria|titular|titulo|caption)\b(?P<resto>.*)$", re.IGNORECASE)


def limpiar_respuesta(texto: str) -> list:
    """Quita la parte citada de una respuesta por correo."""
    lineas = []
    for l in texto.replace("\r", "").split("\n"):
        if re.match(r"^\s*(El|On)\s.+(escribi[oó]|wrote)\s*:?\s*$", l) or l.strip() in ("--", "-- "):
            break
        if l.lstrip().startswith(">"):
            continue
        lineas.append(l)
    return lineas


def leer_ordenes(texto: str):
    ordenes = []
    for l in limpiar_respuesta(texto):
        if notas.sin_tildes(l).strip(" .!").lower() in ("ok", "si", "dale", "listo"):
            ordenes.append(["aprobado", ""])
            continue
        m = RE_ORDEN.match(notas.sin_tildes(l))
        if m:
            original_resto = l[m.start("resto"):]
            ordenes.append([m.group("orden").lower(), original_resto])
        elif ordenes and ordenes[-1][0] == "caption":
            ordenes[-1][1] += "\n" + l
    return ordenes


def numeros(texto: str):
    return [int(x) for x in re.findall(r"\d+", texto)]


def buscar_categoria(nombre: str):
    clave = notas.sin_tildes(nombre).lower().strip(" .:")
    for c in config.CATEGORIAS:
        if notas.sin_tildes(c).lower() == clave:
            return c
    for c in config.CATEGORIAS:
        if notas.sin_tildes(c).lower().startswith(clave) and clave:
            return c
    return None


def cmd_revisar():
    evento = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = evento["issue"]
    numero = issue["number"]
    m = re.search(r"<!-- lote: ([\d,]+) -->", issue.get("body") or "")
    if not m:
        print("Esta conversación no es una revisión de posts.")
        return
    ids = [int(x) for x in m.group(1).split(",") if x]
    posts = {i: datos_post(pid) for i, pid in enumerate(ids, 1)}

    ordenes = leer_ordenes(evento["comment"]["body"])
    if not ordenes:
        print("El comentario no trae órdenes; no se hace nada.")
        return

    def valido(n):
        return n in posts and posts[n] is not None

    resultados, cambiados, aprobar, descartar = [], [], [], []
    for orden, resto in ordenes:
        if orden.startswith(("aprob", "aprueb", "publicar")):
            ns = numeros(resto) or list(posts)
            aprobar += [n for n in ns if valido(n)]
            resultados += [f"⚠️ No existe el post {n}." for n in ns if not valido(n)]
        elif orden.startswith(("descart", "rechaz")):
            for n in numeros(resto):
                if valido(n):
                    descartar.append(n)
                else:
                    resultados.append(f"⚠️ No existe el post {n}.")
        else:
            mm = re.match(r"\s*(\d+)\s*[:=\-]?\s*(.*)", resto, re.S)
            if not mm or not valido(int(mm.group(1))) or not mm.group(2).strip():
                resultados.append(f"⚠️ No entendí: `{orden}{resto.splitlines()[0] if resto else ''}`. "
                                  f"Escribe el número del post y luego el texto, por ejemplo `{orden} 2: …`.")
                continue
            n, valor = int(mm.group(1)), mm.group(2).strip()
            d = posts[n]
            if orden == "categoria":
                cat = buscar_categoria(valor)
                if not cat:
                    resultados.append(f"⚠️ La categoría “{valor}” no existe. Opciones: " + ", ".join(config.CATEGORIAS))
                    continue
                d["categoria"], d["categoria_asumida"] = cat, False
                d["caption"] = notas.armar_caption(d["titulo_plano"], d["resumen"], cat)
            elif orden in ("titular", "titulo"):
                d["titulo"] = valor.replace("\n", " ")
                d["titulo_plano"] = d["titulo"].replace("*", "")
                d["caption"] = notas.armar_caption(d["titulo_plano"], d["resumen"], d["categoria"])
            elif orden == "caption":
                d["caption"] = valor
                d["caption_manual"] = True
            if orden != "caption":
                dibujar(d)
            guardar_datos(d)
            if n not in cambiados:
                cambiados.append(n)

    sha = github.guardar_cambios(f"Revisión #{numero}: cambios") if cambiados else github.guardar_cambios("Revisión")
    if cambiados:
        github.comentar(numero, "Así quedaron los posts que cambiaste:\n\n---\n\n" +
                        "\n\n---\n\n".join(bloque_post(n, posts[n], sha) for n in cambiados))

    for n in dict.fromkeys(descartar):
        posts[n]["estado"] = "descartado"
        guardar_datos(posts[n])
        resultados.append(f"🗑️ Post {n} descartado.")

    ultimo = ultimo_turno()
    nuevos = []
    for n in dict.fromkeys(aprobar):
        d = posts[n]
        if n in descartar:
            continue
        if d["estado"] == "publicado":
            resultados.append(f"ℹ️ El post {n} ya estaba publicado: {d.get('permalink', '')}")
            continue
        if d["estado"] == "programado":
            resultados.append(f"ℹ️ El post {n} ya estaba programado para {hora_texto(d['programado_para'])}.")
            continue
        turno = siguiente_turno(ultimo)
        ultimo = turno
        nuevos.append(n)
        d["estado"], d["programado_para"], d["n"], d["issue"] = "programado", turno.isoformat(), n, numero
        d.pop("error", None)
        guardar_datos(d)

    resultados += publicar_vencidos(sha)
    posts = {i: datos_post(pid) for i, pid in enumerate(ids, 1)}
    for n in nuevos:
        if posts[n]["estado"] == "programado" and n not in descartar:
            resultados.append(f"🕐 Post {n} programado para {hora_texto(posts[n]['programado_para'])}.")

    github.guardar_cambios(f"Revisión #{numero}: resultado")
    if resultados:
        github.comentar(numero, "\n".join(resultados))
    cerrar_si_termino(numero)


# ---------- publicación espaciada ----------

def todos_los_posts():
    return [leer_json(f, None) for f in sorted(POSTS.glob("*/datos.json"))]


def ultimo_turno():
    """Hora de la última publicación hecha o programada (para mantener el espacio entre posts)."""
    horas = []
    for d in todos_los_posts():
        if d and d.get("estado") in ("publicado", "programado"):
            for k in ("programado_para", "publicado_en"):
                if d.get(k):
                    horas.append(datetime.fromisoformat(d[k]))
    return max(horas) if horas else None


def siguiente_turno(ultimo):
    ahora = datetime.now(TZ)
    t = ahora if ultimo is None else max(ahora, ultimo + timedelta(minutes=config.MINUTOS_ENTRE_POSTS))
    inicio, fin = config.HORARIO_PUBLICACION
    if t.hour < inicio:
        t = t.replace(hour=inicio, minute=0, second=0, microsecond=0)
    elif t.hour >= fin:
        t = (t + timedelta(days=1)).replace(hour=inicio, minute=0, second=0, microsecond=0)
    return t


def hora_texto(iso: str) -> str:
    t = datetime.fromisoformat(iso).astimezone(TZ)
    hoy = datetime.now(TZ).date()
    dia = "hoy" if t.date() == hoy else ("mañana" if t.date() == hoy + timedelta(days=1) else f"el {t.day} {MESES[t.month - 1]}")
    return f"{dia} a las {t:%H:%M} (hora de Ecuador)"


def publicar_vencidos(sha: str):
    """Publica los posts programados cuya hora ya llegó. Devuelve líneas de resultado."""
    ahora = datetime.now(TZ) + timedelta(minutes=2)
    resultados = []
    vencidos = [d for d in todos_los_posts()
                if d and d.get("estado") == "programado" and datetime.fromisoformat(d["programado_para"]) <= ahora]
    for d in sorted(vencidos, key=lambda x: x["programado_para"]):
        n = d.get("n", "")
        try:
            enlace = instagram.publicar_imagen(github.url_publica(sha, ruta_post(d["id"])), d["caption"])
            d["estado"], d["permalink"] = "publicado", enlace
            d["publicado_en"] = datetime.now(TZ).isoformat()
            linea = f"✅ Post {n} publicado en Instagram. {enlace}"
        except instagram.ErrorInstagram as e:
            d["estado"], d["error"] = "error", str(e)
            linea = f"❌ El post {n} no se pudo publicar: {e}. Responde `aprobado {n}` para reintentar."
        guardar_datos(d)
        resultados.append(linea)
        d["_linea"] = linea
    publicar_vencidos.ultimos = vencidos
    return resultados


def cerrar_si_termino(numero: int):
    del_lote = [d for d in todos_los_posts() if d and d.get("issue") == numero]
    if del_lote and all(d["estado"] in ("publicado", "descartado") for d in del_lote):
        github.cerrar_issue(numero)


def cmd_publicar():
    """Lo corre GitHub cada 15 minutos: publica lo programado que ya tocó."""
    sha = github.sha_actual()
    publicar_vencidos(sha)
    vencidos = getattr(publicar_vencidos, "ultimos", [])
    if not vencidos:
        print("Nada por publicar ahora.")
        return
    github.guardar_cambios("Publicación programada")
    for numero in dict.fromkeys(d.get("issue") for d in vencidos if d.get("issue")):
        github.comentar(numero, "\n".join(d["_linea"] for d in vencidos if d.get("issue") == numero))
        cerrar_si_termino(numero)


# ---------- verificar ----------

def cmd_verificar():
    try:
        info = instagram.verificar()
    except instagram.ErrorInstagram as e:
        print(f"El token NO funciona: {e}")
        sys.exit(1)
    print(f"Token correcto. Cuenta: @{info['cuenta']}")
    print(f"Límite de publicaciones: {json.dumps(info['limite'], ensure_ascii=False)}")


def main():
    p = argparse.ArgumentParser(prog="posteo")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generar")
    g.add_argument("--ultimas", type=int, default=0, help="Regenerar las N notas más recientes (prueba)")
    g.add_argument("--nota", default="", help="Enlace (o palabras del titular) de una nota puntual")
    sub.add_parser("revisar")
    sub.add_parser("verificar")
    sub.add_parser("publicar")
    a = p.parse_args()
    if a.cmd == "generar":
        cmd_generar(a.ultimas, a.nota)
    elif a.cmd == "revisar":
        cmd_revisar()
    elif a.cmd == "publicar":
        cmd_publicar()
    else:
        cmd_verificar()


if __name__ == "__main__":
    main()
