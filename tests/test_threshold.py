"""Unit tests del umbral de re-entrenamiento por proyecto (A3, CAPA 1).

projects gana retrain_threshold INTEGER DEFAULT 10. threshold_status usa
COALESCE(retrain_threshold, 10) y reporta validadas/restantes/alcanzado.
"""
from __future__ import annotations

import json

import pytest

from pacusam import db, services


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    c.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    c.commit()
    return c


def test_projects_tiene_columna_retrain_threshold(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(projects)").fetchall()}
    assert "retrain_threshold" in cols


def test_threshold_status(conn):
    conn.execute(
        "INSERT INTO projects (name,owner_id,labels,created_at,retrain_threshold) "
        "VALUES (?,?,?,?,?)",
        ("P", 1, json.dumps(["X"]), "t", 10),
    )
    for i in range(12):
        st = "validated" if i < 6 else "pending"
        conn.execute(
            "INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label) "
            "VALUES (1,?,?,?,?,?,?)",
            (f"i{i}.jpg", f"/s/i{i}.jpg", "X", 0.6, st, "X" if st == "validated" else None),
        )
    conn.commit()
    t = services.threshold_status(conn, 1)
    assert t["threshold"] == 10
    assert t["validated"] == 6
    assert t["remaining"] == 4
    assert t["reached"] is False


def test_threshold_default_10_via_create_project(conn):
    """create_project no pasa threshold: COALESCE devuelve el default 10."""
    p = services.create_project(conn, owner_id=1, name="Nuevo", description="", domain="rx", labels=["X"])
    t = services.threshold_status(conn, p["id"])
    assert t["threshold"] == 10


def test_threshold_reached_true(conn):
    conn.execute(
        "INSERT INTO projects (name,owner_id,labels,created_at,retrain_threshold) "
        "VALUES (?,?,?,?,?)",
        ("P", 1, json.dumps(["X"]), "t", 3),
    )
    for i in range(5):
        conn.execute(
            "INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label) "
            "VALUES (1,?,?,?,?, 'validated','X')",
            (f"i{i}.jpg", f"/s/i{i}.jpg", "X", 0.6),
        )
    conn.commit()
    t = services.threshold_status(conn, 1)
    assert t["validated"] == 5
    assert t["remaining"] == 0
    assert t["reached"] is True
