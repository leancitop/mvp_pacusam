# PACUSAM — MVP

**PlAtaforma de CUrado de imágenes médicas de la UNSAM.** Validación asistida de imágenes médicas con *Active Learning*. TPFI, Grupo 9, Ingeniería de Software (LCD-UNSAM).

> El modelo pre-clasifica cada imagen con un nivel de confianza; el curador **valida, corrige o rechaza** la sugerencia. El sistema prioriza las imágenes donde el modelo más duda (*uncertainty sampling*): se etiquetan pocas imágenes con máximo impacto.

## El problema

Los investigadores del CIMeT dedican ~80% del tiempo a etiquetar imágenes a mano. PACUSAM convierte ese etiquetado manual en **validación asistida**: el modelo propone, la persona valida.

## Qué muestra este MVP (los 3 "wow moments")

1. **🩻 Curado tipo "Tinder clínico"** — imagen médica real grande, etiqueta sugerida + barra de confianza, acciones por teclado (`A` aprobar / `C` corregir / `R` rechazar) con auto-avance.
2. **🧠 Active Learning por *uncertainty sampling*** — la cola de curado se reordena sola: arriba las imágenes de menor confianza. *"Etiquetaste 8 de 200 — pero son las 8 que más le enseñan al modelo."*
3. **📊 Analytics** — tasa de concordancia modelo↔humano, distribución de clases, y un badge de **tiempo ahorrado** (~-80% vs etiquetado manual).

Más: registro/login/logout reales, home con proyectos, rechazo con motivo (reversible), y un botón "re-entrenar" que simula un ciclo de Active Learning.

## Stack

Python 3.10+ · **FastAPI** · **Jinja2 + HTMX + Alpine.js + Tailwind** (servidos local, sin build/npm) · **SQLite** (stdlib) · auth con `hashlib.pbkdf2_hmac` (sin dependencias C) · `pytest` + `pytest-bdd`.

## Cómo levantarlo (local)

```bash
# 1) Crear entorno e instalar dependencias
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements-dev.txt

# 2) Levantar la app (siembra sola 2 proyectos con imágenes reales al arrancar)
PYTHONPATH=src PACUSAM_DB=pacusam.db ./.venv/bin/python -m uvicorn pacusam.api:app --reload
```

Abrir **http://127.0.0.1:8000**

**Credenciales demo** (sembradas automáticamente):

| email | password |
|-------|----------|
| `demo@pacusam.org` | `demo1234` |

También podés **registrar** una cuenta nueva desde `/register` (arranca sin proyectos → muestra el empty-state).

> La DB SQLite se crea sola (`pacusam.db`) y se **re-siembra** si está vacía, así el demo siempre arranca con datos. Para empezar de cero: borrá `pacusam.db`.

## El recorrido del demo (sugerido)

1. **Login** con `demo@pacusam.org` / `demo1234`.
2. **Home**: dos proyectos con imágenes reales — *Radiografías de tórax* (NORMAL/PNEUMONIA) y *Células sanguíneas* (multiclase) — con barra de progreso.
3. Entrar a un proyecto → **"Empezar a curar"**.
4. **Curar** 3-4 imágenes con el teclado (`A`/`C`/`R`) mostrando el auto-avance.
5. Señalar el **filmstrip**: el sistema puso adelante las imágenes que más dudaba — *"etiquetás 8 de 200 pero son las 8 que más le enseñan al modelo"*.
6. **Re-entrenar** (toast con la mejora de confianza) y abrir **Analytics**: concordancia, distribución de clases y el badge de tiempo ahorrado.

## Tests

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

124 tests: unitarios de dominio/auth + endpoints + integración + BDD en español (criterios de aceptación project-scoped).

## Arquitectura

Capas: **`api`** (FastAPI, rutas + sesión) → **`services`** (dominio, no conoce HTTP) → **`db`** (SQLite). UI server-side con Jinja2 + HTMX (sin SPA).

```
src/pacusam/
  db.py          SQLite (users / projects / images), WAL + busy_timeout
  classifier.py  stub del motor de AL (confianza mock, determinista)
  auth.py        hashing pbkdf2 + create_user / authenticate
  services.py    dominio: proyectos, cola por incertidumbre, validar/rechazar, métricas
  seed.py        siembra determinista (usuario demo + 2 proyectos + imágenes reales)
  api.py         rutas FastAPI, sesión, autorización por dueño
  templating.py  helper de render Jinja2
  templates/     base + login/register/home/project/curate/analytics + partials
  static/        vendor/ (HTMX/Alpine/Tailwind/Lucide local) · datasets/{1,2}/ (imágenes reales)
```

**Active Learning (mock honesto):** el clasificador es un *stub* (no hay ML real), pero el **uncertainty sampling es real**: la cola se ordena por `1 − confianza`. La concordancia y la distribución de clases se calculan de verdad sobre la DB. El "re-entrenar" simula un ciclo (sube la confianza de las pendientes con un tope, reporta la mejora).

## Datasets

Imágenes reales públicas, versionadas en el repo (demo 100% offline):
- **Tórax** (`static/datasets/1/`): radiografías públicas (repo `ieee8023/covid-chestxray-dataset`).
- **Células** (`static/datasets/2/`): BCCD (MIT).

## Deploy (Render)

`render.yaml` está listo (Blueprint). Setea `PACUSAM_SECURE_COOKIES=1`, `PACUSAM_SECRET` (generado) y `PACUSAM_DB`. El plan free de Render resetea el disco, pero el **re-seed determinista** al arrancar regenera los datos del demo.

## Roadmap (no implementado en este MVP — señal de visión, no de alcance)

- **Subida real de imágenes + DICOM** (US-07): hoy las imágenes vienen pre-sembradas.
- **Motor de AL real** (US-13/15/16): clasificador entrenable, parámetros configurables, historial de ciclos. Hoy es un stub + uncertainty sampling real.
- **Filtro y búsqueda** de imágenes (US-17/18).
- **Exportación de dataset** CSV/JSON + reportes PDF (US-23/24/25).
- **Administración**: gestión de usuarios, roles/permisos, log de actividad (US-26/27/28).

## Limitaciones conocidas (decisiones conscientes de MVP)

- **Single-user en concurrencia alta**: una conexión SQLite compartida (WAL + `busy_timeout` como red de seguridad). Suficiente para el demo; no para producción multiusuario.
- **Motor de AL mockeado**: las sugerencias y el "re-entrenamiento" son simulados (el *uncertainty sampling* sí es real).
- **Validación de password solo client-side** (`minlength`): falta regla server-side.

---

Documentos de diseño: `docs/superpowers/specs/` (spec) y `docs/superpowers/plans/` (plan + review).
