"""Unit tests de ab_summary + dataset_health (B2, CAPA 1).

ab_summary reusa time_saved + throughput (3s/img AL vs 30s/img manual) + concordance;
caso vacio neutro. dataset_health usa umbral relativo (ideal=100/n_clases), nunca el
33% fijo; caso vacio -> status 'sin datos', minority None.
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


def _project(conn, labels):
    cur = conn.execute(
        "INSERT INTO projects (name,owner_id,labels,created_at) VALUES (?,?,?,?)",
        ("P", 1, json.dumps(list(labels)), "t"),
    )
    conn.commit()
    return cur.lastrowid


def test_ab_summary_usa_baseline_manual(conn):
    pid = _project(conn, ["X"])
    for i in range(10):
        conn.execute(
            "INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label,shown_at,validated_at) "
            "VALUES (?,?,?,?,?, 'validated','X','t','t')",
            (pid, f"i{i}.jpg", f"/s/i{i}.jpg", "X", 0.8),
        )
    conn.commit()
    ab = services.ab_summary(conn, pid)
    assert ab["manual_seconds"] > ab["al_seconds"]
    assert ab["saved_pct"] > 0
    assert ab["throughput_al"] > ab["throughput_manual"]
    assert "concordance" in ab


def test_ab_summary_vacio_es_neutro(conn):
    pid = _project(conn, ["X"])
    ab = services.ab_summary(conn, pid)
    assert ab["saved_pct"] == 0.0
    assert ab["al_seconds"] == 0.0


def test_dataset_health_detecta_desbalance(conn):
    pid = _project(conn, ["X", "Y"])
    for i in range(9):
        conn.execute(
            "INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label,validated_at) "
            "VALUES (?,?,?,?,0.8,'validated',?, 't')",
            (pid, f"i{i}.jpg", f"/s/i{i}.jpg", "X", "X" if i < 8 else "Y"),
        )
    conn.commit()
    h = services.dataset_health(conn, pid)
    assert h["status"] in ("rojo", "amarillo")
    assert h["minority"]["label"] == "Y"


def test_dataset_health_vacio_neutro(conn):
    pid = _project(conn, ["X", "Y"])
    h = services.dataset_health(conn, pid)
    assert h["status"] == "sin datos"
    assert h["minority"] is None


def test_dataset_health_balanceado_es_verde(conn):
    pid = _project(conn, ["X", "Y"])
    for i in range(10):
        conn.execute(
            "INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label,validated_at) "
            "VALUES (?,?,?,?,0.8,'validated',?, 't')",
            (pid, f"i{i}.jpg", f"/s/i{i}.jpg", "X", "X" if i < 5 else "Y"),
        )
    conn.commit()
    h = services.dataset_health(conn, pid)
    assert h["status"] == "verde"
