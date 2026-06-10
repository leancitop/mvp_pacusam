"""Steps del acceptance BDD del curado (CAPA 5 — migracion legacy D10).

Project-scoped: cada escenario siembra un proyecto con imagenes de confianza
controlada (por SQL, project_id explicito) y ejerce la capa de dominio
(queue_next / validate_image / reject_image / progress). 3 escenarios:
cola por incertidumbre, validar actualiza progreso, rechazar+motivo excluye.
"""
from __future__ import annotations

import json

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from pacusam import db, services

scenarios("curado.feature")


@pytest.fixture
def conn():
    return db.connect(":memory:")


@pytest.fixture
def ctx():
    return {"project_id": None, "current": None}


@given(parsers.parse("un proyecto con imágenes de confianza {c1:f}, {c2:f} y {c3:f}"))
def proyecto_con_confianzas(conn, ctx, c1, c2, c3):
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at) "
        "VALUES ('demo@pacusam.org','h','2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES ('P', '', 1, 'rx', ?, '2026-01-01T00:00:00+00:00')",
        (json.dumps(["normal", "anomalia"]),),
    )
    conn.commit()
    pid = conn.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1").fetchone()["id"]
    for i, c in enumerate((c1, c2, c3)):
        conn.execute(
            "INSERT INTO images (project_id, filename, path, suggested_label, "
            "confidence, status) VALUES (?,?,?,?,?, 'pending')",
            (pid, f"img_{i}.jpeg", f"/static/datasets/{pid}/img_{i}.jpeg", "normal", c),
        )
    conn.commit()
    ctx["project_id"] = pid


@when("pido la próxima imagen de la cola")
def pido_proxima(conn, ctx):
    ctx["current"] = services.queue_next(conn, ctx["project_id"])


@when(parsers.parse('valido la próxima imagen de la cola con la etiqueta "{label}"'))
def valido_proxima(conn, ctx, label):
    nxt = services.queue_next(conn, ctx["project_id"])
    services.validate_image(conn, nxt["id"], label)


@when(parsers.parse('rechazo la próxima imagen de la cola con motivo "{motivo}"'))
def rechazo_proxima(conn, ctx, motivo):
    nxt = services.queue_next(conn, ctx["project_id"])
    services.reject_image(conn, nxt["id"], motivo)


@then(parsers.parse("recibo la imagen de confianza {c:f}"))
def recibo_confianza(ctx, c):
    assert ctx["current"] is not None
    assert abs(ctx["current"]["confidence"] - c) < 1e-9


@then(parsers.parse("el progreso muestra {validadas:d} validada y {pendientes:d} pendientes"))
def progreso_validadas(conn, ctx, validadas, pendientes):
    prog = services.progress(conn, ctx["project_id"])
    assert prog["validated"] == validadas
    assert prog["pending"] == pendientes


@then(parsers.parse("el progreso muestra {rechazadas:d} rechazada y {pendientes:d} pendientes"))
def progreso_rechazadas(conn, ctx, rechazadas, pendientes):
    prog = services.progress(conn, ctx["project_id"])
    assert prog["rejected"] == rechazadas
    assert prog["pending"] == pendientes


@then(parsers.parse("la próxima imagen de la cola es la de confianza {c:f}"))
def proxima_es_confianza(conn, ctx, c):
    nxt = services.queue_next(conn, ctx["project_id"])
    assert nxt is not None
    assert abs(nxt["confidence"] - c) < 1e-9
