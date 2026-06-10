"""Politica de password server-side (ISO/IEC 25010 — Seguridad).

El template register.html ya tiene minlength=6 client-side; aca verificamos la
regla server-side: create_user rechaza passwords < 6 con DomainError.
"""
import pytest

from pacusam import auth, db
from pacusam.services import DomainError


def test_password_corta_es_rechazada():
    conn = db.connect(":memory:")
    with pytest.raises(DomainError) as e:
        auth.create_user(conn, "a@b.com", "123")
    assert e.value.code == "password_too_short"


def test_password_valida_ok():
    conn = db.connect(":memory:")
    u = auth.create_user(conn, "a@b.com", "secreto1")
    assert u["email"] == "a@b.com"
