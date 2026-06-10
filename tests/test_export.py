"""Unit tests del export de dataset (US-23, CAPA 1 - backend logico).

Cubre: export_rows (solo validadas no rechazadas, con campos esperados) y
export_summary (total + conteo por clase).
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


def test_export_rows_solo_validadas_no_rechazadas(conn):
    pid = _mk_project(conn)
    v1 = _img(conn, pid, "a.dcm", "normal", 0.9)
    v2 = _img(conn, pid, "b.dcm", "normal", 0.8)
    rej = _img(conn, pid, "c.dcm", "normal", 0.7)
    _img(conn, pid, "d.dcm", "normal", 0.6)  # pending
    services.validate_image(conn, v1, "normal")
    services.validate_image(conn, v2, "anomalia")  # corregida
    services.reject_image(conn, rej, "borrosa")
    rows = services.export_rows(conn, pid)
    filenames = {r["filename"] for r in rows}
    assert filenames == {"a.dcm", "b.dcm"}
    by_fn = {r["filename"]: r for r in rows}
    assert by_fn["a.dcm"]["final_label"] == "normal"
    assert by_fn["a.dcm"]["suggested_label"] == "normal"
    assert by_fn["b.dcm"]["final_label"] == "anomalia"
    assert by_fn["a.dcm"]["confidence"] == 0.9
    assert by_fn["a.dcm"]["validated_at"]


def test_export_rows_vacio_sin_validadas(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "a.dcm", "normal", 0.9)  # pending
    assert services.export_rows(conn, pid) == []


def test_export_summary_total_y_por_clase(conn):
    pid = _mk_project(conn)
    n = [_img(conn, pid, f"n{i}.dcm", "normal", 0.9) for i in range(3)]
    a = _img(conn, pid, "an.dcm", "anomalia", 0.8)
    rej = _img(conn, pid, "rej.dcm", "normal", 0.7)
    _img(conn, pid, "pend.dcm", "normal", 0.6)
    for i in n:
        services.validate_image(conn, i, "normal")
    services.validate_image(conn, a, "anomalia")
    services.reject_image(conn, rej, "mala")
    summary = services.export_summary(conn, pid)
    assert summary["total"] == 4
    by_class = {c["label"]: c["count"] for c in summary["by_class"]}
    assert by_class == {"normal": 3, "anomalia": 1}


def test_export_summary_vacio(conn):
    pid = _mk_project(conn)
    summary = services.export_summary(conn, pid)
    assert summary["total"] == 0
    assert summary["by_class"] == []
