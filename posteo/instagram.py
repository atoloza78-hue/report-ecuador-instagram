"""Publicación en Instagram con la API oficial de Meta."""
import os
import time

import requests

from . import config


class ErrorInstagram(Exception):
    pass


def _token() -> str:
    t = os.environ.get("IG_TOKEN", "").strip()
    if not t:
        raise ErrorInstagram("Falta el secreto IG_TOKEN en GitHub (Settings → Secrets and variables → Actions).")
    return t


def _base() -> str:
    version = os.environ.get("IG_API_VERSION", "v23.0")
    # Tokens de "inicio de sesión de Instagram" (IG…) van por graph.instagram.com;
    # tokens de Facebook/usuario del sistema (EAA…) van por graph.facebook.com.
    host = "graph.facebook.com" if _token().startswith("EAA") else "graph.instagram.com"
    return f"https://{host}/{version}"


def _llamar(metodo: str, ruta: str, **params):
    params["access_token"] = _token()
    r = requests.request(metodo, f"{_base()}/{ruta}", params=params if metodo == "GET" else None,
                         data=params if metodo != "GET" else None, timeout=60)
    datos = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in datos:
        err = datos.get("error", {})
        raise ErrorInstagram(err.get("error_user_msg") or err.get("message") or r.text[:300])
    return datos


def verificar() -> dict:
    cuenta = _llamar("GET", config.IG_USER_ID, fields="username")
    limite = _llamar("GET", f"{config.IG_USER_ID}/content_publishing_limit", fields="quota_usage,config")
    return {"cuenta": cuenta.get("username"), "limite": limite}


def publicar_imagen(url_imagen: str, caption: str) -> str:
    """Publica una imagen y devuelve el enlace al post en Instagram."""
    contenedor = _llamar("POST", f"{config.IG_USER_ID}/media", image_url=url_imagen, caption=caption)["id"]
    for _ in range(30):
        estado = _llamar("GET", contenedor, fields="status_code").get("status_code")
        if estado == "FINISHED":
            break
        if estado in ("ERROR", "EXPIRED"):
            raise ErrorInstagram(f"Meta no pudo procesar la imagen (estado {estado}).")
        time.sleep(3)
    media_id = _llamar("POST", f"{config.IG_USER_ID}/media_publish", creation_id=contenedor)["id"]
    try:
        return _llamar("GET", media_id, fields="permalink").get("permalink", "")
    except ErrorInstagram:
        return ""
