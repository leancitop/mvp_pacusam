"""Capa de autenticacion (CAPA 1).

Hashing de contrasenas con hashlib.pbkdf2_hmac (stdlib) — SIN passlib/bcrypt, para
no arrastrar dependencias C. Formato del hash almacenado:

    pbkdf2_sha256$<iteraciones>$<salt_hex>$<hash_hex>

Operaciones de dominio sobre la tabla `users`. No conoce HTTP: la capa `api` la
envuelve (SessionMiddleware + require_user). Errores de negocio via
services.DomainError(code), re-exportado como auth.DomainError.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
from datetime import datetime, timezone

from .services import DomainError  # re-exportado: auth.DomainError

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 200_000
_SALT_BYTES = 16
_HASH_NAME = "sha256"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    """Hash PBKDF2-HMAC-SHA256 con salt aleatorio.

    Devuelve 'pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>'.
    """
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGO}${_ITERATIONS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """True si `password` coincide con el hash almacenado. Tolerante a hashes
    malformados (devuelve False en vez de lanzar)."""
    try:
        algo, iter_s, salt_hex, hash_hex = password_hash.split("$")
        if algo != _ALGO:
            return False
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    dk = hashlib.pbkdf2_hmac(_HASH_NAME, password.encode("utf-8"), salt, iterations)
    # comparacion en tiempo constante
    return hmac.compare_digest(dk, expected)


def _user_dict(row) -> dict:
    """Proyeccion publica de un usuario (sin password_hash)."""
    return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}


def create_user(conn, email: str, password: str) -> dict:
    """Crea un usuario. Lanza DomainError('email_exists') si el email ya existe."""
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
            (email, hash_password(password), _now()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise DomainError("email_exists", "El email ya esta registrado")
    row = conn.execute(
        "SELECT id, email, created_at FROM users WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _user_dict(row)


def authenticate(conn, email: str, password: str) -> dict | None:
    """Devuelve el usuario (sin hash) si las credenciales son validas; None si no."""
    row = conn.execute(
        "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    if row is None:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return _user_dict(row)


def get_user(conn, user_id: int) -> dict | None:
    """Usuario por id (sin hash), o None si no existe."""
    row = conn.execute(
        "SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return _user_dict(row) if row else None
