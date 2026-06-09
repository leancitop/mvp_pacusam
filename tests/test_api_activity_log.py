"""Tests de que las rutas de curado registran actividad (CAPA 2 - API, D2 / _log).

El helper _log() en api.py es best-effort y se llama tras un _guard exitoso en
validate/reject/unreject. Verifica que la accion queda registrada en activity_log
con el usuario de sesion, el image_id y el project_id correctos.
"""
from __future__ import annotations

from conftest import make_project, seed_image


def _demo_user_id(conn):
    from pacusam import seed

    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (seed.DEMO_EMAIL,)
    ).fetchone()["id"]


def test_validate_registra_actividad(demo_login, conn):
    """POST validate -> entrada 'validate' en activity_log del usuario demo."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="LogVal", labels=("normal", "anomalia"))
    img = seed_image(conn, pid, filename="lv.jpeg", label="normal", confidence=0.55)

    demo_login.post(f"/images/{img}/validate", data={"label": "normal"}, follow_redirects=False)

    from pacusam import services

    rows = services.list_activity(conn, user_id=uid, action="validate")
    assert len(rows) == 1
    assert rows[0]["image_id"] == img
    assert rows[0]["project_id"] == pid


def test_reject_y_unreject_registran_actividad(demo_login, conn):
    """reject y unreject quedan registrados con el usuario de sesion."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="LogRej", labels=("normal", "anomalia"))
    img = seed_image(conn, pid, filename="lr.jpeg", label="normal", confidence=0.55)

    demo_login.post(f"/images/{img}/reject", data={"reason": "borrosa"}, follow_redirects=False)
    demo_login.post(f"/images/{img}/unreject", follow_redirects=False)

    from pacusam import services

    assert len(services.list_activity(conn, user_id=uid, action="reject")) == 1
    assert len(services.list_activity(conn, user_id=uid, action="unreject")) == 1


def test_log_no_rompe_si_falla(demo_login, conn):
    """El _log es best-effort: una accion exitosa sigue devolviendo 200 aunque el log
    fallara. Aca solo confirmamos que validate sigue 200 con log activo."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="LogOk", labels=("normal", "anomalia"))
    img = seed_image(conn, pid, filename="lo.jpeg", label="normal", confidence=0.55)
    resp = demo_login.post(
        f"/images/{img}/validate", data={"label": "normal"}, follow_redirects=False
    )
    assert resp.status_code == 200
