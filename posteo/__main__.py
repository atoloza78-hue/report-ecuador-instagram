"""Sistema de posteo de Report Ecuador en Instagram.

Uso:
  python -m posteo generar [--ultimas N]   Busca notas nuevas, genera los posts y abre la revisión.
  python -m posteo revisar                 Procesa una respuesta a la revisión (aprobar, descartar, cambios).
  python -m posteo verificar               Comprueba que el token de Instagram funciona.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config, github, instagram, notas, render

RAIZ = Path(__file__).resolve().parent.parent
ESTADO = RAIZ / "estado.json"
POSTS = RAIZ / "posts"
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
EN_GITHUB = bool(os.environ.get("GITHUB_ACTIONS"))


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
    t = datetime.now(ZoneInfo("America/Guayaquil"))
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

Puedes combinar cambios y aprobación en la misma respuesta."""


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

def cmd_generar(ultimas: int):
    estado = leer_json(ESTADO, None)
    primera_vez = estado is None
    estado = estado or {"procesadas": []}
    recientes = notas.ultimas_notas(10)

    if ultimas:
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
    partes = [f"Se generaron **{len(generados)} posts** de las últimas notas de {config.DOMINIO_POST}.", AYUDA]
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
        github.comentar(numero, "No encontré ninguna orden en tu respuesta.\n\n" + AYUDA)
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

    for n in dict.fromkeys(aprobar):
        d = posts[n]
        if d["estado"] == "publicado":
            resultados.append(f"ℹ️ El post {n} ya estaba publicado: {d.get('permalink', '')}")
            continue
        if n in descartar:
            continue
        try:
            enlace = instagram.publicar_imagen(github.url_publica(sha, ruta_post(d["id"])), d["caption"])
            d["estado"], d["permalink"] = "publicado", enlace
            resultados.append(f"✅ Post {n} publicado en Instagram. {enlace}")
        except instagram.ErrorInstagram as e:
            d["estado"] = "error"
            d["error"] = str(e)
            resultados.append(f"❌ El post {n} no se pudo publicar: {e}")
        guardar_datos(d)

    github.guardar_cambios(f"Revisión #{numero}: resultado")
    if resultados:
        github.comentar(numero, "\n".join(resultados))
    if all(d is None or d["estado"] in ("publicado", "descartado") for d in posts.values()):
        github.cerrar_issue(numero)


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
    sub.add_parser("revisar")
    sub.add_parser("verificar")
    a = p.parse_args()
    if a.cmd == "generar":
        cmd_generar(a.ultimas)
    elif a.cmd == "revisar":
        cmd_revisar()
    else:
        cmd_verificar()


if __name__ == "__main__":
    main()
