"""Tests de endpoint del historial de ciclos AL (US-16, CAPA 2 — API).

Login demo (D02). Cubre: GET /analytics expone cycles (list_cycles) en el contexto
y el POST /retrain registra un ciclo nuevo que aparece luego en analytics.
"""
from __future__ import annotations

from conftest import demo_project_ids, make_project, seed_image


def _demo_user_id(conn):
    from pacusam import seed

    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (seed.DEMO_EMAIL,)
    ).fetchone()["id"]


def test_analytics_200_y_render(demo_login, conn):
    """GET /analytics del proyecto demo -> 200."""
    pid = demo_project_ids(conn)[0]
    resp = demo_login.get(f"/projects/{pid}/analytics", follow_redirects=False)
    assert resp.status_code == 200


def test_analytics_muestra_historial_de_ciclos_sembrados(demo_login, conn):
    """El seed deja 2 ciclos AL por proyecto; analytics los renderiza en el historial."""
    pid = demo_project_ids(conn)[0]
    cycles = __import__("pacusam.services", fromlist=["services"]).list_cycles(conn, pid)
    assert len(cycles) == 2  # contrato del seed
    resp = demo_login.get(f"/projects/{pid}/analytics", follow_redirects=False)
    assert resp.status_code == 200
    # El porcentaje de mejora del ultimo ciclo aparece en el render.
    assert f"{cycles[-1]['improvement_pct']}" in resp.text


def test_retrain_registra_ciclo_visible_en_analytics(demo_login, conn):
    """POST /retrain con pendientes registra un ciclo; analytics suma uno mas."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Ciclo nuevo", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="p1.jpeg", confidence=0.50)
    seed_image(conn, pid, filename="p2.jpeg", confidence=0.55)

    from pacusam import services

    assert services.list_cycles(conn, pid) == []
    resp = demo_login.post(f"/projects/{pid}/retrain", follow_redirects=False)
    assert resp.status_code == 200
    cycles = services.list_cycles(conn, pid)
    assert len(cycles) == 1

    a = demo_login.get(f"/projects/{pid}/analytics", follow_redirects=False)
    assert a.status_code == 200
    assert f"{cycles[0]['improvement_pct']}" in a.text


def test_analytics_proyecto_ajeno_es_404(client, conn):
    """IDOR: analytics de un proyecto ajeno -> 404."""
    from conftest import make_user

    user_a = make_user(conn, email="ya@hospital.org")
    pid_a = make_project(conn, owner_id=user_a, name="A-analytics", labels=("normal", "anomalia"))

    client.post(
        "/register",
        data={"email": "yb@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    resp = client.get(f"/projects/{pid_a}/analytics", follow_redirects=False)
    assert resp.status_code == 404
