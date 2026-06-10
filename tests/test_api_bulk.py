"""Tests de endpoint para aprobar pendientes en lote (CAPA 2 - API, C2 / P2).

Login demo (D02). Cubre: POST /projects/{id}/bulk-validate aprueba las pendientes
propias con confidence>=0.9 cuando no llegan ids; con ids del form, filtra IDOR
(WHERE project_id=? AND id IN(...)) antes de validar; el toast dice "N aprobadas".
"""
from __future__ import annotations

from conftest import make_project, make_user, seed_image


def _demo_user_id(conn):
    from pacusam import seed

    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (seed.DEMO_EMAIL,)
    ).fetchone()["id"]


def test_bulk_validate_aprueba_pendientes_de_alta_confianza(demo_login, conn):
    """Sin ids en el form: el server arma la lista de pendientes propias >=0.9."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Bulk", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="hi1.jpeg", label="normal", confidence=0.95)
    seed_image(conn, pid, filename="hi2.jpeg", label="normal", confidence=0.92)
    seed_image(conn, pid, filename="lo1.jpeg", label="normal", confidence=0.60)

    from pacusam import services

    resp = demo_login.post(f"/projects/{pid}/bulk-validate", follow_redirects=False)
    assert resp.status_code == 200
    assert "2 aprobadas" in resp.text
    prog = services.progress(conn, pid)
    assert prog["validated"] == 2
    assert prog["pending"] == 1  # la de baja confianza queda pendiente


def test_bulk_validate_filtra_ids_del_form_al_proyecto(demo_login, conn):
    """Con ids en el form, solo se validan los del proyecto (IDOR)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="BulkIds", labels=("normal", "anomalia"))
    a = seed_image(conn, pid, filename="m1.jpeg", label="normal", confidence=0.50)
    b = seed_image(conn, pid, filename="m2.jpeg", label="normal", confidence=0.50)

    from pacusam import services

    resp = demo_login.post(
        f"/projects/{pid}/bulk-validate",
        data={"ids": [str(a), str(b)]},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "2 aprobadas" in resp.text
    assert services.progress(conn, pid)["validated"] == 2


def test_bulk_validate_cross_user_no_valida_imagenes_ajenas(demo_login, conn):
    """IDOR: B no puede validar imagenes de A pasandolas por el form de su propio proyecto."""
    uid = _demo_user_id(conn)
    pid_b = make_project(conn, owner_id=uid, name="Bdest", labels=("normal", "anomalia"))

    # Proyecto e imagen de otro usuario (A).
    user_a = make_user(conn, email="bulka@hospital.org")
    pid_a = make_project(conn, owner_id=user_a, name="A-bulk", labels=("normal", "anomalia"))
    img_a = seed_image(conn, pid_a, filename="ajena.jpeg", label="normal", confidence=0.95)

    from pacusam import services

    # demo (B) intenta validar la imagen de A pasandola por el form de su proyecto.
    resp = demo_login.post(
        f"/projects/{pid_b}/bulk-validate",
        data={"ids": [str(img_a)]},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert "0 aprobadas" in resp.text
    # La imagen de A sigue pendiente: no fue tocada.
    row = conn.execute("SELECT status FROM images WHERE id = ?", (img_a,)).fetchone()
    assert row["status"] == "pending"


def test_bulk_validate_proyecto_ajeno_es_404(client, conn):
    """IDOR: bulk-validate sobre un proyecto ajeno -> 404."""
    user_a = make_user(conn, email="bca@hospital.org")
    pid_a = make_project(conn, owner_id=user_a, name="A-bulk2", labels=("normal", "anomalia"))

    client.post(
        "/register",
        data={"email": "bcb@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    resp = client.post(f"/projects/{pid_a}/bulk-validate", follow_redirects=False)
    assert resp.status_code == 404
