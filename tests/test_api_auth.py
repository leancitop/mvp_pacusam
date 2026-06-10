"""Tests de endpoint de auth (CAPA 5).

Cubre registro/login/logout y el guard via require_user (D01/D21.a). Las
credenciales demo se importan de seed (D02). El client usa cookies de sesion
relajadas (PACUSAM_INSECURE_COOKIES) seteadas en conftest.
"""
from __future__ import annotations

from pacusam import seed


def test_registro_ok_redirige_a_home(client):
    """Registro valido -> 303 a / y, siguiendo el redirect, home 200 logueado."""
    resp = client.post(
        "/register",
        data={"email": "nuevo@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"
    # siguiendo el redirect ya hay sesion -> home 200 (no rebota a /login)
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
    assert "Proyectos" in home.text


def test_registro_email_duplicado_muestra_error(client):
    """Email ya registrado -> re-render del form con 400 y mensaje (no 500)."""
    client.post(
        "/register",
        data={"email": "dup@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    resp = client.post(
        "/register",
        data={"email": "dup@hospital.org", "password": "otra-pass"},
        follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "ya esta registrado" in resp.text


def test_login_invalido_muestra_error(client):
    """Credenciales malas -> 401 con mensaje de credenciales (no redirige)."""
    resp = client.post(
        "/login",
        data={"email": seed.DEMO_EMAIL, "password": "mal-password"},
        follow_redirects=False,
    )
    assert resp.status_code == 401
    assert "Credenciales" in resp.text


def test_login_demo_ok_redirige_a_home(client):
    resp = client.post(
        "/login",
        data={"email": seed.DEMO_EMAIL, "password": seed.DEMO_PASSWORD},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/"


def test_guard_sin_sesion_redirige_a_login(client):
    """Home sin sesion -> 303 a /login (require_user LANZA _RedirectException, D01)."""
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_logout_limpia_sesion_y_redirige(demo_login):
    """Logout -> 303 a /login; tras logout la home vuelve a rebotar a /login."""
    resp = demo_login.post("/logout", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    home = demo_login.get("/", follow_redirects=False)
    assert home.status_code == 303
    assert home.headers["location"] == "/login"


def test_sesion_a_usuario_borrado_redirige_a_login(demo_login, conn):
    """D21.a: si el user_id de la sesion apunta a un usuario inexistente, el guard
    limpia la sesion y redirige a /login (no 500)."""
    # borrar al usuario demo de la DB mientras la sesion sigue viva
    conn.execute("DELETE FROM users WHERE email = ?", (seed.DEMO_EMAIL,))
    conn.commit()
    resp = demo_login.get("/", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
