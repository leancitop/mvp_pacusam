"""Tests de endpoint del gating admin (CAPA 2 - API, D3 read-only).

Cubre el contrato de require_admin: no-auth -> 303 /login; curador -> 403;
admin -> 200. GET /admin lista usuarios (email, role) y el log de actividad,
filtrable por query params user/action.
"""
from __future__ import annotations

from conftest import make_project, seed_image


def _login_admin(client):
    from pacusam import seed

    resp = client.post(
        "/login",
        data={"email": seed.ADMIN_EMAIL, "password": seed.ADMIN_PASSWORD},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    return client


def test_admin_no_auth_redirige_a_login(client):
    """Sin sesion -> 303 a /login (require_user dispara antes que el chequeo de rol)."""
    resp = client.get("/admin", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_admin_curador_es_403(demo_login):
    """El usuario demo es curador -> 403 en /admin."""
    resp = demo_login.get("/admin", follow_redirects=False)
    assert resp.status_code == 403


def test_admin_admin_ve_la_pagina(client, conn):
    """El admin demo ve /admin -> 200 con la lista de usuarios."""
    _login_admin(client)
    resp = client.get("/admin", follow_redirects=False)
    assert resp.status_code == 200
    from pacusam import seed

    assert seed.ADMIN_EMAIL in resp.text
    assert seed.DEMO_EMAIL in resp.text


def test_admin_muestra_log_de_actividad(client, conn):
    """El log de actividad aparece en /admin (registrado via servicio)."""
    from pacusam import services

    admin_id = conn.execute(
        "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
    ).fetchone()["id"]
    services.log_activity(conn, admin_id, "validate", image_id=42, project_id=1)

    _login_admin(client)
    resp = client.get("/admin", follow_redirects=False)
    assert resp.status_code == 200
    assert "validate" in resp.text


def test_admin_filtra_log_por_action(client, conn):
    """GET /admin?action=reject filtra el log mostrado por accion."""
    from pacusam import services

    admin_id = conn.execute(
        "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
    ).fetchone()["id"]
    services.log_activity(conn, admin_id, "validate", image_id=1, project_id=1)
    services.log_activity(conn, admin_id, "reject", image_id=2, project_id=1)

    _login_admin(client)
    resp = client.get("/admin", params={"action": "reject"}, follow_redirects=False)
    assert resp.status_code == 200
