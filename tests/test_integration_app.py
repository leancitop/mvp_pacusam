"""Test de integracion de arranque de la app (CAPA 5).

D22: verificar el seed VIA API (login demo + GET / y assert de los 2 nombres),
no abriendo una segunda conexion. Mas /static sirve una imagen real del dataset.
"""
from __future__ import annotations

from pacusam import seed


def test_arranque_siembra_dos_proyectos_visibles_en_home(demo_login):
    """D22: la app fresca corre seed_if_empty en create_app; el usuario demo ve
    sus 2 proyectos en la home (leido por API, no por SQL)."""
    home = demo_login.get("/", follow_redirects=False)
    assert home.status_code == 200
    for spec in seed.DEMO_PROJECTS:
        assert spec["name"] in home.text


def test_static_sirve_una_imagen_del_dataset(demo_login, conn):
    """/static expone las imagenes reales: tomar el path de una imagen sembrada y
    pedirla -> 200 con content-type de imagen."""
    row = conn.execute(
        "SELECT path FROM images WHERE path LIKE '/static/datasets/%' LIMIT 1"
    ).fetchone()
    assert row is not None, "el seed deberia haber registrado imagenes con path /static/datasets/"
    resp = demo_login.get(row["path"], follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("image/")


def test_placeholder_servido(demo_login):
    """El onerror de las <img> apunta a /static/placeholder.png; debe existir (D09)."""
    resp = demo_login.get("/static/placeholder.png", follow_redirects=False)
    assert resp.status_code == 200
