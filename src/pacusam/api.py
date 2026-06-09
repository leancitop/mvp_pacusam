"""Capa de presentación. FastAPI sobre la capa de dominio. Sin auth en la iteración 1."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import db, services

_STATIC = Path(__file__).parent / "static"

_STATUS = {"image_not_found": 404, "label_required": 422}

# Dataset semilla por defecto (nombres mockeados) para que el demo tenga datos al abrir.
_DEFAULT_SEED = [
    "rx_torax_0001.dcm",
    "rx_torax_0002.dcm",
    "rx_torax_0003.png",
    "tc_cerebro_0001.dcm",
    "tc_cerebro_0002.jpg",
]


class SeedIn(BaseModel):
    filenames: list[str]


class ValidateIn(BaseModel):
    label: str


def create_app(db_path: str | None = None, seed: bool = False) -> FastAPI:
    db_path = db_path or os.environ.get("PACUSAM_DB", ":memory:")
    conn = db.connect(db_path)
    app = FastAPI(title="PACUSAM MVP", version="0.1.0")
    app.state.conn = conn

    # Siembra inicial para el demo desplegado (no en tests, que controlan sus propios datos).
    if seed and services.progress(conn)["total"] == 0:
        services.seed_images(conn, _DEFAULT_SEED)

    def get_conn():
        return app.state.conn

    @app.get("/", include_in_schema=False)
    def root():
        return FileResponse(_STATIC / "index.html")

    def _guard(fn, *args):
        try:
            return fn(*args)
        except services.DomainError as e:
            raise HTTPException(status_code=_STATUS.get(e.code, 400), detail=e.code)

    @app.post("/seed", status_code=201)
    def seed(body: SeedIn, conn=Depends(get_conn)):
        return {"seeded": services.seed_images(conn, body.filenames)}

    @app.get("/next")
    def next_image(conn=Depends(get_conn)):
        img = services.next_pending(conn)
        if img is None:
            raise HTTPException(status_code=404, detail="no_pending_images")
        return img

    @app.post("/images/{image_id}/validate")
    def validate(image_id: int, body: ValidateIn, conn=Depends(get_conn)):
        return _guard(services.validate_image, conn, image_id, body.label)

    @app.get("/progress")
    def get_progress(conn=Depends(get_conn)):
        return services.progress(conn)

    return app


app = create_app(seed=True)
