# Posteo automático de Report Ecuador en Instagram

Convierte las notas nuevas de [ecuador.reportnews.la](https://ecuador.reportnews.la) en posts de Instagram con la línea gráfica de Report Ecuador, los manda a revisión por correo y publica los que se aprueban.

## Cómo funciona

1. **Cada hora** (de 7 a. m. a 8 p. m., hora de Ecuador) revisa la web.
2. Por cada nota nueva genera el post: foto destacada, categoría, titular (la parte inicial va en amarillo) y `ecuador.reportnews.la`. Las categorías **Latam** (Grupo 6, Destacada, Abajo) se ignoran.
3. Abre **una revisión** con todos los posts nuevos. GitHub la envía por correo.
4. **Respondes el correo** con lo que quieres hacer y el sistema lo aplica.

## Órdenes para la revisión

Responde al correo (o comenta en la revisión) con una orden por línea:

| Escribe | Qué hace |
|---|---|
| `aprobado` | Publica todos los posts |
| `aprobado 1 3` | Publica solo esos |
| `descartar 2` | No publica ese post |
| `categoria 2: Destinos` | Cambia la categoría y regenera el post |
| `titular 2: *WTE Miami 2026* puso la IA en el centro` | Cambia el titular; lo que va entre `*` sale en amarillo |
| `caption 2: texto nuevo` | Reemplaza el caption |

Cuando todos los posts están publicados o descartados, la revisión se cierra sola.

## Configuración (una sola vez)

1. **Repositorio público**: Settings → General → Danger Zone → *Change visibility* → Public. Meta necesita descargar las imágenes desde una dirección pública. El token no queda expuesto: vive en los secretos.
2. **Token de Instagram**: Settings → Secrets and variables → Actions → *New repository secret*. Nombre `IG_TOKEN`, valor el token generado en Meta.
3. **Correo de las revisiones**: en tu perfil de GitHub, Settings → Emails, agrega `alejo@reportcolombia.com`; luego en Settings → Notifications → *Custom routing* asigna ese correo a este repositorio.
4. **Probar**: Actions → *Verificar conexión con Instagram* → *Run workflow*. Luego Actions → *Generar posts para revisión* → *Run workflow* con `ultimas = 3`.

## Archivos

- `posteo/` — el sistema (Python).
- `assets/` — fondo del bloque rojo con el mapamundi y logo de Report Ecuador.
- `posts/<id>/` — cada post generado (`post.jpg`) y sus datos (`datos.json`).
- `estado.json` — notas ya revisadas, para no repetirlas.
- `posteo/config.py` — dominio, categorías, hashtags y cuenta de Instagram.
