"""Unit tests del log de actividad (D2, CAPA 1).

activity_log(id, user_id, action, image_id, project_id, created_at).
log_activity inserta con timestamp; list_activity lista filtrable, orden desc.
"""
from __future__ import annotations

import pytest

from pacusam import db, services


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_activity_log_tiene_columnas(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(activity_log)").fetchall()}
    assert {"id", "user_id", "action", "image_id", "project_id", "created_at"} <= cols


def test_log_y_listado_de_actividad(conn):
    services.log_activity(conn, user_id=1, action="validate", image_id=5, project_id=1)
    rows = services.list_activity(conn)
    assert rows[0]["action"] == "validate"
    assert rows[0]["image_id"] == 5
    assert rows[0]["created_at"]


def test_log_activity_image_y_project_opcionales(conn):
    out = services.log_activity(conn, user_id=2, action="create_project")
    assert out["image_id"] is None
    assert out["project_id"] is None


def test_list_activity_orden_desc(conn):
    services.log_activity(conn, user_id=1, action="a")
    services.log_activity(conn, user_id=1, action="b")
    services.log_activity(conn, user_id=1, action="c")
    rows = services.list_activity(conn)
    assert [r["action"] for r in rows] == ["c", "b", "a"]


def test_list_activity_filtra_por_usuario_y_accion(conn):
    services.log_activity(conn, user_id=1, action="validate")
    services.log_activity(conn, user_id=2, action="reject")
    services.log_activity(conn, user_id=1, action="reject")
    assert len(services.list_activity(conn, user_id=1)) == 2
    assert len(services.list_activity(conn, action="reject")) == 2
    assert len(services.list_activity(conn, user_id=1, action="reject")) == 1


def test_list_activity_limit(conn):
    for i in range(5):
        services.log_activity(conn, user_id=1, action=f"a{i}")
    assert len(services.list_activity(conn, limit=2)) == 2
