"""Fixtures + step definitions del test BDD de curado.

El escenario corre contra una app FastAPI fresca con SQLite en memoria, vía TestClient:
verifica el sistema punta a punta como lo usaría un cliente real.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, when, then, parsers

from pacusam.api import create_app


@pytest.fixture
def client():
    return TestClient(create_app(":memory:"))


@pytest.fixture
def ctx():
    return {"resp": None}


@given(parsers.parse("un conjunto de {n:d} imágenes sembradas"))
def imagenes_sembradas(client, n):
    filenames = [f"img_{i}.dcm" for i in range(n)]
    r = client.post("/seed", json={"filenames": filenames})
    assert r.status_code == 201


@when("pido la próxima imagen pendiente")
def pido_proxima(client, ctx):
    ctx["resp"] = client.get("/next")


@when(parsers.parse('valido la próxima imagen con la etiqueta "{label}"'))
def valido_proxima(client, ctx, label):
    img = client.get("/next").json()
    ctx["resp"] = client.post(f"/images/{img['id']}/validate", json={"label": label})


@then("la imagen trae una etiqueta sugerida y un nivel de confianza")
def imagen_con_sugerencia(ctx):
    body = ctx["resp"].json()
    assert body["suggested_label"]
    assert 0.0 <= body["confidence"] <= 1.0


@then("se informa cuántas imágenes pendientes quedan")
def informa_pendientes(ctx):
    assert ctx["resp"].json()["remaining_pending"] >= 1


@then(parsers.parse("el progreso muestra {labeled:d} etiquetada de {total:d} y {pending:d} pendientes"))
def progreso_es(client, labeled, total, pending):
    prog = client.get("/progress").json()
    assert prog["labeled"] == labeled
    assert prog["total"] == total
    assert prog["pending"] == pending
