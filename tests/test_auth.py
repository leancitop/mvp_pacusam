"""Unit tests de auth.py (CAPA 1 — backend logico).

Hashing con hashlib.pbkdf2_hmac (stdlib): formato 'pbkdf2_sha256$iter$salt$hash'.
Sin passlib/bcrypt (decision de arquitectura: cero dependencias C).
"""
from __future__ import annotations

import pytest

from pacusam import auth, db


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_hash_password_no_es_plano():
    h = auth.hash_password("secreto123")
    assert h != "secreto123"
    assert h.startswith("pbkdf2_sha256$")
    # formato: algo$iteraciones$salt$hash -> 4 partes
    assert len(h.split("$")) == 4


def test_hash_password_salt_aleatorio():
    # mismo password -> hashes distintos (salt aleatorio)
    assert auth.hash_password("secreto123") != auth.hash_password("secreto123")


def test_verify_password_roundtrip():
    h = auth.hash_password("secreto123")
    assert auth.verify_password("secreto123", h) is True
    assert auth.verify_password("otra-cosa", h) is False


def test_verify_password_hash_malformado_no_rompe():
    assert auth.verify_password("x", "no-es-un-hash-valido") is False


def test_db_tiene_tabla_users(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert {"id", "email", "password_hash", "created_at"} <= cols


def test_create_user_devuelve_dict(conn):
    u = auth.create_user(conn, "ana@hospital.org", "secreto123")
    assert u["id"] >= 1
    assert u["email"] == "ana@hospital.org"
    assert "password_hash" not in u  # no exponemos el hash


def test_create_user_persiste_hash(conn):
    auth.create_user(conn, "ana@hospital.org", "secreto123")
    row = conn.execute(
        "SELECT password_hash FROM users WHERE email=?", ("ana@hospital.org",)
    ).fetchone()
    assert row["password_hash"].startswith("pbkdf2_sha256$")
    assert row["password_hash"] != "secreto123"


def test_create_user_email_duplicado(conn):
    auth.create_user(conn, "ana@hospital.org", "secreto123")
    with pytest.raises(auth.DomainError) as exc:
        auth.create_user(conn, "ana@hospital.org", "otra-pass")
    assert exc.value.code == "email_exists"


def test_authenticate_ok(conn):
    creado = auth.create_user(conn, "ana@hospital.org", "secreto123")
    u = auth.authenticate(conn, "ana@hospital.org", "secreto123")
    assert u is not None
    assert u["id"] == creado["id"]
    assert "password_hash" not in u


def test_authenticate_password_invalida(conn):
    auth.create_user(conn, "ana@hospital.org", "secreto123")
    assert auth.authenticate(conn, "ana@hospital.org", "mal") is None


def test_authenticate_email_inexistente(conn):
    assert auth.authenticate(conn, "nadie@hospital.org", "x") is None


def test_get_user_ok(conn):
    creado = auth.create_user(conn, "ana@hospital.org", "secreto123")
    u = auth.get_user(conn, creado["id"])
    assert u["email"] == "ana@hospital.org"
    assert "password_hash" not in u


def test_get_user_inexistente(conn):
    assert auth.get_user(conn, 9999) is None
