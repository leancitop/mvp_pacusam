"""Fixtures compartidas de la capa de endpoint (CAPA 5 — tests de API + BDD).

Migracion del legacy (D10): un solo `conftest.py` que monta la app nueva
(`create_app`) sobre un archivo SQLite temporal y expone helpers project-scoped.

Por que archivo temporal y no ':memory:' (D03/D10): `create_app` comparte UNA
conexion (`app.state.conn`), pero el `TestClient`/uvicorn pueden usar otro hilo;
un archivo evita que ':memory:' quede aislado por conexion. Cada test recibe una
DB fresca via `tmp_path`.

Cookies de sesion (nota de Capa 4 / D25): por defecto la app setea la cookie con
`https_only=True`, asi que sobre http (TestClient plano) NO viaja y la sesion se
pierde. Seteamos `PACUSAM_INSECURE_COOKIES=1` ANTES de `create_app` para relajar
solo `https_only` en tests; el default de produccion sigue seguro.

Las credenciales demo se IMPORTAN de seed (D02), nunca se hardcodean.
"""
from __future__ import annotations

import json
import os

import pytest
from fastapi.testclient import TestClient

# D25 / nota Capa 4: relajar https_only para que la cookie de sesion viaje sobre
# http en el TestClient. Debe setearse ANTES de create_app (lee la env ahi).
os.environ.setdefault("PACUSAM_INSECURE_COOKIES", "1")

from pacusam import api, seed  # noqa: E402  (import tras setear la env)


@pytest.fixture
def app(tmp_path):
    """App fresca sobre un archivo SQLite temporal. Arranca con el seed demo
    (seed_if_empty en create_app): usuario demo + 2 proyectos + imagenes reales."""
    db_file = tmp_path / "pacusam_test.db"
    return api.create_app(db_path=str(db_file))


@pytest.fixture
def conn(app):
    """La UNICA conexion de la app (app.state.conn). Los helpers seed-by-SQL
    escriben aca para que la API vea los mismos datos (no abrir una 2da conexion)."""
    return app.state.conn


@pytest.fixture
def client(app):
    """TestClient sobre la app. raise_server_exceptions=False para poder
    inspeccionar respuestas de error (404/422) en vez de que se propaguen."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def demo_login(client):
    """Loguea al usuario demo sembrado (D02) y devuelve el client con sesion viva.
    Sigue el 303 -> GET / (200). Falla ruidosamente si la sesion no se mantiene."""
    resp = client.post(
        "/login",
        data={"email": seed.DEMO_EMAIL, "password": seed.DEMO_PASSWORD},
        follow_redirects=True,
    )
    assert resp.status_code == 200, "login demo deberia terminar en home 200"
    return client


# --------------------------------------------------------- helpers seed-by-SQL

def make_user(conn, email="otro@pacusam.org", password="secreto123"):
    """Crea un usuario via auth (hash real) sobre la conexion de la app.
    Devuelve su id. Util para los tests de IDOR (segundo usuario)."""
    from pacusam import auth

    return auth.create_user(conn, email, password)["id"]


def make_project(conn, owner_id, name="Proyecto Test", labels=("normal", "anomalia")):
    """Inserta un proyecto por SQL directo y devuelve su id (D10: helper seed-by-SQL
    con project_id explicito)."""
    cur = conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES (?, '', ?, 'rx', ?, '2026-01-01T00:00:00+00:00')",
        (name, owner_id, json.dumps(list(labels))),
    )
    conn.commit()
    return cur.lastrowid


def seed_image(conn, project_id, filename="img.jpeg", label="normal",
               confidence=0.6, status="pending"):
    """Inserta UNA imagen en el proyecto (project_id explicito) y devuelve su id.
    `path` imita el layout de static/datasets/<project_id>/<filename>."""
    cur = conn.execute(
        "INSERT INTO images (project_id, filename, path, suggested_label, "
        "confidence, status) VALUES (?,?,?,?,?,?)",
        (
            project_id,
            filename,
            f"/static/datasets/{project_id}/{filename}",
            label,
            confidence,
            status,
        ),
    )
    conn.commit()
    return cur.lastrowid


def demo_project_ids(conn):
    """Ids de los 2 proyectos demo sembrados, en orden de creacion."""
    rows = conn.execute("SELECT id FROM projects ORDER BY id").fetchall()
    return [r["id"] for r in rows]
