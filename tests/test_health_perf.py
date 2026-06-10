"""Endpoint /health + evidencia de performance (ISO/IEC 25010).

Fiabilidad: /health responde 200 con JSON {status, version} sin requerir sesion.
Eficiencia: la pagina de login responde holgadamente por debajo de 3s.
"""
import time

from fastapi.testclient import TestClient

from pacusam.api import create_app


def test_health_ok(tmp_path):
    c = TestClient(create_app(db_path=str(tmp_path / "t.db")))
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_login_carga_rapido(tmp_path):
    # Evidencia de Eficiencia (ISO 25010): la pagina responde holgadamente < 3s.
    c = TestClient(create_app(db_path=str(tmp_path / "t.db")))
    t0 = time.perf_counter()
    r = c.get("/login")
    dt = time.perf_counter() - t0
    assert r.status_code == 200 and dt < 3.0
