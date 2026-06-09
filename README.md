# mvp_pacusam

MVP de **PACUSAM** (*PlAtaforma de CUrado de imágenes médicas de la unSAM*). Validación asistida de imágenes médicas con *Active Learning*. TPFI, Grupo 9, Ingeniería de Software (LCD-UNSAM).

## Problema

Los investigadores del CIMeT dedican ~80% del tiempo a etiquetar imágenes manualmente. PACUSAM transforma ese etiquetado manual en **validación asistida**: el modelo propone, la persona valida.

## Alcance de esta iteración

Una sola US end-to-end: **US-10, validar imágenes pre-clasificadas** (+ un poco de US-09 ). Sobre dataset semilla mockeado y pre-clasificador *stub*. Sin auth ni proyectos todavía: llegan en próximas iteraciones.

Flujo: `seed de imágenes → el stub sugiere etiqueta+confianza → el curador valida → progreso`.

## Stack

Python 3.10+,  FastAPI,  SQLite,  pytest-bdd.

## Estructura

```
src/pacusam/
  db.py          datos: SQLite, tabla images
  classifier.py  STUB del motor de Active Learning (US-15/M3, fuera del MVP)
  services.py    dominio: seed / next / validate / progress (US-10, US-09)
  api.py         presentación: rutas FastAPI
tests/
  features/curado.feature   criterios de aceptación en Gherkin
  conftest.py               fixtures + step definitions
```

## Cómo correr

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Linux/Mac: .venv/bin/python
.venv/Scripts/python -m pytest -q                             # tests de aceptación (BDD)
PYTHONPATH=src .venv/Scripts/python -m uvicorn pacusam.api:app --reload   # API + /docs
```

## Metodología

BDD: el `.feature` es el criterio de aceptación de US-10 traducido a Gherkin y corre contra la API real. Es además insumo del **Plan de Pruebas de Software** (entregable pendiente del TP). Ver `wiki/tp/entregables/plan-mvp.md`.
