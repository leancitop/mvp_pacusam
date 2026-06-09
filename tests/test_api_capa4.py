"""Tests de endpoint de CAPA 4 (verificacion final).

Aceptacion explicita de los cuatro contratos de endpoint que la UI consume:
- GET /export.csv: 200, content-type CSV, y contiene una fila de una imagen validada
  concreta (filename + final_label) con su header.
- GET /export.json: 200, con summary (total + by_class) y filas alineadas a las
  validadas.
- GET /queue?label=X: devuelve el filmstrip FILTRADO (solo la clase pedida, excluye
  las otras clases del proyecto).
- GET /analytics: incluye los ciclos AL (list_cycles) renderizados en el historial.

Datos sembrados de forma DETERMINISTA con los helpers de conftest (project_id
explicito) para poder afirmar contenido exacto sin depender del dataset en disco.
Login demo (D02). No duplican los tests de CAPA 2 (test_api_export/filter/cycles):
aca afirmamos contenido concreto, no solo forma.
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


def _proyecto_con_validada(conn):
    """Crea un proyecto del usuario demo con una imagen validada concreta y
    devuelve (project_id, filename, final_label). La validacion va por la capa
    de dominio para que validated_at y final_label queden persistidos como en
    produccion."""
    from pacusam import services

    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Export concreto", labels=("normal", "anomalia"))
    img_id = seed_image(conn, pid, filename="caso_007.jpeg", label="normal", confidence=0.61)
    # Corregimos a 'anomalia' para distinguir suggested_label de final_label.
    services.validate_image(conn, img_id, "anomalia")
    # Una pendiente que NO debe salir en el export.
    seed_image(conn, pid, filename="pendiente_x.jpeg", label="normal", confidence=0.4)
    return pid, "caso_007.jpeg", "anomalia"


# ----------------------------------------------------------------- export.csv

def test_export_csv_contiene_fila_validada_concreta(demo_login, conn):
    """GET /export.csv -> 200, text/csv, y trae la fila de la imagen validada con
    su filename y su final_label corregido (no la pendiente)."""
    pid, filename, final_label = _proyecto_con_validada(conn)

    resp = demo_login.get(f"/projects/{pid}/export.csv", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    # Solo la validada (la pendiente queda fuera del export).
    assert len(rows) == 1
    fila = rows[0]
    assert fila["filename"] == filename
    assert fila["final_label"] == final_label
    assert fila["suggested_label"] == "normal"  # se conserva la sugerencia original
    assert fila["validated_at"]  # timestamp de validacion presente


# ---------------------------------------------------------------- export.json

def test_export_json_trae_summary_con_total_y_by_class(demo_login, conn):
    """GET /export.json -> 200 con summary.total = nro de validadas y by_class con
    el conteo de la clase final."""
    pid, filename, final_label = _proyecto_con_validada(conn)

    resp = demo_login.get(f"/projects/{pid}/export.json", follow_redirects=False)
    assert resp.status_code == 200
    data = resp.json()

    assert data["summary"]["total"] == 1
    assert data["summary"]["by_class"] == [{"label": final_label, "count": 1}]
    assert len(data["rows"]) == 1
    assert data["rows"][0]["filename"] == filename
    assert data["rows"][0]["final_label"] == final_label


# ------------------------------------------------------------- filtro /queue

def test_queue_con_label_devuelve_filmstrip_filtrado(demo_login, conn):
    """GET /queue?label=anomalia -> 200 y el filmstrip solo lista la clase pedida,
    excluyendo las miniaturas de las otras clases del proyecto."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Queue filtrada c4", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="norm_a.jpeg", label="normal", confidence=0.55)
    seed_image(conn, pid, filename="norm_b.jpeg", label="normal", confidence=0.62)
    seed_image(conn, pid, filename="anom_a.jpeg", label="anomalia", confidence=0.51)

    resp = demo_login.get(
        f"/projects/{pid}/queue", params={"label": "anomalia"}, follow_redirects=False
    )
    assert resp.status_code == 200
    assert "anom_a.jpeg" in resp.text
    assert "norm_a.jpeg" not in resp.text
    assert "norm_b.jpeg" not in resp.text


def test_queue_filtrado_marca_el_chip_activo(demo_login, conn):
    """El filtro re-renderiza los chips OOB marcando la clase activa (active_label)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Queue chip activo", labels=("normal", "anomalia"))
    seed_image(conn, pid, filename="cc_n.jpeg", label="normal", confidence=0.55)
    seed_image(conn, pid, filename="cc_a.jpeg", label="anomalia", confidence=0.52)

    resp = demo_login.get(
        f"/projects/{pid}/queue", params={"label": "anomalia"}, follow_redirects=False
    )
    assert resp.status_code == 200
    # Chips OOB para reflejar la clase activa en el panel de filtros de curado.
    assert 'id="filter-chips"' in resp.text
    assert "hx-swap-oob" in resp.text


# ----------------------------------------------------------- analytics cycles

def test_analytics_incluye_ciclos_con_su_mejora(demo_login, conn):
    """GET /analytics -> 200 y renderiza el historial de ciclos AL: el porcentaje de
    mejora de cada ciclo aparece en el HTML."""
    from pacusam import services

    pid = demo_project_ids(conn)[0]
    cycles = services.list_cycles(conn, pid)
    assert len(cycles) >= 1  # el seed deja ciclos vivos

    resp = demo_login.get(f"/projects/{pid}/analytics", follow_redirects=False)
    assert resp.status_code == 200
    for c in cycles:
        assert f"{c['improvement_pct']}" in resp.text
