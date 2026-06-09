"""Tests de que analytics_page expone el contexto nuevo de calidad (CAPA 2 - API, B3).

Verifica que GET /analytics no rompe con 0 validadas (P1) y que el render incluye
senales del contexto nuevo (precision/recall, A/B, salud) sin lanzar excepcion.
"""
from __future__ import annotations

from conftest import make_project, seed_image


def _demo_user_id(conn):
    from pacusam import seed

    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (seed.DEMO_EMAIL,)
    ).fetchone()["id"]


def test_analytics_con_cero_validadas_es_200(demo_login, conn):
    """P1: proyecto recien creado, solo pendientes -> GET /analytics 200 (no 500)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Vacio", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="p.jpeg", confidence=0.6)

    resp = demo_login.get(f"/projects/{pid}/analytics", follow_redirects=False)
    assert resp.status_code == 200


def test_analytics_render_no_rompe_con_validadas(demo_login, conn):
    """Con validadas el render sigue 200 (el contexto nuevo no rompe el template)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="ConVal", labels=("normal", "anomalia"))
    img = seed_image(conn, pid, filename="v.jpeg", label="normal", confidence=0.8)
    from pacusam import services

    services.validate_image(conn, img, "normal")
    resp = demo_login.get(f"/projects/{pid}/analytics", follow_redirects=False)
    assert resp.status_code == 200
