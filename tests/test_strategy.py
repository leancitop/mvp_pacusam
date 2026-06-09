"""Unit tests de la estrategia de sampling en la cola (A1, CAPA 1).

Estrategias: uncertainty (default, orden actual), sequential (id ASC), random
(determinista por seed via random.Random(seed).shuffle). Params opcionales al
final: el DEFAULT preserva el comportamiento de uncertainty.
"""
from __future__ import annotations

import pytest

from pacusam import db, services


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    c.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    c.execute("INSERT INTO projects (name,owner_id,labels,created_at) VALUES ('P',1,'[\"X\",\"Y\"]','t')")
    # 3 pending con confidencias distintas, en orden de insercion a/b/c.
    for fn, cf in [("a.jpg", 0.95), ("b.jpg", 0.55), ("c.jpg", 0.75)]:
        c.execute(
            "INSERT INTO images (project_id,filename,path,suggested_label,confidence) "
            "VALUES (1,?,?,?,?)",
            (fn, "/s/" + fn, "X", cf),
        )
    c.commit()
    return c


def test_uncertainty_trae_la_menos_confiada_primero(conn):
    item = services.queue_next(conn, 1, strategy="uncertainty")
    assert item["filename"] == "b.jpg"  # 0.55 -> mayor incertidumbre


def test_sequential_trae_por_id(conn):
    item = services.queue_next(conn, 1, strategy="sequential")
    assert item["filename"] == "a.jpg"  # menor id


def test_random_es_determinista_por_seed(conn):
    a = services.queue_next(conn, 1, strategy="random", seed=42)
    b = services.queue_next(conn, 1, strategy="random", seed=42)
    assert a["id"] == b["id"]


def test_default_sigue_siendo_uncertainty(conn):
    assert services.queue_next(conn, 1)["filename"] == "b.jpg"


def test_queue_list_random_orden_completo_determinista_y_distinto_de_sequential(conn):
    r1 = [i["id"] for i in services.queue_list(conn, 1, strategy="random", seed=42)]
    r2 = [i["id"] for i in services.queue_list(conn, 1, strategy="random", seed=42)]
    assert r1 == r2  # mismo seed -> mismo orden completo
    seq = [i["id"] for i in services.queue_list(conn, 1, strategy="sequential")]
    assert seq == sorted(seq)
    assert r1 != seq  # el shuffle con seed=42 no coincide con id ASC


def test_queue_list_default_sigue_siendo_uncertainty(conn):
    ids = [i["id"] for i in services.queue_list(conn, 1)]
    # b (0.55) primero, c (0.75), a (0.95) ultimo
    by_fn = {i["filename"]: i["id"] for i in services.queue_list(conn, 1)}
    assert ids[0] == by_fn["b.jpg"]
    assert ids[-1] == by_fn["a.jpg"]
