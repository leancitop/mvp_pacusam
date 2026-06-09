"""Tests de endpoint de proyectos (CAPA 5).

Cubre: home lista SOLO los proyectos del usuario, crear proyecto redirige a
/projects/{id} y aparece, empty-state (D21.d) e IDOR cross-user (D05/#14: 404).
"""
from __future__ import annotations

from conftest import make_project, make_user


def test_home_lista_solo_proyectos_del_usuario(client, conn):
    """Registro un usuario nuevo (home vacia) y le creo 1 proyecto; los proyectos
    demo (de otro owner) NO deben aparecer (filtro por owner)."""
    # usuario nuevo -> sesion propia, sin proyectos demo
    client.post(
        "/register",
        data={"email": "ana@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    me = conn.execute(
        "SELECT id FROM users WHERE email = ?", ("ana@hospital.org",)
    ).fetchone()["id"]
    make_project(conn, owner_id=me, name="Mi Dataset Privado")

    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
    assert "Mi Dataset Privado" in home.text
    # los proyectos demo pertenecen a otro owner -> no se listan
    assert "Radiografías de tórax" not in home.text
    assert "Células sanguíneas" not in home.text


def test_empty_state_sin_proyectos(client):
    """D21.d: usuario recien registrado sin proyectos -> home 200 con empty-state."""
    client.post(
        "/register",
        data={"email": "vacio@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    home = client.get("/", follow_redirects=False)
    assert home.status_code == 200
    assert "Todavía no tenés proyectos" in home.text


def test_crear_proyecto_redirige_a_detalle_y_aparece(demo_login):
    """POST /projects valido -> 303 a /projects/{id} (#6); el detalle y la home
    muestran el nombre nuevo."""
    resp = demo_login.post(
        "/projects",
        data={
            "name": "Tomografías 2026",
            "description": "Curado de TAC",
            "domain": "ct",
            "labels": "SANO,LESION",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("/projects/")

    detail = demo_login.get(location, follow_redirects=False)
    assert detail.status_code == 200
    assert "Tomografías 2026" in detail.text

    home = demo_login.get("/", follow_redirects=False)
    assert "Tomografías 2026" in home.text


def test_crear_proyecto_sin_nombre_flashea_error(demo_login):
    """name vacio -> redirect a / con flash (no 500), y la home muestra el mensaje."""
    resp = demo_login.post(
        "/projects",
        data={"name": "   ", "labels": "A,B"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "obligatorio" in resp.text


def test_idor_proyecto_ajeno_da_404(client, conn):
    """D05/#14: el usuario B pide GET /projects/{idA} de A -> 404 (no 403, no 200)."""
    # usuario A con un proyecto
    user_a = make_user(conn, email="a@hospital.org")
    pid_a = make_project(conn, owner_id=user_a, name="Dataset de A")

    # usuario B logueado
    client.post(
        "/register",
        data={"email": "b@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    resp = client.get(f"/projects/{pid_a}", follow_redirects=False)
    assert resp.status_code == 404
    # tampoco filtra el nombre del proyecto ajeno
    assert "Dataset de A" not in resp.text


def test_proyecto_inexistente_da_404(demo_login):
    resp = demo_login.get("/projects/999999", follow_redirects=False)
    assert resp.status_code == 404
