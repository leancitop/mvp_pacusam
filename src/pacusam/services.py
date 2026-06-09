"""Capa de dominio. Lógica del curado (US-10) sobre una conexión SQLite.

No conoce HTTP: la capa `api` la envuelve. Errores de negocio via DomainError(code).
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import classifier


class DomainError(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_images(conn, filenames: list[str]) -> int:
    """Carga imágenes mockeadas. Cada una pasa por el STUB del clasificador
    (sustituye a US-15/M3): recibe etiqueta sugerida + score de confianza."""
    for fn in filenames:
        label, conf = classifier.suggest(fn)
        conn.execute(
            "INSERT INTO images (filename, suggested_label, confidence, status) "
            "VALUES (?,?,?, 'pending')",
            (fn, label, conf),
        )
    conn.commit()
    return len(filenames)


def next_pending(conn) -> dict | None:
    """Próxima imagen pendiente con su sugerencia + confianza, y cuántas quedan."""
    row = conn.execute(
        "SELECT * FROM images WHERE status = 'pending' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        return None
    remaining = conn.execute(
        "SELECT COUNT(*) c FROM images WHERE status = 'pending'"
    ).fetchone()["c"]
    return {
        "id": row["id"],
        "filename": row["filename"],
        "suggested_label": row["suggested_label"],
        "confidence": row["confidence"],
        "remaining_pending": remaining,
    }


def validate_image(conn, image_id: int, label: str) -> dict:
    """US-10. Confirma o cambia la etiqueta sugerida; registra timestamp."""
    row = conn.execute("SELECT 1 FROM images WHERE id = ?", (image_id,)).fetchone()
    if not row:
        raise DomainError("image_not_found", "Imagen inexistente")
    if not (label or "").strip():
        raise DomainError("label_required", "La etiqueta es obligatoria")
    ts = _now()
    conn.execute(
        "UPDATE images SET status='validated', final_label=?, validated_at=? WHERE id=?",
        (label, ts, image_id),
    )
    conn.commit()
    return {"id": image_id, "status": "validated", "final_label": label, "validated_at": ts}


def progress(conn) -> dict:
    """Total / etiquetadas / pendientes + porcentaje."""
    rows = conn.execute(
        "SELECT status, COUNT(*) c FROM images GROUP BY status"
    ).fetchall()
    counts = {r["status"]: r["c"] for r in rows}
    total = sum(counts.values())
    labeled = counts.get("validated", 0)
    pending = counts.get("pending", 0)
    pct = round(100 * labeled / total, 1) if total else 0.0
    return {"total": total, "labeled": labeled, "pending": pending, "percent": pct}
