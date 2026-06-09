"""Tests de la capa de animaciones / loaders / wow (CAPA 3 — UI).

Verifican que las piezas visuales nuevas esten presentes en el HTML renderizado
sin romper el contrato existente. No abren navegador: chequean el markup que
sirve la app (confetti vendorizado y cargado, spinner de carga, transicion de
swap, count-up en analitica) y que no haya em-dashes en el texto de UI.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from conftest import demo_project_ids


def test_base_carga_confetti_vendorizado(client: TestClient):
    """El vendor de confetti esta pineado en /static/vendor y se sirve 200."""
    r = client.get("/static/vendor/confetti.min.js")
    assert r.status_code == 200
    assert "confetti" in r.text


def test_base_referencia_confetti_y_transicion_de_swap(demo_login, conn):
    """base.html carga confetti local (no CDN) y define la transicion suave del
    auto-avance (#image-card con htmx-swapping/htmx-settling)."""
    r = demo_login.get("/login") if False else demo_login.get("/")
    # base.html se hereda en home; basta con verla una vez.
    html = r.text
    assert "/static/vendor/confetti.min.js" in html
    assert "cdn.jsdelivr.net" not in html  # vendorizado, no CDN
    # Transicion del swap del card: clases de fase HTMX presentes en una <style>.
    assert "htmx-swapping" in html
    assert "htmx-settling" in html


def test_curate_muestra_spinner_no_texto_pelado(demo_login, conn):
    """curate.html reemplaza el texto pelado por un spinner CSS + texto."""
    pid = demo_project_ids(conn)[0]
    html = demo_login.get(f"/projects/{pid}/curate").text
    # El spinner usa una clase dedicada y sigue acompañando el texto de carga.
    assert "pacusam-spinner" in html
    assert "Cargando la cola" in html


def test_micro_celebracion_dispara_confetti(demo_login, conn):
    """El else branch (cola vacia) trae el hook de confetti para la celebracion."""
    from conftest import make_project, seed_image

    uid = conn.execute(
        "SELECT id FROM users ORDER BY id LIMIT 1"
    ).fetchone()["id"]
    pid = make_project(conn, owner_id=uid, name="Solo una", labels=("normal", "anomalia"))
    img_id = seed_image(conn, pid, filename="x.jpeg", confidence=0.5)
    resp = demo_login.post(
        f"/images/{img_id}/validate", data={"label": "normal"}, follow_redirects=False
    )
    assert resp.status_code == 200
    assert "Dataset curado" in resp.text
    # Hook que dispara confetti al aparecer la celebracion.
    assert "pacusam-celebrate" in resp.text


def test_analytics_tiene_count_up(demo_login, conn):
    """analytics.html anima los numeros grandes con un helper Alpine (count-up)."""
    pid = demo_project_ids(conn)[0]
    html = demo_login.get(f"/projects/{pid}/analytics").text
    assert "countUp" in html  # helper Alpine x-data
    # El total animado se expone al helper como dato inicial.
    assert "x-data=\"countUp" in html or "x-data='countUp" in html


def test_paginas_wow_sin_em_dash(demo_login, conn):
    """Ni curate ni analytics renderizan em-dashes en el texto de UI."""
    pid = demo_project_ids(conn)[0]
    for path in (f"/projects/{pid}/curate", f"/projects/{pid}/analytics"):
        html = demo_login.get(path).text
        assert "—" not in html, f"em-dash en {path}"
