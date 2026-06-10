"""Unit tests del filtro por etiqueta (US-17, CAPA 1 - backend logico).

Cubre: queue_list con parametro opcional label (filtra por suggested_label) y
label_counts (conteo por suggested_label sobre TODAS las imagenes).
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


def test_queue_list_sin_label_devuelve_todas(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "a.dcm", "normal", 0.55)
    _img(conn, pid, "b.dcm", "anomalia", 0.60)
    items = services.queue_list(conn, pid)
    assert len(items) == 2


def test_queue_list_label_none_explicito_devuelve_todas(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "a.dcm", "normal", 0.55)
    _img(conn, pid, "b.dcm", "anomalia", 0.60)
    items = services.queue_list(conn, pid, label=None)
    assert len(items) == 2


def test_queue_list_filtra_por_suggested_label(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "a.dcm", "normal", 0.55)
    _img(conn, pid, "b.dcm", "anomalia", 0.60)
    _img(conn, pid, "c.dcm", "normal", 0.70)
    items = services.queue_list(conn, pid, label="normal")
    assert {i["filename"] for i in items} == {"a.dcm", "c.dcm"}
    assert all(i["suggested_label"] == "normal" for i in items)


def test_queue_list_filtro_mantiene_orden_incertidumbre(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "alta.dcm", "normal", 0.90)  # inc 0.10
    _img(conn, pid, "baja.dcm", "normal", 0.55)  # inc 0.45
    items = services.queue_list(conn, pid, label="normal")
    assert [i["filename"] for i in items] == ["baja.dcm", "alta.dcm"]


def test_label_counts_cuenta_todas_por_suggested_label(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "a.dcm", "normal", 0.9, status="validated")
    _img(conn, pid, "b.dcm", "normal", 0.8, status="pending")
    _img(conn, pid, "c.dcm", "anomalia", 0.7, status="rejected")
    counts = dict(services.label_counts(conn, pid))
    assert counts == {"normal": 2, "anomalia": 1}


def test_label_counts_vacio(conn):
    pid = _mk_project(conn)
    assert services.label_counts(conn, pid) == []
