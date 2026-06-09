"""Capa de datos. SQLite a archivo (env PACUSAM_DB) o :memory: en tests.

Esquema canónico del MVP académico PACUSAM: usuarios, proyectos y sus imágenes.
Las tablas se crean con IF NOT EXISTS para que connect() sea idempotente.

Decisiones canónicas aplicadas:
- D18: una sola conexión compartida con WAL + busy_timeout=3000.
- D19: images.confidence REAL DEFAULT 0.5 (nunca NULL en la pantalla estrella).
- #integración: índice único ux_images_project_filename (project_id, filename).
"""
from __future__ import annotations

import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'curador',  -- D1: curador | admin
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    name              TEXT NOT NULL,
    description       TEXT,
    owner_id          INTEGER NOT NULL REFERENCES users(id),
    domain            TEXT,
    labels            TEXT NOT NULL,          -- JSON array de strings
    retrain_threshold INTEGER DEFAULT 10,     -- A3: validadas para el proximo retrain
    created_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    filename        TEXT NOT NULL,
    path            TEXT NOT NULL,
    suggested_label TEXT,
    confidence      REAL DEFAULT 0.5,        -- D19: nunca NULL, 0.50-0.99 al sembrar
    status          TEXT DEFAULT 'pending',  -- pending | validated | rejected
    final_label     TEXT,
    reject_reason   TEXT,
    shown_at        TEXT,
    validated_at    TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_images_project_filename
    ON images (project_id, filename);

CREATE TABLE IF NOT EXISTS al_cycles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    created_at      TEXT,
    images_used     INTEGER,
    avg_conf_before REAL,
    avg_conf_after  REAL,
    improvement_pct REAL,
    f1              REAL,   -- A2: F1 mockeado por ciclo (creciente)
    auc             REAL    -- A2: AUC mockeado por ciclo (creciente)
);

CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER,
    action      TEXT NOT NULL,
    image_id    INTEGER,
    project_id  INTEGER,
    created_at  TEXT NOT NULL
);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    """Abre conexión y garantiza el esquema.

    `path=None` usa la env var PACUSAM_DB (default 'pacusam.db').
    Pasar ':memory:' explícitamente para tests.

    Aplica PRAGMA journal_mode=WAL + busy_timeout=3000 (D18) sobre conexiones a
    archivo (WAL no aplica a :memory:, pero el PRAGMA no rompe).
    """
    if path is None:
        path = os.environ.get("PACUSAM_DB", "pacusam.db")
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=3000")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
