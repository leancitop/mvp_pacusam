"""STUB del motor de Active Learning (componente `active_learning`).

El pre-clasificador REAL es M3 (US-15), fuera del MVP. Acá hay un stub determinista:
dado un nombre de archivo devuelve una etiqueta sugerida + score de confianza.
Determinista a propósito (deriva de un hash del filename) para que los tests BDD
sean reproducibles. US-15 reemplaza este módulo sin tocar el resto del sistema
(es el beneficio de Pipes & Filters / Pub-Sub documentado en la arquitectura).
"""
from __future__ import annotations

import hashlib

LABELS = ["normal", "anomalia"]


def suggest(filename: str) -> tuple[str, float]:
    """Etiqueta sugerida + confianza en [0.50, 0.99]. Determinista por filename."""
    h = int(hashlib.sha256(filename.encode()).hexdigest(), 16)
    label = LABELS[h % len(LABELS)]
    confidence = round(0.50 + (h % 50) / 100.0, 2)  # 0.50..0.99
    return label, confidence
