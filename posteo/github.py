"""Guardar cambios en el repositorio y manejar la revisión (issue) de GitHub."""
import os
import subprocess

import requests

API = "https://api.github.com"


def repo() -> str:
    return os.environ["GITHUB_REPOSITORY"]


def _h():
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
    }


def _git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout.strip()


def guardar_cambios(mensaje: str) -> str:
    """Hace commit y push de todo lo cambiado. Devuelve el SHA del commit."""
    _git("config", "user.name", "github-actions[bot]")
    _git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    _git("add", "-A")
    if subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0:
        _git("commit", "-m", mensaje)
    for _ in range(3):
        try:
            _git("pull", "--rebase", "--quiet")
            _git("push", "--quiet")
            break
        except subprocess.CalledProcessError:
            continue
    return _git("rev-parse", "HEAD")


def sha_actual() -> str:
    return _git("rev-parse", "HEAD")


def url_publica(sha: str, ruta: str) -> str:
    """URL pública y fija (no cambia aunque el archivo se edite después)."""
    return f"https://raw.githubusercontent.com/{repo()}/{sha}/{ruta}"


def asegurar_etiqueta(nombre="revision", color="c0392b"):
    requests.post(f"{API}/repos/{repo()}/labels", headers=_h(),
                  json={"name": nombre, "color": color}, timeout=30)


def crear_issue(titulo: str, cuerpo: str) -> int:
    asegurar_etiqueta()
    r = requests.post(f"{API}/repos/{repo()}/issues", headers=_h(),
                      json={"title": titulo, "body": cuerpo, "labels": ["revision"]}, timeout=30)
    r.raise_for_status()
    return r.json()["number"]


def comentar(numero: int, cuerpo: str):
    r = requests.post(f"{API}/repos/{repo()}/issues/{numero}/comments", headers=_h(),
                      json={"body": cuerpo}, timeout=30)
    r.raise_for_status()


def cerrar_issue(numero: int):
    requests.patch(f"{API}/repos/{repo()}/issues/{numero}", headers=_h(),
                   json={"state": "closed"}, timeout=30)
