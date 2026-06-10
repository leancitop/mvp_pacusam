"""Capa de dominio. Logica de negocio del curado asistido sobre una conexion SQLite.

No conoce HTTP: la capa `api` la envuelve. Errores de negocio via DomainError(code).
Funciones project-scoped: proyectos, imagenes, cola por incertidumbre (Active
Learning), validacion/rechazo, progreso y analytics (concordancia, distribucion,
retrain simulado y tiempo ahorrado).
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timezone

from . import classifier, events, pipeline


class DomainError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================ proyectos

def _project_row_to_dict(row) -> dict:
    """Normaliza una fila de projects: deserializa labels (JSON array)."""
    d = dict(row)
    d["labels"] = json.loads(d["labels"]) if d.get("labels") else []
    return d


def _project_labels(conn, project_id: int) -> list[str]:
    """Labels (JSON array) del proyecto. DomainError si no existe."""
    row = conn.execute(
        "SELECT labels FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if not row:
        raise DomainError("project_not_found", "Proyecto inexistente")
    return json.loads(row["labels"])


def list_projects(conn, owner_id: int) -> list[dict]:
    """Proyectos de un owner, mas recientes primero. labels ya deserializado."""
    rows = conn.execute(
        "SELECT * FROM projects WHERE owner_id = ? ORDER BY created_at DESC, id DESC",
        (owner_id,),
    ).fetchall()
    return [_project_row_to_dict(r) for r in rows]


def create_project(
    conn, owner_id: int, name: str, description: str, domain: str, labels: list[str]
) -> dict:
    """Crea un proyecto. name obligatorio (<=100 chars). labels se guarda como JSON."""
    name = (name or "").strip()
    if not name:
        raise DomainError("name_required", "El nombre es obligatorio")
    if len(name) > 100:
        raise DomainError("name_too_long", "El nombre no puede superar 100 caracteres")
    ts = _now()
    cur = conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (name, description or "", owner_id, domain or "", json.dumps(list(labels or [])), ts),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)).fetchone()
    return _project_row_to_dict(row)


def get_project(conn, project_id: int) -> dict:
    """Proyecto por id. DomainError('project_not_found') si no existe."""
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise DomainError("project_not_found", "Proyecto inexistente")
    return _project_row_to_dict(row)


# ============================================================ imagenes / seed

def _image_row(conn, image_id: int):
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if not row:
        raise DomainError("image_not_found", "Imagen inexistente")
    return row


def get_image(conn, image_id: int) -> dict:
    """Devuelve la imagen como dict; DomainError('image_not_found') si no existe."""
    return dict(_image_row(conn, image_id))


def seed_images(conn, project_id: int, filenames: list[str]) -> int:
    """Registra imagenes mockeadas del proyecto en DB, pasando cada una por el
    pipeline de ingesta (Pipes & Filters, A.7): validar formato -> clasificar
    (sugerencia + confianza via el STUB del clasificador). Idempotente por
    (project_id, filename): re-sembrar no duplica. Devuelve cuantas se insertaron.

    `path` apunta al archivo servido estaticamente en static/datasets/<project_id>/.
    """
    labels = _project_labels(conn, project_id)
    inserted = 0
    for fn in filenames:
        exists = conn.execute(
            "SELECT 1 FROM images WHERE project_id = ? AND filename = ?",
            (project_id, fn),
        ).fetchone()
        if exists:
            continue
        # Pipes & Filters (A.7): la ingesta corre los filtros encadenados. El
        # filtro_clasificar usa el MISMO classifier.suggest -> confianza identica.
        ctx = pipeline.run_pipeline(
            pipeline.INGESTA, {"filename": fn, "labels": labels}
        )
        label = ctx["suggested_label"]
        conf = ctx["confidence"]
        path = f"/static/datasets/{project_id}/{fn}"
        conn.execute(
            "INSERT INTO images (project_id, filename, path, suggested_label, "
            "confidence, status) VALUES (?,?,?,?,?, 'pending')",
            (project_id, fn, path, label, conf),
        )
        inserted += 1
    conn.commit()
    # Pub-Sub (A.7): notifica la ingesta de un lote. Aditivo: no cambia el retorno.
    if inserted > 0:
        events.bus.publish(
            events.IMAGENES_SUBIDAS,
            {"conn": conn, "project_id": project_id, "count": inserted},
        )
    return inserted


# ============================================================ cola (Active Learning)

# A1: estrategias de sampling soportadas. uncertainty es el default historico.
_STRATEGIES = ("uncertainty", "sequential", "random")


def _order_rows(rows: list, strategy: str, seed: int | None) -> list:
    """Ordena las filas segun la estrategia de sampling (A1).

    - uncertainty: 1 - COALESCE(confidence, 0.5) DESC, id ASC (comportamiento actual).
    - sequential: id ASC.
    - random: random.Random(seed).shuffle (seed None -> seed=0, determinista).
    Estrategia desconocida cae a uncertainty.
    """
    items = list(rows)
    if strategy == "sequential":
        return sorted(items, key=lambda r: r["id"])
    if strategy == "random":
        rng = random.Random(0 if seed is None else seed)
        shuffled = sorted(items, key=lambda r: r["id"])  # base estable antes de mezclar
        rng.shuffle(shuffled)
        return shuffled
    # uncertainty (default): mas dudosa primero, desempata por id ASC.
    return sorted(
        items,
        key=lambda r: (
            -(1.0 - (r["confidence"] if r["confidence"] is not None else 0.5)),
            r["id"],
        ),
    )


def queue_next(
    conn,
    project_id: int,
    strategy: str = "uncertainty",
    seed: int | None = None,
) -> dict | None:
    """Proxima imagen 'pending' del proyecto segun la estrategia de sampling (A1).

    Default 'uncertainty' = 1 - COALESCE(confidence, 0.5) DESC, id ASC (la MAS dudosa
    primero, D19). 'sequential' = id ASC. 'random' = shuffle determinista por seed.
    None si no quedan pendientes.
    """
    rows = conn.execute(
        "SELECT * FROM images WHERE project_id = ? AND status = 'pending'",
        (project_id,),
    ).fetchall()
    if not rows:
        return None
    ordered = _order_rows(rows, strategy, seed)
    row = ordered[0]
    remaining = len(rows)
    conf = row["confidence"] if row["confidence"] is not None else 0.5
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "filename": row["filename"],
        "path": row["path"],
        "suggested_label": row["suggested_label"],
        "confidence": conf,
        "uncertainty": round(1.0 - conf, 2),
        "remaining_pending": remaining,
    }


def queue_list(
    conn,
    project_id: int,
    label: str | None = None,
    strategy: str = "uncertainty",
    seed: int | None = None,
) -> list[dict]:
    """Todas las imagenes del proyecto, ordenadas segun la estrategia (filmstrip).
    Incluye status para que el front pinte validadas/rechazadas/pendientes.

    US-17: `label` opcional filtra por suggested_label (None = todas las clases).
    A1: `strategy`/`seed` opcionales al final; el default sigue siendo uncertainty.
    """
    sql = (
        "SELECT id, filename, path, suggested_label, confidence, status, final_label "
        "FROM images WHERE project_id = ? "
    )
    params: list = [project_id]
    if label is not None:
        sql += "AND suggested_label = ? "
        params.append(label)
    rows = conn.execute(sql, tuple(params)).fetchall()
    ordered = _order_rows(rows, strategy, seed)
    out = []
    for r in ordered:
        conf = r["confidence"] if r["confidence"] is not None else 0.5
        out.append(
            {
                "id": r["id"],
                "filename": r["filename"],
                "path": r["path"],
                "suggested_label": r["suggested_label"],
                "confidence": conf,
                "uncertainty": round(1.0 - conf, 2),
                "status": r["status"],
                "final_label": r["final_label"],
            }
        )
    return out


def label_counts(conn, project_id: int) -> list[tuple[str, int]]:
    """US-17. Conteo por suggested_label sobre TODAS las imagenes del proyecto
    (cualquier status), para los chips de filtro con su numero. Lista de tuplas
    (label, count) ordenada por count DESC, luego label ASC."""
    rows = conn.execute(
        "SELECT suggested_label AS label, COUNT(*) AS count FROM images "
        "WHERE project_id = ? AND suggested_label IS NOT NULL "
        "GROUP BY suggested_label ORDER BY count DESC, suggested_label ASC",
        (project_id,),
    ).fetchall()
    return [(r["label"], r["count"]) for r in rows]


# ============================================================ bulk (C2)

def bulk_validate(conn, image_ids) -> int:
    """C2. Confirma en lote la sugerencia del modelo para cada imagen (best-effort).

    Para cada id valida con su propio suggested_label. try/except DomainError por id:
    una imagen invalida (sin suggested_label, inexistente, etc.) NO aborta el lote.
    Devuelve la cantidad efectivamente validada.
    """
    validated = 0
    for image_id in image_ids:
        try:
            row = _image_row(conn, image_id)
            validate_image(conn, image_id, row["suggested_label"])
            validated += 1
        except DomainError:
            continue
    return validated


# ============================================================ validar / rechazar

def validate_image(conn, image_id: int, label: str) -> dict:
    """US-10/11. Confirma o corrige la sugerencia; valida contra las labels del proyecto."""
    row = _image_row(conn, image_id)
    if not (label or "").strip():
        raise DomainError("label_required", "La etiqueta es obligatoria")
    if label not in _project_labels(conn, row["project_id"]):
        raise DomainError("invalid_label", "Etiqueta fuera del proyecto")
    ts = _now()
    conn.execute(
        "UPDATE images SET status='validated', final_label=?, reject_reason=NULL, "
        "validated_at=? WHERE id=?",
        (label, ts, image_id),
    )
    conn.commit()
    project_id = row["project_id"]
    # SEP (A.7): cada validacion emite un evento de dominio uno-a-uno.
    events.bus.publish(
        events.IMAGEN_VALIDADA,
        {"conn": conn, "image_id": image_id, "project_id": project_id},
    )
    # CEP (A.7): UmbralAlcanzado es un evento DERIVADO de N ImagenValidada; se
    # publica SOLO en el cruce exacto (validated == threshold) para que dispare
    # una unica vez. Aditivo: no cambia el retorno de la funcion.
    ts_status = threshold_status(conn, project_id)
    if ts_status["validated"] == ts_status["threshold"]:
        events.bus.publish(
            events.UMBRAL_ALCANZADO,
            {
                "conn": conn,
                "project_id": project_id,
                "validated": ts_status["validated"],
                "threshold": ts_status["threshold"],
            },
        )
    return {"id": image_id, "status": "validated", "final_label": label, "validated_at": ts}


def reject_image(conn, image_id: int, reason: str) -> dict:
    """US-12. Marca la imagen como rechazada con un motivo (excluye de la cola)."""
    _image_row(conn, image_id)
    if not (reason or "").strip():
        raise DomainError("reason_required", "El motivo es obligatorio")
    conn.execute(
        "UPDATE images SET status='rejected', reject_reason=?, final_label=NULL, "
        "validated_at=? WHERE id=?",
        (reason.strip(), _now(), image_id),
    )
    conn.commit()
    return {"id": image_id, "status": "rejected", "reject_reason": reason.strip()}


def unreject_image(conn, image_id: int) -> dict:
    """Revierte un rechazo: la imagen vuelve a 'pending' y reaparece en la cola."""
    _image_row(conn, image_id)
    conn.execute(
        "UPDATE images SET status='pending', reject_reason=NULL, final_label=NULL, "
        "validated_at=NULL WHERE id=?",
        (image_id,),
    )
    conn.commit()
    return {"id": image_id, "status": "pending"}


# ============================================================ progreso

def progress(conn, project_id: int) -> dict:
    """Avance del curado: total / validated / rejected / pending + percent decidido."""
    rows = conn.execute(
        "SELECT status, COUNT(*) c FROM images WHERE project_id = ? GROUP BY status",
        (project_id,),
    ).fetchall()
    counts = {r["status"]: r["c"] for r in rows}
    validated = counts.get("validated", 0)
    rejected = counts.get("rejected", 0)
    pending = counts.get("pending", 0)
    total = validated + rejected + pending
    decided = validated + rejected
    percent = round(100 * decided / total, 1) if total else 0.0
    return {
        "total": total,
        "validated": validated,
        "rejected": rejected,
        "pending": pending,
        "percent": percent,
    }


# ============================================================ umbral de retrain (A3)

def threshold_status(conn, project_id: int) -> dict:
    """A3. Estado del umbral de re-entrenamiento del proyecto.

    Usa COALESCE(retrain_threshold, 10) para tolerar filas sin valor explicito.
    Devuelve {threshold, validated, remaining (max 0), reached (validated>=threshold)}.
    """
    row = conn.execute(
        "SELECT COALESCE(retrain_threshold, 10) AS threshold FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()
    if not row:
        raise DomainError("project_not_found", "Proyecto inexistente")
    threshold = row["threshold"]
    validated = conn.execute(
        "SELECT COUNT(*) c FROM images WHERE project_id = ? AND status = 'validated'",
        (project_id,),
    ).fetchone()["c"]
    remaining = max(0, threshold - validated)
    return {
        "threshold": threshold,
        "validated": validated,
        "remaining": remaining,
        "reached": validated >= threshold,
    }


# ============================================================ analytics

def concordance(conn, project_id: int) -> dict:
    """Tasa de acuerdo curador<->modelo: de las validadas del proyecto, cuantas
    terminaron con final_label == suggested_label. rate en [0,1]."""
    rows = conn.execute(
        "SELECT final_label, suggested_label FROM images "
        "WHERE project_id = ? AND status = 'validated'",
        (project_id,),
    ).fetchall()
    total = len(rows)
    agreed = sum(1 for r in rows if r["final_label"] == r["suggested_label"])
    rate = round(agreed / total, 4) if total else 0.0
    return {"agreed": agreed, "total_validated": total, "rate": rate}


def class_distribution(conn, project_id: int) -> list[dict]:
    """Distribucion de final_label sobre validadas (excluye rechazadas/pendientes).
    Lista [{label, count, percent}] ordenada por count DESC, luego label ASC."""
    rows = conn.execute(
        "SELECT final_label AS label, COUNT(*) AS count FROM images "
        "WHERE project_id = ? AND status = 'validated' AND final_label IS NOT NULL "
        "GROUP BY final_label ORDER BY count DESC, final_label ASC",
        (project_id,),
    ).fetchall()
    total = sum(r["count"] for r in rows)
    return [
        {
            "label": r["label"],
            "count": r["count"],
            "percent": round(100 * r["count"] / total, 1) if total else 0.0,
        }
        for r in rows
    ]


# ============================================================ calidad (B1)

def _validated_pairs(conn, project_id: int) -> list[tuple[str, str]]:
    """(suggested_label, final_label) de las imagenes validadas del proyecto."""
    rows = conn.execute(
        "SELECT suggested_label, final_label FROM images "
        "WHERE project_id = ? AND status = 'validated'",
        (project_id,),
    ).fetchall()
    return [(r["suggested_label"], r["final_label"]) for r in rows]


def conflicts(conn, project_id: int) -> list[dict]:
    """B1. Validadas donde el curador corrigio al modelo (final_label != suggested_label).

    Devuelve [{id, filename, path, suggested_label, final_label, confidence}].
    """
    rows = conn.execute(
        "SELECT id, filename, path, suggested_label, final_label, confidence FROM images "
        "WHERE project_id = ? AND status = 'validated' "
        "AND final_label IS NOT NULL AND final_label != suggested_label "
        "ORDER BY id ASC",
        (project_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "filename": r["filename"],
            "path": r["path"],
            "suggested_label": r["suggested_label"],
            "final_label": r["final_label"],
            "confidence": r["confidence"] if r["confidence"] is not None else 0.5,
        }
        for r in rows
    ]


def confusion_matrix(conn, project_id: int) -> dict:
    """B1. Matriz de confusion NxN sobre validadas: filas = suggested, columnas = final.

    labels = labels del proyecto (orden de definicion). Caso 0-validadas -> matriz de
    ceros (sin excepcion). Labels fuera del set se ignoran (guarda 'if lbl in labels').
    """
    labels = _project_labels(conn, project_id)
    index = {lbl: i for i, lbl in enumerate(labels)}
    matrix = [[0 for _ in labels] for _ in labels]
    for suggested, final in _validated_pairs(conn, project_id):
        if suggested in index and final in index:
            matrix[index[suggested]][index[final]] += 1
    return {"labels": labels, "matrix": matrix}


def quality_metrics(conn, project_id: int) -> dict:
    """B1. accuracy global + precision/recall por clase sobre validadas.

    final_label = ground truth, suggested_label = prediccion del modelo.
    precision = TP/(TP+FP), recall = TP/(TP+FN); div/0 -> 0.0. Caso 0-validadas ->
    accuracy 0.0 y per_class con 0.0 (sin excepcion). Labels fuera del set se ignoran.
    """
    labels = _project_labels(conn, project_id)
    valid = [
        (s, f) for (s, f) in _validated_pairs(conn, project_id) if s in labels and f in labels
    ]
    total = len(valid)
    agreed = sum(1 for s, f in valid if s == f)
    accuracy = round(agreed / total, 4) if total else 0.0

    per_class = []
    for lbl in labels:
        tp = sum(1 for s, f in valid if s == lbl and f == lbl)
        fp = sum(1 for s, f in valid if s == lbl and f != lbl)
        fn = sum(1 for s, f in valid if f == lbl and s != lbl)
        precision = round(tp / (tp + fp), 4) if (tp + fp) else 0.0
        recall = round(tp / (tp + fn), 4) if (tp + fn) else 0.0
        per_class.append({"label": lbl, "precision": precision, "recall": recall})

    return {"accuracy": accuracy, "per_class": per_class}


# ============================================================ export dataset (US-23)

def export_rows(conn, project_id: int) -> list[dict]:
    """US-23. Filas del dataset curado: SOLO validadas (no rechazadas, no pendientes).

    Cada fila trae filename, final_label, suggested_label, confidence y validated_at,
    ordenadas por validated_at para un export reproducible.
    """
    rows = conn.execute(
        "SELECT filename, final_label, suggested_label, confidence, validated_at "
        "FROM images WHERE project_id = ? AND status = 'validated' "
        "ORDER BY validated_at ASC, id ASC",
        (project_id,),
    ).fetchall()
    return [
        {
            "filename": r["filename"],
            "final_label": r["final_label"],
            "suggested_label": r["suggested_label"],
            "confidence": r["confidence"] if r["confidence"] is not None else 0.5,
            "validated_at": r["validated_at"],
        }
        for r in rows
    ]


def export_summary(conn, project_id: int) -> dict:
    """US-23. Resumen del export: total de validadas + conteo por clase (final_label).

    by_class es una lista [{label, count}] ordenada por count DESC, luego label ASC.
    """
    rows = conn.execute(
        "SELECT final_label AS label, COUNT(*) AS count FROM images "
        "WHERE project_id = ? AND status = 'validated' AND final_label IS NOT NULL "
        "GROUP BY final_label ORDER BY count DESC, final_label ASC",
        (project_id,),
    ).fetchall()
    by_class = [{"label": r["label"], "count": r["count"]} for r in rows]
    total = sum(c["count"] for c in by_class)
    return {"total": total, "by_class": by_class}


# ============================================================ ciclos AL (US-16)

def record_cycle(
    conn,
    project_id: int,
    images_used: int,
    avg_before: float,
    avg_after: float,
    improvement_pct: float,
    *,
    f1: float | None = None,
    auc: float | None = None,
) -> dict:
    """US-16. Registra un ciclo de Active Learning en al_cycles y lo devuelve como dict.

    Guarda cuantas imagenes se usaron y el promedio de confianza antes/despues
    junto con el porcentaje de mejora, para el historial de la pantalla analytics.

    A2: `f1`/`auc` keyword-only opcionales al final (default None). La llamada
    posicional historica sin f1/auc sigue funcionando sin cambios.
    """
    ts = _now()
    cur = conn.execute(
        "INSERT INTO al_cycles (project_id, created_at, images_used, "
        "avg_conf_before, avg_conf_after, improvement_pct, f1, auc) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (project_id, ts, images_used, avg_before, avg_after, improvement_pct, f1, auc),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM al_cycles WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row)


def list_cycles(conn, project_id: int) -> list[dict]:
    """US-16. Ciclos AL del proyecto en orden cronologico (mas antiguo primero)."""
    rows = conn.execute(
        "SELECT * FROM al_cycles WHERE project_id = ? ORDER BY created_at ASC, id ASC",
        (project_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# Piso de incertidumbre del retrain (D13): no subir pending por encima de 0.95,
# para preservar el orden del uncertainty sampling (wow #2).
_RETRAIN_CEILING = 0.95


def simulate_retrain(conn, project_id: int) -> dict:
    """Wow #3: simula un reentrenamiento. Acerca la confianza de cada imagen pending
    hacia 1.0 (cierra el 60% del gap restante) con piso/cap en 0.95, persiste, y
    reporta cuanto subio el promedio de confianza de las pending (D13).

    Cap del re-click: si improvement_pct < 0.5 o el promedio de pending ya supera 0.9,
    no aplica cambios y marca status='calibrado' (el modelo ya esta bien calibrado).
    Sin pending -> mejora 0 y status='calibrado'.
    """
    rows = conn.execute(
        "SELECT id, COALESCE(confidence, 0.5) AS confidence FROM images "
        "WHERE project_id = ? AND status = 'pending'",
        (project_id,),
    ).fetchall()
    if not rows:
        return {"improvement_pct": 0.0, "new_avg_confidence": 0.0, "status": "calibrado"}

    old_avg = sum(r["confidence"] for r in rows) / len(rows)

    # Si ya estan bien calibradas (promedio alto), no toca nada.
    if old_avg > 0.9:
        return {
            "improvement_pct": 0.0,
            "new_avg_confidence": round(old_avg, 4),
            "status": "calibrado",
        }

    boosted = []
    for r in rows:
        c = r["confidence"]
        nc = round(min(c + (1.0 - c) * 0.6, _RETRAIN_CEILING), 4)
        boosted.append((r["id"], nc))

    new_avg = sum(nc for _, nc in boosted) / len(boosted)
    improvement = round(100 * (new_avg - old_avg) / old_avg, 1) if old_avg else 0.0

    if improvement < 0.5:
        return {
            "improvement_pct": 0.0,
            "new_avg_confidence": round(old_avg, 4),
            "status": "calibrado",
        }

    for iid, nc in boosted:
        conn.execute("UPDATE images SET confidence = ? WHERE id = ?", (nc, iid))
    conn.commit()

    # A2: F1/AUC mockeados crecientes por numero de ciclo (1-based).
    n = len(list_cycles(conn, project_id)) + 1
    f1 = round(min(0.82 + 0.04 * n, 0.97), 3)
    auc = round(min(0.85 + 0.035 * n, 0.98), 3)

    # US-16: registra el ciclo AL con los valores ya calculados.
    record_cycle(
        conn,
        project_id,
        len(boosted),
        round(old_avg, 4),
        round(new_avg, 4),
        improvement,
        f1=f1,
        auc=auc,
    )

    # Pub-Sub (A.7): cierre del ciclo de Active Learning. Aditivo: no cambia el
    # retorno (solo se publica en el path 'ok', tras registrar el ciclo).
    events.bus.publish(
        events.CICLO_FINALIZO,
        {"conn": conn, "project_id": project_id, "improvement_pct": improvement},
    )

    return {
        "improvement_pct": improvement,
        "new_avg_confidence": round(new_avg, 4),
        "status": "ok",
    }


# Estimacion de tiempo por imagen (D12): mock realista cuando no hay timestamps.
_AL_SECONDS_PER_IMAGE = 3.0     # curado asistido por AL
_MANUAL_SECONDS_PER_IMAGE = 30.0  # etiquetado manual sin asistencia


def time_saved(conn, project_id: int) -> dict:
    """Estima el tiempo ahorrado por el curado asistido (ROI, D12).

    Si las imagenes decididas tienen shown_at + validated_at, usa el tiempo real;
    si no, cae a un mock (~3s con AL vs ~30s manual). Devuelve segundos AL/manual,
    ahorro absoluto, porcentaje y minutos ahorrados.
    """
    rows = conn.execute(
        "SELECT shown_at, validated_at FROM images "
        "WHERE project_id = ? AND status IN ('validated', 'rejected')",
        (project_id,),
    ).fetchall()
    decided = len(rows)
    if decided == 0:
        return {
            "decided": 0,
            "al_seconds": 0.0,
            "manual_seconds": 0.0,
            "saved_seconds": 0.0,
            "saved_minutes": 0.0,
            "saved_pct": 0.0,
        }

    al_seconds = 0.0
    for r in rows:
        real = _elapsed_seconds(r["shown_at"], r["validated_at"])
        al_seconds += real if real is not None else _AL_SECONDS_PER_IMAGE
    manual_seconds = decided * _MANUAL_SECONDS_PER_IMAGE
    saved_seconds = max(manual_seconds - al_seconds, 0.0)
    saved_pct = round(100 * saved_seconds / manual_seconds, 1) if manual_seconds else 0.0
    return {
        "decided": decided,
        "al_seconds": round(al_seconds, 1),
        "manual_seconds": round(manual_seconds, 1),
        "saved_seconds": round(saved_seconds, 1),
        "saved_minutes": round(saved_seconds / 60.0, 1),
        "saved_pct": saved_pct,
    }


def ab_summary(conn, project_id: int) -> dict:
    """B2. Resumen A/B (manual vs PACUSAM-AL) para la tabla comparativa.

    Reusa time_saved (al_seconds/manual_seconds/saved_pct) + throughput en img/hora
    (3s/img con AL, 30s/img manual) + concordance. Caso 0-decididas -> neutro.
    """
    ts = time_saved(conn, project_id)
    conc = concordance(conn, project_id)
    throughput_al = round(3600.0 / _AL_SECONDS_PER_IMAGE, 1)  # img/hora con AL
    throughput_manual = round(3600.0 / _MANUAL_SECONDS_PER_IMAGE, 1)  # img/hora manual
    return {
        "decided": ts["decided"],
        "al_seconds": ts["al_seconds"],
        "manual_seconds": ts["manual_seconds"],
        "saved_seconds": ts["saved_seconds"],
        "saved_minutes": ts["saved_minutes"],
        "saved_pct": ts["saved_pct"],
        "throughput_al": throughput_al,
        "throughput_manual": throughput_manual,
        "concordance": conc["rate"],
    }


def dataset_health(conn, project_id: int) -> dict:
    """B2. Salud/balance del dataset validado, con umbral RELATIVO al numero de clases.

    ideal = 100 / n_clases. status: verde si min_pct >= ideal*0.8, amarillo si >=
    ideal*0.5, rojo si menos. Considera todas las labels del proyecto (una clase sin
    validadas cuenta como 0%). Caso 0-validadas -> status 'sin datos', minority None.
    """
    labels = _project_labels(conn, project_id)
    dist = {d["label"]: d for d in class_distribution(conn, project_id)}
    total = sum(d["count"] for d in dist.values())
    n = len(labels)
    if total == 0 or n == 0:
        return {
            "status": "sin datos",
            "minority": None,
            "ideal_pct": round(100.0 / n, 1) if n else 0.0,
            "message": "Sin validaciones aun: la salud del dataset se calcula al curar.",
        }

    # Cada label del proyecto, con 0% si no tiene validadas.
    per_label = []
    for lbl in labels:
        count = dist[lbl]["count"] if lbl in dist else 0
        per_label.append({"label": lbl, "count": count, "percent": round(100 * count / total, 1)})

    minority = min(per_label, key=lambda d: d["percent"])
    min_pct = minority["percent"]
    ideal = 100.0 / n
    if min_pct >= ideal * 0.8:
        status = "verde"
        message = "Dataset balanceado: todas las clases bien representadas."
    elif min_pct >= ideal * 0.5:
        status = "amarillo"
        message = (
            f"Desbalance moderado: la clase '{minority['label']}' "
            f"esta en {min_pct}% (ideal {round(ideal, 1)}%)."
        )
    else:
        status = "rojo"
        message = (
            f"Desbalance fuerte: la clase '{minority['label']}' "
            f"esta en {min_pct}% (ideal {round(ideal, 1)}%)."
        )
    return {
        "status": status,
        "minority": {"label": minority["label"], "percent": min_pct},
        "ideal_pct": round(ideal, 1),
        "distribution": per_label,
        "message": message,
    }


def _elapsed_seconds(shown_at, validated_at) -> float | None:
    """Segundos entre shown_at y validated_at (ISO 8601), o None si falta alguno."""
    if not shown_at or not validated_at:
        return None
    try:
        t0 = datetime.fromisoformat(shown_at)
        t1 = datetime.fromisoformat(validated_at)
    except (ValueError, TypeError):
        return None
    delta = (t1 - t0).total_seconds()
    return delta if delta >= 0 else None


# ============================================================ log de actividad (D2)

def log_activity(
    conn,
    user_id: int,
    action: str,
    image_id: int | None = None,
    project_id: int | None = None,
) -> dict:
    """D2/US-28. Registra una entrada de actividad con timestamp y la devuelve.

    image_id/project_id opcionales (acciones como create_project no tienen imagen).
    """
    ts = _now()
    cur = conn.execute(
        "INSERT INTO activity_log (user_id, action, image_id, project_id, created_at) "
        "VALUES (?,?,?,?,?)",
        (user_id, action, image_id, project_id, ts),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM activity_log WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return dict(row)


def list_activity(
    conn,
    user_id: int | None = None,
    action: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """D2/US-28. Lista la actividad mas reciente primero, filtrable por usuario/accion.

    Desempata por id DESC para que el orden sea estable aun con timestamps iguales.
    """
    sql = "SELECT * FROM activity_log WHERE 1=1 "
    params: list = []
    if user_id is not None:
        sql += "AND user_id = ? "
        params.append(user_id)
    if action is not None:
        sql += "AND action = ? "
        params.append(action)
    sql += "ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, tuple(params)).fetchall()
    return [dict(r) for r in rows]
