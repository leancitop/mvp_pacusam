"""Unit tests de bulk_validate + gallery (C2-backend, CAPA 1).

bulk_validate es best-effort: try/except DomainError por id, cuenta solo exitos,
no aborta el lote. gallery filtra por nombre parcial (LIKE) y/o label.
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


def _project(conn, labels=("X", "Y")):
    cur = conn.execute(
        "INSERT INTO projects (name,owner_id,labels,created_at) VALUES (?,?,?,?)",
        ("P", 1, json.dumps(list(labels)), "t"),
    )
    conn.commit()
    return cur.lastrowid


def _img(conn, pid, fn, label="X", conf=0.95):
    cur = conn.execute(
        "INSERT INTO images (project_id,filename,path,suggested_label,confidence) "
        "VALUES (?,?,?,?,?)",
        (pid, fn, "/s/" + fn, label, conf),
    )
    conn.commit()
    return cur.lastrowid


def test_bulk_validate_confirma_la_sugerencia(conn):
    pid = _project(conn)
    ids = [_img(conn, pid, f"i{i}.jpg") for i in range(3)]
    n = services.bulk_validate(conn, ids)
    assert n == 3
    assert services.progress(conn, pid)["validated"] == 3


def test_bulk_validate_best_effort_ignora_sin_suggested(conn):
    """Una imagen sin suggested_label no rompe el lote; se cuentan solo los exitos."""
    pid = _project(conn)
    ok1 = _img(conn, pid, "ok1.jpg")
    bad = _img(conn, pid, "bad.jpg", label=None)  # sin suggested_label
    ok2 = _img(conn, pid, "ok2.jpg")
    n = services.bulk_validate(conn, [ok1, bad, ok2])
    assert n == 2  # solo los dos validos
    assert services.progress(conn, pid)["validated"] == 2


def test_gallery_busca_por_nombre_parcial(conn):
    pid = _project(conn, labels=("X",))
    for fn in ["rx_0001.jpg", "rx_0002.jpg", "bccd_5.jpg"]:
        _img(conn, pid, fn, label="X", conf=0.7)
    r = services.gallery(conn, pid, q="rx_000")
    assert len(r) == 2
    assert services.gallery(conn, pid, q="zzz") == []


def test_gallery_filtra_por_label(conn):
    pid = _project(conn, labels=("X", "Y"))
    _img(conn, pid, "a.jpg", label="X")
    _img(conn, pid, "b.jpg", label="Y")
    r = services.gallery(conn, pid, label="Y")
    assert len(r) == 1 and r[0]["filename"] == "b.jpg"


def test_gallery_sin_filtros_devuelve_todas(conn):
    pid = _project(conn, labels=("X",))
    for fn in ["a.jpg", "b.jpg"]:
        _img(conn, pid, fn, label="X")
    assert len(services.gallery(conn, pid)) == 2
