"""Siembra determinista del demo PACUSAM: 1 usuario + 2 proyectos + imagenes.

Idempotente: re-correr no duplica (usuario por email, proyectos por (owner, name),
imagenes por (project_id, filename) via services.seed_images).

Las imagenes se toman de src/pacusam/static/datasets/<project_id>/ si existen
(las baja scripts/fetch_datasets.py); si el directorio no existe o esta vacio,
no se registran imagenes (no rompe).

Las credenciales demo (DEMO_EMAIL/DEMO_PASSWORD) son la FUENTE UNICA (D02): tests,
README y verificaciones las importan desde aqui, nunca las hardcodean.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import auth, services

_STATIC_DATASETS = Path(__file__).parent / "static" / "datasets"

DEMO_EMAIL = "demo@pacusam.org"
DEMO_PASSWORD = "demo1234"

# (id esperado, nombre, descripcion, domain, labels)
DEMO_PROJECTS = [
    {
        "name": "Radiografías de tórax",
        "description": "Curado de radiografías de tórax: detectar neumonía.",
        "domain": "chest_xray",
        "labels": ["NORMAL", "PNEUMONIA"],
    },
    {
        "name": "Células sanguíneas",
        "description": "Clasificación de leucocitos en frotis de sangre.",
        "domain": "blood_cells",
        "labels": ["NEUTROPHIL", "EOSINOPHIL", "LYMPHOCYTE", "MONOCYTE"],
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_demo_user(conn) -> int:
    """Crea (o devuelve) el usuario demo via auth.create_user. Idempotente por email."""
    row = conn.execute("SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone()
    if row:
        return row["id"]
    user = auth.create_user(conn, DEMO_EMAIL, DEMO_PASSWORD)
    return user["id"]


def _ensure_project(conn, owner_id: int, spec: dict) -> int:
    """Crea (o devuelve) un proyecto por (owner_id, name). Idempotente."""
    row = conn.execute(
        "SELECT id FROM projects WHERE owner_id = ? AND name = ?",
        (owner_id, spec["name"]),
    ).fetchone()
    if row:
        return row["id"]
    conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (
            spec["name"],
            spec["description"],
            owner_id,
            spec["domain"],
            json.dumps(spec["labels"]),
            _now(),
        ),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM projects WHERE owner_id = ? AND name = ?",
        (owner_id, spec["name"]),
    ).fetchone()["id"]


def _filenames_for(project_id: int) -> list[str]:
    """Imagenes a registrar: archivos .jpeg/.png/.jpg presentes en el dir del dataset.
    Si el dir no existe o esta vacio, devuelve [] (no rompe el demo)."""
    d = _STATIC_DATASETS / str(project_id)
    if not d.is_dir():
        return []
    files = sorted(
        p.name
        for p in d.iterdir()
        if p.is_file() and p.suffix.lower() in (".jpeg", ".jpg", ".png")
    )
    return files


def seed_demo(conn) -> dict:
    """Siembra el demo completo. Devuelve un resumen {user_id, projects, images_inserted}."""
    owner_id = _ensure_demo_user(conn)
    project_ids: list[int] = []
    total_images = 0
    for spec in DEMO_PROJECTS:
        pid = _ensure_project(conn, owner_id, spec)
        project_ids.append(pid)
        filenames = _filenames_for(pid)
        if filenames:
            total_images += services.seed_images(conn, pid, filenames)
    return {
        "user_id": owner_id,
        "projects": project_ids,
        "images_inserted": total_images,
    }


def seed_if_empty(conn) -> bool:
    """Re-seed determinista al arrancar: siembra el demo solo si no hay proyectos.
    Devuelve True si sembro, False si ya habia datos. El Track API la invoca en
    create_app para que el deploy tenga datos al abrir sin pisar lo existente."""
    count = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    if count > 0:
        return False
    seed_demo(conn)
    return True


if __name__ == "__main__":
    from . import db

    conn = db.connect()
    summary = seed_demo(conn)
    print(f"seed demo: {summary}")
