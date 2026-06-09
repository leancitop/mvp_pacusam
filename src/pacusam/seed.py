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
from datetime import datetime, timedelta, timezone
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


# Timestamp base del curado sembrado: fijo para que el re-seed sea reproducible
# (D02/determinismo). Las decididas obtienen shown_at/validated_at derivados de
# este ancla y su indice, asi time_saved (D12) da numeros sin depender de _now().
_SEED_ANCHOR = datetime(2026, 6, 1, 9, 0, 0, tzinfo=timezone.utc)
_SEED_TARGET_VALIDATED_PCT = 0.35  # ~35% validadas


def _live_plan(total: int) -> tuple[int, int]:
    """Cuantas rechazar y cuantas validar de forma DETERMINISTA, dejando pendientes.

    Escala con el tamano del dataset: rechaza 1 si es chico, hasta 3 si es grande,
    y valida ~35% del resto. Garantiza validadas>=1, rechazadas>=1 y pendientes>=1
    siempre que haya al menos 3 imagenes."""
    if total < 3:
        return 0, 0
    rejected = 1 if total < 8 else min(3, total // 8)
    remaining = total - rejected
    validated = max(1, round(total * _SEED_TARGET_VALIDATED_PCT))
    # Dejar al menos una pendiente: no validar todo lo que queda.
    validated = min(validated, remaining - 1)
    return rejected, validated


def _seed_live_progress(conn, project_id: int) -> None:
    """Marca de forma DETERMINISTA (por indice, sin random) parte del proyecto como
    validado/rechazado con timestamps plausibles, y registra 2 ciclos AL de ejemplo.

    La mayoria de las validadas confirman la sugerencia (concordancia alta y creible
    ~85%); unas pocas se corrigen a otra label. Re-seed reproducible: depende solo
    del orden por id y de _SEED_ANCHOR. Deja suficientes pendientes para la demo."""
    labels = json.loads(
        conn.execute(
            "SELECT labels FROM projects WHERE id = ?", (project_id,)
        ).fetchone()["labels"]
    )
    images = conn.execute(
        "SELECT id, suggested_label FROM images WHERE project_id = ? ORDER BY id",
        (project_id,),
    ).fetchall()
    total = len(images)
    n_reject, n_validate = _live_plan(total)

    # Rechazos: las ultimas n_reject por id (motivo deterministico).
    reject_reasons = ["imagen borrosa", "fuera de foco", "artefacto de captura"]
    reject_ids = {images[total - 1 - i]["id"] for i in range(n_reject)} if n_reject else set()

    # Validadas: las primeras imagenes que NO esten rechazadas.
    validate_rows = [r for r in images if r["id"] not in reject_ids][:n_validate]

    step = 0
    for idx, r in enumerate(validate_rows):
        suggested = r["suggested_label"] or (labels[0] if labels else "")
        # Corregir ~1 de cada 7 para que la concordancia no sea 100% (creible).
        if labels and len(labels) > 1 and idx % 7 == 6:
            others = [l for l in labels if l != suggested]
            final_label = others[idx % len(others)] if others else suggested
        else:
            final_label = suggested
        shown_at = (_SEED_ANCHOR + timedelta(minutes=step)).isoformat()
        validated_at = (_SEED_ANCHOR + timedelta(minutes=step, seconds=3)).isoformat()
        conn.execute(
            "UPDATE images SET status='validated', final_label=?, reject_reason=NULL, "
            "shown_at=?, validated_at=? WHERE id=?",
            (final_label, shown_at, validated_at, r["id"]),
        )
        step += 1

    for i, iid in enumerate(sorted(reject_ids)):
        shown_at = (_SEED_ANCHOR + timedelta(minutes=step)).isoformat()
        validated_at = (_SEED_ANCHOR + timedelta(minutes=step, seconds=4)).isoformat()
        conn.execute(
            "UPDATE images SET status='rejected', reject_reason=?, final_label=NULL, "
            "shown_at=?, validated_at=? WHERE id=?",
            (reject_reasons[i % len(reject_reasons)], shown_at, validated_at, iid),
        )
        step += 1
    conn.commit()

    # 2 ciclos AL de ejemplo con precision creciente (~78% -> ~84%).
    used = max(n_validate, 1)
    services.record_cycle(conn, project_id, used, 0.72, 0.78, 8.3)
    services.record_cycle(conn, project_id, used, 0.78, 0.84, 7.7)


def seed_if_empty(conn) -> bool:
    """Re-seed determinista al arrancar: siembra el demo solo si no hay proyectos.
    Devuelve True si sembro, False si ya habia datos. El Track API la invoca en
    create_app para que el deploy tenga datos al abrir sin pisar lo existente.

    Ademas deja cada proyecto con progreso parcial vivo (validadas/rechazadas/
    ciclos AL) para que analytics arranque con numeros reales, dejando pendientes."""
    count = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    if count > 0:
        return False
    summary = seed_demo(conn)
    for pid in summary["projects"]:
        _seed_live_progress(conn, pid)
    return True


if __name__ == "__main__":
    from . import db

    conn = db.connect()
    summary = seed_demo(conn)
    print(f"seed demo: {summary}")
