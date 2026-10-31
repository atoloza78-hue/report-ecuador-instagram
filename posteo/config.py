"""Configuración de Report Ecuador. Cambia aquí los valores fijos del sistema."""

SITIO = "https://ecuador.reportnews.la"
DOMINIO_POST = "ecuador.reportnews.la"

# Cuenta de Instagram de Report Ecuador (el ID no es secreto; el token sí,
# y se guarda en GitHub como secreto IG_TOKEN).
IG_USER_ID = "17841441121997895"

# Categorías de WordPress que NO van en el post (son de ubicación en portada).
# Se ignora toda categoría cuyo nombre empiece por "Latam".
PREFIJO_IGNORADO = "latam"

# Categoría que se usa si la nota solo tiene categorías ignoradas.
CATEGORIA_POR_DEFECTO = "Actualidad"

CATEGORIAS = [
    "Actualidad", "Agencias y TTOO", "Asistencias", "Asociaciones", "Aviación",
    "Chile", "Destinos", "Eventos", "Hotelería y Gastronomía", "MICE",
    "Mensajes", "Navieras", "Parques", "Rentadoras", "Tecnología", "Tendencias",
]

HASHTAGS_FIJOS = ["#ReportEcuador", "#TurismoEcuador", "#Turismo", "#IndustriaTuristica"]

# En la primera ejecución (sin historial) solo se toman estas notas recientes,
# para no inundar la revisión con notas viejas.
MAX_PRIMERA_VEZ = 3

# Espacio entre publicaciones aprobadas (minutos) y horario en que se publica
# (hora de Ecuador). Lo que caiga fuera del horario pasa al día siguiente a la hora de inicio.
MINUTOS_ENTRE_POSTS = 60
HORARIO_PUBLICACION = (7, 21)
