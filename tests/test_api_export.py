"""Tests de endpoint del export de dataset (US-23, CAPA 2 — API).

Login demo (D02). Cubre: GET /export.csv (text/csv + Content-Disposition attachment
con columnas filename, final_label, suggested_label, confidence, validated_at) y
GET /export.json (filas + summary). Ambos protegidos por _owned_project (404 ajeno).
"""
from __future__ import annotations

import csv
import io

from conftest import demo_project_ids, make_project, seed_image


def _demo_user_id(conn):
    from pacusam import seed

    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (seed.DEMO_EMAIL,)
    ).fetchone()["id"]


def test_export_csv_content_type_y_attachment(demo_login, conn):
    """GET /export.csv -> 200, content-type text/csv, header de descarga."""
    pid = demo_project_ids(conn)[0]
    resp = demo_login.get(f"/projects/{pid}/export.csv", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers.get("content-disposition", "")


def test_export_csv_tiene_header_y_filas_validadas(demo_login, conn):
    """El CSV trae el header esperado y una fila por cada imagen validada."""
    pid = demo_project_ids(conn)[0]
    resp = demo_login.get(f"/projects/{pid}/export.csv", follow_redirects=False)
    reader = csv.reader(io.StringIO(resp.text))
    rows = list(reader)
    assert rows[0] == [
        "filename",
        "final_label",
        "suggested_label",
        "confidence",
        "validated_at",
    ]
    # El seed deja 14 validadas por proyecto -> 14 filas de datos + 1 header.
    assert len(rows) == 15


def test_export_json_trae_rows_y_summary(demo_login, conn):
    """GET /export.json -> 200 con keys rows (lista) y summary (total + by_class)."""
    pid = demo_project_ids(conn)[0]
    resp = demo_login.get(f"/projects/{pid}/export.json", follow_redirects=False)
    assert resp.status_code == 200
    data = resp.json()
    assert "rows" in data and "summary" in data
    assert isinstance(data["rows"], list)
    assert len(data["rows"]) == 14
    assert data["summary"]["total"] == 14
    assert {"label", "count"} <= set(data["summary"]["by_class"][0].keys())
    # Cada fila trae los campos del export de dominio.
    assert {"filename", "final_label", "suggested_label", "confidence", "validated_at"} <= set(
        data["rows"][0].keys()
    )


def test_export_csv_proyecto_ajeno_es_404(client, conn):
    """IDOR: el usuario B no puede exportar el CSV de un proyecto de A."""
    from conftest import make_user

    user_a = make_user(conn, email="ea@hospital.org")
    pid_a = make_project(conn, owner_id=user_a, name="A-export", labels=("normal", "anomalia"))
    seed_image(conn, pid_a, filename="aa.jpeg")

    client.post(
        "/register",
        data={"email": "eb@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    resp = client.get(f"/projects/{pid_a}/export.csv", follow_redirects=False)
    assert resp.status_code == 404


def test_export_json_proyecto_ajeno_es_404(client, conn):
    """IDOR: el usuario B no puede exportar el JSON de un proyecto de A."""
    from conftest import make_user

    user_a = make_user(conn, email="ea2@hospital.org")
    pid_a = make_project(conn, owner_id=user_a, name="A-export2", labels=("normal", "anomalia"))

    client.post(
        "/register",
        data={"email": "eb2@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    resp = client.get(f"/projects/{pid_a}/export.json", follow_redirects=False)
    assert resp.status_code == 404


def test_export_csv_sin_login_redirige(client, conn):
    """Sin sesion, el export redirige a /login (require_user / _RedirectException)."""
    pid = demo_project_ids(conn)[0]
    resp = client.get(f"/projects/{pid}/export.csv", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
