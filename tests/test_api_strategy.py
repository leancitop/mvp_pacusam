"""Tests de endpoint para la estrategia de sampling en GET /queue (CAPA 2 - API, A1).

Login demo (D02). Cubre: el query param `strategy` se valida contra
{uncertainty, random, sequential}; una estrategia desconocida cae a uncertainty;
el filmstrip (queue_list) SIEMPRE usa uncertainty (no se rompe test_api_filter).
"""
from __future__ import annotations

from conftest import demo_project_ids, make_project, seed_image


def _demo_user_id(conn):
    from pacusam import seed

    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (seed.DEMO_EMAIL,)
    ).fetchone()["id"]


def test_queue_strategy_sequential_trae_menor_id_primero(demo_login, conn):
    """strategy=sequential: la card es la de menor id (no la mas incierta)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Seq", labels=("normal", "anomalia"))
    first = seed_image(conn, pid, filename="z_high.jpeg", confidence=0.95)
    seed_image(conn, pid, filename="a_low.jpeg", confidence=0.50)

    resp = demo_login.get(
        f"/projects/{pid}/queue", params={"strategy": "sequential"}, follow_redirects=False
    )
    assert resp.status_code == 200
    # sequential -> menor id (la primera insertada), aunque sea la mas confiada.
    assert f'data-image-id="{first}"' in resp.text


def test_queue_strategy_uncertainty_default(demo_login, conn):
    """Sin strategy: comportamiento uncertainty (la mas incierta primero)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Unc", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="conf.jpeg", confidence=0.95)
    low = seed_image(conn, pid, filename="dudo.jpeg", confidence=0.50)

    resp = demo_login.get(f"/projects/{pid}/queue", follow_redirects=False)
    assert resp.status_code == 200
    assert f'data-image-id="{low}"' in resp.text


def test_queue_strategy_desconocida_cae_a_uncertainty(demo_login, conn):
    """strategy invalida -> uncertainty (la mas incierta), sin error."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Bad", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="conf2.jpeg", confidence=0.95)
    low = seed_image(conn, pid, filename="dudo2.jpeg", confidence=0.50)

    resp = demo_login.get(
        f"/projects/{pid}/queue", params={"strategy": "no-existe"}, follow_redirects=False
    )
    assert resp.status_code == 200
    assert f'data-image-id="{low}"' in resp.text


def test_queue_strategy_no_rompe_filmstrip_filtrado(demo_login, conn):
    """El filmstrip sigue filtrando por label aunque se pida una strategy distinta.

    a1 (anomalia) es la de menor id, asi es a la vez la card sequential-next y el
    unico item del filmstrip filtrado por 'anomalia'; n1 (normal) no debe aparecer
    en ningun lado del fragmento."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="SeqFilm", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="a1.jpeg", label="anomalia", confidence=0.52)
    seed_image(conn, pid, filename="n1.jpeg", label="normal", confidence=0.55)

    resp = demo_login.get(
        f"/projects/{pid}/queue",
        params={"strategy": "sequential", "label": "anomalia"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "a1.jpeg" in resp.text
    assert "n1.jpeg" not in resp.text


def test_queue_strategy_proyecto_ajeno_es_404(client, conn):
    """IDOR: queue con strategy de un proyecto ajeno -> 404."""
    from conftest import make_user

    user_a = make_user(conn, email="sa@hospital.org")
    pid_a = make_project(conn, owner_id=user_a, name="A-strat", labels=("normal", "anomalia"))
    seed_image(conn, pid_a, filename="aa.jpeg")

    client.post(
        "/register",
        data={"email": "sb@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    resp = client.get(
        f"/projects/{pid_a}/queue", params={"strategy": "sequential"}, follow_redirects=False
    )
    assert resp.status_code == 404
