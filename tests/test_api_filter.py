"""Tests de endpoint del filtro por etiqueta (US-17, CAPA 2 — API).

Login demo (D02). Cubre: GET /queue?label=X filtra el filmstrip por suggested_label
(queue_next sigue dando la proxima sin filtrar) y los chips de filtro (label_counts)
aparecen en el render de curate.
"""
from __future__ import annotations

from conftest import demo_project_ids, make_project, seed_image


def _demo_user_id(conn):
    from pacusam import seed

    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (seed.DEMO_EMAIL,)
    ).fetchone()["id"]


def test_queue_con_label_filtra_filmstrip(demo_login, conn):
    """GET /queue?label=anomalia: el filmstrip solo trae imagenes de esa clase."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Filtro cola", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="n1.jpeg", label="normal", confidence=0.55)
    seed_image(conn, pid, filename="n2.jpeg", label="normal", confidence=0.70)
    a1 = seed_image(conn, pid, filename="a1.jpeg", label="anomalia", confidence=0.52)

    resp = demo_login.get(
        f"/projects/{pid}/queue", params={"label": "anomalia"}, follow_redirects=False
    )
    assert resp.status_code == 200
    # El filmstrip filtrado solo debe contener la miniatura de la clase pedida.
    assert "a1.jpeg" in resp.text
    assert "n1.jpeg" not in resp.text
    assert "n2.jpeg" not in resp.text


def test_queue_sin_label_trae_todas(demo_login, conn):
    """GET /queue sin label: el filmstrip trae todas las imagenes (regresion)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Filtro todas", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="todo_n.jpeg", label="normal", confidence=0.55)
    seed_image(conn, pid, filename="todo_a.jpeg", label="anomalia", confidence=0.52)

    resp = demo_login.get(f"/projects/{pid}/queue", follow_redirects=False)
    assert resp.status_code == 200
    assert "todo_n.jpeg" in resp.text
    assert "todo_a.jpeg" in resp.text


def test_curate_renderiza_chips_de_filtro(demo_login, conn):
    """La pagina de curado expone los chips de filtro con el nombre de cada clase."""
    pid = demo_project_ids(conn)[0]  # "Radiografias de torax": NORMAL / PNEUMONIA
    resp = demo_login.get(f"/projects/{pid}/curate", follow_redirects=False)
    assert resp.status_code == 200
    assert "NORMAL" in resp.text
    assert "PNEUMONIA" in resp.text


def test_queue_con_label_proyecto_ajeno_es_404(client, conn):
    """IDOR: filtrar la cola de un proyecto ajeno -> 404."""
    from conftest import make_user

    user_a = make_user(conn, email="fa@hospital.org")
    pid_a = make_project(conn, owner_id=user_a, name="A-filtro", labels=("normal", "anomalia"))
    seed_image(conn, pid_a, filename="aa.jpeg")

    client.post(
        "/register",
        data={"email": "fb@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    resp = client.get(
        f"/projects/{pid_a}/queue", params={"label": "normal"}, follow_redirects=False
    )
    assert resp.status_code == 404
