"""Unit tests de F1/AUC por ciclo de Active Learning (A2, CAPA 1).

al_cycles gana columnas f1/auc. record_cycle las acepta keyword-only al final
(default None, regresion: la llamada posicional sin f1/auc sigue funcionando).
simulate_retrain las calcula deterministicamente y crecientes por numero de ciclo.
"""
from __future__ import annotations

import json

import pytest

from pacusam import db, services


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    c.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    c.execute(
        "INSERT INTO projects (name,owner_id,labels,created_at) VALUES (?,?,?,?)",
        ("P", 1, json.dumps(["X", "Y"]), "t"),
    )
    c.commit()
    return c


def _pending(conn, n, conf=0.6):
    for i in range(n):
        conn.execute(
            "INSERT INTO images (project_id,filename,path,suggested_label,confidence,status) "
            "VALUES (1,?,?,?,?,?)",
            (f"i{i}.jpg", f"/s/i{i}.jpg", "X", conf, "pending"),
        )
    conn.commit()


def test_al_cycles_tiene_columnas_f1_auc():
    conn = db.connect(":memory:")
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(al_cycles)").fetchall()}
    assert {"f1", "auc"} <= cols


def test_record_cycle_posicional_sin_f1_auc_sigue_ok(conn):
    out = services.record_cycle(conn, 1, 10, 0.70, 0.84, 20.0)
    assert out["images_used"] == 10
    assert out["f1"] is None and out["auc"] is None


def test_record_cycle_acepta_f1_auc_keyword(conn):
    out = services.record_cycle(conn, 1, 10, 0.70, 0.84, 20.0, f1=0.9, auc=0.92)
    assert out["f1"] == 0.9 and out["auc"] == 0.92


def test_simulate_retrain_registra_f1_auc_creciente(conn):
    _pending(conn, 6)
    services.simulate_retrain(conn, 1)
    c = services.list_cycles(conn, 1)
    assert "f1" in c[-1] and "auc" in c[-1]
    assert 0.5 <= c[-1]["f1"] <= 0.99
    assert 0.5 <= c[-1]["auc"] <= 0.99
