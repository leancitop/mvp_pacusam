"""Capa de datos. SQLite mínimo — una sola tabla de imágenes para el MVP.

La iteración 1 cubre solo US-10 (validar imágenes pre-clasificadas), así que el
esquema es deliberadamente chico: nada de usuarios/proyectos todavía.
"""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT NOT NULL,
    suggested_label TEXT,
    confidence      REAL,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | validated
    final_label     TEXT,
    validated_at    TEXT
);
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    """Abre conexión y garantiza el esquema. `path` puede ser archivo o ':memory:'."""
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
