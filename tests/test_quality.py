"""Unit tests de calidad: conflicts, confusion_matrix, quality_metrics (B1, CAPA 1).

Caso 0-validadas: matriz de ceros, accuracy 0.0, per_class 0.0 (sin excepcion).
Label fuera del set: se ignora (guarda 'if lbl in labels'), sin excepcion.
"""
from __future__ import annotations

import json

import pytest

from pacusam import db, services


def _seed_validated(conn, pairs, labels=("X", "Y")):
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute(
        "INSERT INTO projects (name,owner_id,labels,created_at) VALUES (?,?,?,?)",
        ("P", 1, json.dumps(list(labels)), "t"),
    )
    for i, (sug, fin) in enumerate(pairs):
        conn.execute(
            "INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label,validated_at) "
            "VALUES (1,?,?,?,0.8,'validated',?,'t')",
            (f"i{i}.jpg", f"/s/i{i}.jpg", sug, fin),
        )
    conn.commit()


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_conflicts_lista_discordancias(conn):
    _seed_validated(conn, [("X", "X"), ("X", "Y"), ("Y", "Y")])
    c = services.conflicts(conn, 1)
    assert len(c) == 1
    assert c[0]["suggested_label"] == "X" and c[0]["final_label"] == "Y"


def test_confusion_matrix(conn):
    _seed_validated(conn, [("X", "X"), ("X", "Y"), ("Y", "Y")])
    m = services.confusion_matrix(conn, 1)
    assert m["labels"] == ["X", "Y"]
    assert m["matrix"][0][0] == 1
    assert m["matrix"][0][1] == 1
    assert m["matrix"][1][1] == 1


def test_quality_metrics(conn):
    _seed_validated(conn, [("X", "X"), ("X", "Y"), ("Y", "Y")])
    q = services.quality_metrics(conn, 1)
    assert 0 <= q["accuracy"] <= 1
    assert "per_class" in q
    labels_out = {pc["label"] for pc in q["per_class"]}
    assert labels_out == {"X", "Y"}


def test_confusion_matrix_sin_validadas_es_ceros(conn):
    _seed_validated(conn, [])  # 0 validadas
    m = services.confusion_matrix(conn, 1)
    assert m["labels"] == ["X", "Y"]
    assert m["matrix"] == [[0, 0], [0, 0]]


def test_quality_metrics_sin_validadas_es_neutro(conn):
    _seed_validated(conn, [])
    q = services.quality_metrics(conn, 1)
    assert q["accuracy"] == 0.0
    for pc in q["per_class"]:
        assert pc["precision"] == 0.0 and pc["recall"] == 0.0


def test_confusion_matrix_ignora_label_fuera_de_set(conn):
    # 'Z' no esta en labels ["X","Y"]: se ignora sin excepcion.
    _seed_validated(conn, [("X", "X"), ("Z", "X"), ("X", "Z")])
    m = services.confusion_matrix(conn, 1)
    assert m["labels"] == ["X", "Y"]
    assert m["matrix"][0][0] == 1  # solo el par X/X valido cuenta


def test_quality_metrics_ignora_label_fuera_de_set(conn):
    _seed_validated(conn, [("X", "X"), ("Z", "X"), ("X", "Z")])
    q = services.quality_metrics(conn, 1)  # no debe romper
    assert 0 <= q["accuracy"] <= 1
