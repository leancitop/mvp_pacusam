"""Ingesta como Pipes & Filters (white paper, A.7): filtros puros encadenados.

Cada filtro es f(ctx)->ctx. El runner los aplica en orden. Hoy la ingesta usa
[validar_formato, clasificar]; cuando llegue la ingesta real (US-07/M3) se
agregan filtros decode/anonimizar/almacenar SIN reescribir el flujo.
"""
from __future__ import annotations

from typing import Any, Callable

from pacusam import classifier

Ctx = dict[str, Any]
Filtro = Callable[[Ctx], Ctx]

_FORMATOS_OK = (".jpg", ".jpeg", ".png", ".dcm", ".dicom")


def run_pipeline(filtros: list[Filtro], ctx: Ctx) -> Ctx:
    """Aplica los filtros en orden sobre el contexto (Pipes & Filters)."""
    for f in filtros:
        ctx = f(ctx)
    return ctx


def filtro_validar_formato(ctx: Ctx) -> Ctx:
    """Filtro: marca si el formato del archivo es soportado (JPG/PNG/DICOM)."""
    fn = ctx.get("filename", "").lower()
    ctx["formato_ok"] = fn.endswith(_FORMATOS_OK)
    return ctx


def filtro_clasificar(ctx: Ctx) -> Ctx:
    """Filtro: pre-clasificacion (stub de AL) que asigna label + confianza."""
    label, conf = classifier.suggest(ctx["filename"], ctx["labels"])
    ctx["suggested_label"] = label
    ctx["confidence"] = conf
    return ctx


# Pipeline de ingesta actual (M2): validar formato -> clasificar.
INGESTA = [filtro_validar_formato, filtro_clasificar]
