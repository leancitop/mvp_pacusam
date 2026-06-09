"""Unit tests de roles de usuario (D1, CAPA 1 - backend logico).

Roles: 'curador' (default) y 'admin'. La columna role vive en users con DEFAULT
'curador'. create_user/authenticate/get_user devuelven role; nunca password_hash.
"""
from __future__ import annotations

import pytest

from pacusam import auth, db


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_users_tiene_columna_role(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert "role" in cols


def test_create_user_default_curador_y_admin_explicito(conn):
    u = auth.create_user(conn, "c@x.com", "secreto1")
    assert u["role"] == "curador"
    a = auth.create_user(conn, "a@x.com", "secreto1", role="admin")
    assert a["role"] == "admin"


def test_create_user_no_expone_hash(conn):
    u = auth.create_user(conn, "c@x.com", "secreto1")
    assert "password_hash" not in u


def test_authenticate_devuelve_role(conn):
    auth.create_user(conn, "a@x.com", "secreto1", role="admin")
    u = auth.authenticate(conn, "a@x.com", "secreto1")
    assert u is not None
    assert u["role"] == "admin"
    assert "password_hash" not in u


def test_get_user_devuelve_role(conn):
    creado = auth.create_user(conn, "c@x.com", "secreto1")
    u = auth.get_user(conn, creado["id"])
    assert u["role"] == "curador"
    assert "password_hash" not in u
