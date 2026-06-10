"""Unit tests de la capa de datos (CAPA 1 — backend lógico)."""
from __future__ import annotations

import sqlite3

from pacusam import db


def test_connect_devuelve_row_factory():
    conn = db.connect(":memory:")
    assert conn.row_factory is sqlite3.Row


def test_connect_crea_las_tres_tablas():
    conn = db.connect(":memory:")
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"users", "projects", "images"} <= names


def test_users_tiene_email_unico():
    conn = db.connect(":memory:")
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
        ("a@b.com", "h", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
            ("a@b.com", "h2", "2026-01-01T00:00:00+00:00"),
        )
        assert False, "debía violar UNIQUE(email)"
    except sqlite3.IntegrityError:
        pass


def test_images_status_default_pending():
    conn = db.connect(":memory:")
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES ('u@x.com','h','t')"
    )
    conn.execute(
        "INSERT INTO projects (name, owner_id, labels, created_at) "
        "VALUES ('P', 1, '[\"NORMAL\"]', 't')"
    )
    conn.execute(
        "INSERT INTO images (project_id, filename, path) VALUES (1, 'a.jpg', '/a.jpg')"
    )
    conn.commit()
    row = conn.execute("SELECT status FROM images WHERE id=1").fetchone()
    assert row["status"] == "pending"


def test_images_confidence_default_05():
    """D19: confidence nunca NULL — DEFAULT 0.5."""
    conn = db.connect(":memory:")
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES ('u@x.com','h','t')"
    )
    conn.execute(
        "INSERT INTO projects (name, owner_id, labels, created_at) "
        "VALUES ('P', 1, '[\"NORMAL\"]', 't')"
    )
    conn.execute(
        "INSERT INTO images (project_id, filename, path) VALUES (1, 'a.jpg', '/a.jpg')"
    )
    conn.commit()
    row = conn.execute("SELECT confidence FROM images WHERE id=1").fetchone()
    assert row["confidence"] == 0.5


def test_indice_unico_project_filename():
    conn = db.connect(":memory:")
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES ('u@x.com','h','t')"
    )
    conn.execute(
        "INSERT INTO projects (name, owner_id, labels, created_at) "
        "VALUES ('P', 1, '[\"NORMAL\"]', 't')"
    )
    conn.execute(
        "INSERT INTO images (project_id, filename, path) VALUES (1, 'a.jpg', '/a.jpg')"
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO images (project_id, filename, path) VALUES (1, 'a.jpg', '/dup.jpg')"
        )
        assert False, "debía violar el índice único (project_id, filename)"
    except sqlite3.IntegrityError:
        pass


def test_connect_aplica_wal_y_busy_timeout(tmp_path):
    """D18: WAL + busy_timeout=3000 (sobre archivo; :memory: no soporta WAL)."""
    p = str(tmp_path / "wal.db")
    conn = db.connect(p)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
    timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout == 3000


def test_connect_es_idempotente_sobre_archivo(tmp_path):
    p = str(tmp_path / "x.db")
    db.connect(p)
    conn2 = db.connect(p)  # segunda apertura no debe romper (CREATE IF NOT EXISTS)
    names = {
        r["name"]
        for r in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"users", "projects", "images"} <= names


def test_connect_default_usa_env_pacusam_db(tmp_path, monkeypatch):
    p = str(tmp_path / "env.db")
    monkeypatch.setenv("PACUSAM_DB", p)
    conn = db.connect()
    assert conn.execute("SELECT 1").fetchone()[0] == 1
