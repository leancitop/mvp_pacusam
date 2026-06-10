"""Event bus in-process (estilo Publish-Subscribe del white paper, A.7).

Materializa el estilo Pub-Sub SIN infraestructura (sin Celery/Redis): un bus
sincrono en memoria. El backend publica los 4 eventos canonicos del dominio y
los suscriptores (registrados en create_app) reaccionan. La entrega es
best-effort: un handler que falla no corta a los demas ni propaga al publisher.

Clasificacion de Event Processing (A.7):
- SEP (Single Event Processing): cada accion de curado emite un unico evento de
  dominio uno-a-uno (`ImagenValidada` por cada POST /validate|reject).
- OEP (Online Event Processing): el score de confianza se actualiza al instante
  y la cola se reordena por incertidumbre tras cada accion (`queue_next`).
- CEP (Complex Event Processing): `UmbralAlcanzado` es un evento DERIVADO de N
  `ImagenValidada` acumuladas (al cruzar el umbral), que dispara el ciclo de
  re-entrenamiento (feedback loop).
"""
from __future__ import annotations

from typing import Any, Callable

# Eventos canonicos del white paper (A.7 Estilos Arquitectonicos).
IMAGENES_SUBIDAS = "ImagenesSubidas"
IMAGEN_VALIDADA = "ImagenValidada"
UMBRAL_ALCANZADO = "UmbralAlcanzado"
CICLO_FINALIZO = "CicloFinalizo"

Handler = Callable[[dict[str, Any]], None]


class EventBus:
    """Bus de publish-subscribe sincrono en memoria (dict evento -> handlers)."""

    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = {}

    def subscribe(self, event: str, handler: Handler) -> None:
        """Registra un handler para un evento (se acumulan en orden de suscripcion)."""
        self._subs.setdefault(event, []).append(handler)

    def publish(self, event: str, payload: dict[str, Any]) -> None:
        """Entrega el payload a cada suscriptor del evento (best-effort)."""
        for handler in list(self._subs.get(event, [])):
            try:
                handler(payload)
            except Exception:
                # Best-effort: un suscriptor que falla no afecta al publisher
                # ni a los demas suscriptores.
                pass

    def clear(self) -> None:
        """Elimina todas las suscripciones (usado al re-wirear eventos en create_app)."""
        self._subs.clear()


# Bus global del proceso. services.py publica aca; create_app suscribe.
bus = EventBus()
