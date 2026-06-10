"""STUB del motor de Active Learning (componente `active_learning`).

Pre-clasificador mockeado y determinista: dado un nombre de archivo y las labels
del proyecto, devuelve una etiqueta sugerida + score de confianza realista.
Determinista a proposito (deriva de un hash del filename) para tests reproducibles.
El modelo REAL (US-15/M3) reemplaza este modulo sin tocar el resto del sistema.
"""
from __future__ import annotations

import hashlib


def suggest(filename: str, labels: list[str]) -> tuple[str, float]:
    """Etiqueta sugerida (in labels) + confianza en [0.50, 0.99].

    Determinista por filename. La confianza se distribuye en todo el rango para
    que haya MEZCLA de altas (>0.9) y bajas (<0.6) — combustible del uncertainty
    sampling de services.queue_next.
    """
    if not labels:
        raise ValueError("labels no puede estar vacio")
    h = int(hashlib.sha256(filename.encode()).hexdigest(), 16)
    label = labels[h % len(labels)]
    # Segundo hash independiente para la confianza, asi no correlaciona con la label.
    hc = int(hashlib.sha256((filename + "#conf").encode()).hexdigest(), 16)
    confidence = round(0.50 + (hc % 50) / 100.0, 2)  # 0.50..0.99
    return label, confidence
