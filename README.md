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

### Funciones avanzadas (inspiradas en Kaapana / MONAI Label / CVAT / OHIF)

- **🧠 Rigor de Active Learning:** selector de estrategia de sampling (Uncertainty / Random / Secuencial), score de incertidumbre por imagen, **curva F1/AUC ascendente por ciclo**, y contador hacia el **umbral de re-entrenamiento**.
- **📊 Calidad y A/B:** **matriz de confusión**, precisión/recall por clase, **comparativa A/B** (curado asistido vs etiquetado manual), **salud del dataset** (semáforo de balance de clases) y lista de **conflictos** modelo↔humano.
- **🩺 Sello clínico-pro:** **visor estilo OHIF** sobre la imagen (zoom/pan/invertir/reset por teclado `=` `-` `0` `i`), **aprobado en lote** ("aprobar pendientes con confianza >90%"), metadata clínica.
- **🔐 Administración y trazabilidad:** **roles** (curador / admin), **log de actividad** de la plataforma, y vista de administración protegida por rol.

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

| rol | email | password |
|-----|-------|----------|
| curador | `demo@pacusam.org` | `demo1234` |
| administrador | `admin@pacusam.org` | `admin1234` |

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

252 tests: unitarios de dominio/auth + endpoints + integración + BDD en español (criterios de aceptación project-scoped) + estilos arquitectónicos (event bus, eventos de dominio, feedback loop, pipeline) + calidad ISO 25010 (password server-side, /health + performance, cobertura de docstrings >= 80%).

## Arquitectura

Capas: **`api`** (FastAPI, rutas + sesión) → **`services`** (dominio, no conoce HTTP) → **`db`** (SQLite). UI server-side con Jinja2 + HTMX (sin SPA).

**Estilos arquitectónicos materializados** (del white paper, A.7):

- **Layered:** `api` → `services` → `db`; el dominio no conoce HTTP.
- **Pub-Sub** (`events.py`): bus síncrono in-process. `services` publica 4 eventos canónicos (`ImagenesSubidas`, `ImagenValidada`, `UmbralAlcanzado`, `CicloFinalizo`); los suscriptores (feedback loop de re-entrenamiento) se registran solo en `create_app`. Entrega best-effort.
- **Event Processing:** **SEP** (cada validación es una acción uno-a-uno), **OEP** (el score se ve al instante y la cola se reordena por incertidumbre tras cada acción) y **CEP** (`UmbralAlcanzado` es un evento derivado de N validadas que dispara el re-entrenamiento automático).
- **Pipes & Filters** (`pipeline.py`): la ingesta corre filtros encadenados puros `[filtro_validar_formato, filtro_clasificar]`; se agregan filtros (decode/anonimizar/almacenar) con la ingesta real sin reescribir el flujo.

Trazabilidad completa de cada decisión (white paper / actividad del curso / riesgo / estado) en [`docs/trazabilidad.md`](docs/trazabilidad.md); atributos de calidad ISO/IEC 25010 en [`docs/arquitectura.md`](docs/arquitectura.md).

```
src/pacusam/
  db.py          SQLite (users / projects / images), WAL + busy_timeout
  classifier.py  stub del motor de AL (confianza mock, determinista)
  auth.py        hashing pbkdf2 + create_user / authenticate (password server-side)
  services.py    dominio: proyectos, cola por incertidumbre, validar/rechazar, métricas; publica eventos
  events.py      bus Pub-Sub in-process (4 eventos canónicos, SEP/OEP/CEP)
  pipeline.py    ingesta como Pipes & Filters (filtros encadenados puros)
  seed.py        siembra determinista (usuario demo + 2 proyectos + imágenes reales)
  api.py         rutas FastAPI, sesión, autorización por dueño, /health, suscriptores del feedback loop
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

## Cobertura de user stories

**Hechas en el MVP:** US-01/02/03 (auth), US-04/05/06/08 (home/proyectos), US-09/10/11 (curado + navegación), US-12 (rechazo + motivo reversible), US-14 (pre-clasificación), US-16 (historial de ciclos + F1/AUC), US-17 (filtro por etiqueta), US-19 (concordancia), US-20 (tiempo de validación / ahorro), US-21 (resumen ejecutivo), US-22 (distribución de clases), US-23 (export CSV/JSON), US-26/27 (roles, vista admin), US-28 (log de actividad). El motor de AL (US-13/15) está **mockeado de forma honesta** (uncertainty sampling y métricas reales; el entrenamiento es simulado).

**Roadmap (no implementado — señal de visión, no de alcance):**
- **Subida real de imágenes + DICOM** (US-07): hoy las imágenes vienen pre-sembradas.
- **Motor de AL real** (US-13/15): clasificador entrenable con parámetros configurables. Hoy es un stub + uncertainty sampling real.
- **Búsqueda** por id/nombre en una galería dedicada (US-18) y **filtros de export** (US-24): el backend ya existe (`gallery`, `bulk_validate`); falta la pantalla.
- **Reportes PDF** del proyecto (US-25).
- **Cambio de rol en vivo** desde la vista admin (hoy read-only).

## Limitaciones conocidas (decisiones conscientes de MVP)

- **Single-user en concurrencia alta**: una conexión SQLite compartida (WAL + `busy_timeout` como red de seguridad). Suficiente para el demo; no para producción multiusuario.
- **Motor de AL mockeado**: las sugerencias y el "re-entrenamiento" son simulados (el *uncertainty sampling* sí es real).

---

Documentos de diseño: `docs/superpowers/specs/` (spec) y `docs/superpowers/plans/` (plan + review).
