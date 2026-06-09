"""Unit tests del historial de ciclos AL (US-16, CAPA 1 - backend logico).

Cubre: tabla al_cycles idempotente, record_cycle/list_cycles, y que
simulate_retrain registra un ciclo cada vez que corre con mejora real.
"""
from __future__ import annotations

import json

import pytest

from pacusam import db, services


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    c.execute(
        "INSERT INTO users (email, password_hash, created_at) "
        "VALUES ('demo@pacusam.org','h','2026-01-01T00:00:00+00:00')"
    )
    c.commit()
    return c


def _mk_project(conn, owner_id=1, name="P", labels=("normal", "anomalia")):
    cur = conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES (?, '', ?, 'rx', ?, '2026-01-01T00:00:00+00:00')",
        (name, owner_id, json.dumps(list(labels))),
    )
    conn.commit()
    return cur.lastrowid


def _img(conn, project_id, filename="x.dcm", label="normal", conf=0.6, status="pending"):
    cur = conn.execute(
        "INSERT INTO images (project_id, filename, path, suggested_label, confidence, status) "
        "VALUES (?,?,?,?,?,?)",
        (project_id, filename, f"/p/{filename}", label, conf, status),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------- tabla / schema

def test_tabla_al_cycles_existe_y_es_idempotente(tmp_path):
    p = str(tmp_path / "x.db")
    db.connect(p)
    conn2 = db.connect(p)  # segunda apertura no debe romper (CREATE IF NOT EXISTS)
    names = {
        r["name"]
        for r in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "al_cycles" in names


def test_al_cycles_tiene_columnas_esperadas():
    conn = db.connect(":memory:")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(al_cycles)").fetchall()}
    assert {
        "id",
        "project_id",
        "created_at",
        "images_used",
        "avg_conf_before",
        "avg_conf_after",
        "improvement_pct",
    } <= cols


# ---------------------------------------------------------------- record / list

def test_record_cycle_devuelve_dict_y_persiste(conn):
    pid = _mk_project(conn)
    out = services.record_cycle(conn, pid, 10, 0.70, 0.84, 20.0)
    assert out["project_id"] == pid
    assert out["images_used"] == 10
    assert out["avg_conf_before"] == 0.70
    assert out["avg_conf_after"] == 0.84
    assert out["improvement_pct"] == 20.0
    assert out["created_at"]
    assert out["id"] >= 1
    row = conn.execute(
        "SELECT * FROM al_cycles WHERE id = ?", (out["id"],)
    ).fetchone()
    assert row["project_id"] == pid
    assert row["images_used"] == 10


def test_list_cycles_orden_cronologico(conn):
    pid = _mk_project(conn)
    services.record_cycle(conn, pid, 5, 0.60, 0.70, 16.7)
    services.record_cycle(conn, pid, 8, 0.70, 0.80, 14.3)
    cycles = services.list_cycles(conn, pid)
    assert len(cycles) == 2
    assert cycles[0]["images_used"] == 5
    assert cycles[1]["images_used"] == 8
    assert cycles[0]["created_at"] <= cycles[1]["created_at"]


def test_list_cycles_aisla_por_proyecto(conn):
    p1 = _mk_project(conn, name="P1")
    p2 = _mk_project(conn, name="P2")
    services.record_cycle(conn, p1, 5, 0.60, 0.70, 16.7)
    services.record_cycle(conn, p2, 9, 0.50, 0.80, 60.0)
    assert len(services.list_cycles(conn, p1)) == 1
    assert services.list_cycles(conn, p1)[0]["images_used"] == 5


def test_list_cycles_vacio(conn):
    pid = _mk_project(conn)
    assert services.list_cycles(conn, pid) == []


# ---------------------------------------------------------------- integracion retrain

def test_simulate_retrain_registra_un_ciclo(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "p1.dcm", "normal", 0.50)
    _img(conn, pid, "p2.dcm", "anomalia", 0.60)
    assert services.list_cycles(conn, pid) == []
    res = services.simulate_retrain(conn, pid)
    assert res["status"] == "ok"
    cycles = services.list_cycles(conn, pid)
    assert len(cycles) == 1
    c = cycles[0]
    assert c["images_used"] == 2
    assert c["avg_conf_after"] > c["avg_conf_before"]
    assert c["improvement_pct"] == res["improvement_pct"]


def test_simulate_retrain_calibrado_no_registra_ciclo(conn):
    """Si el modelo ya esta calibrado (sin cambios), no se registra ciclo."""
    pid = _mk_project(conn)
    _img(conn, pid, "p1.dcm", "normal", 0.93)
    _img(conn, pid, "p2.dcm", "anomalia", 0.94)
    res = services.simulate_retrain(conn, pid)
    assert res["status"] == "calibrado"
    assert services.list_cycles(conn, pid) == []


def test_simulate_retrain_sin_pending_no_registra_ciclo(conn):
    pid = _mk_project(conn)
    services.simulate_retrain(conn, pid)
    assert services.list_cycles(conn, pid) == []
