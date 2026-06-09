# PACUSAM MVP "wow" — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transformar el walking-skeleton de Leandro en un MVP que deslumbra: auth real, home con 2 proyectos de imágenes médicas reales, pantalla de curado "Tinder clínico", Active Learning por uncertainty sampling (mock convincente), y analytics — todo con UI minimalista limpia.

**Architecture:** Se extiende el código en capas existente (api -> services -> db) de FastAPI. UI server-side con Jinja2 + HTMX + Alpine + Tailwind (CDN, sin build). SQLite a archivo con re-seed determinista. El motor de AL es mock (confianzas pre-generadas) pero el uncertainty sampling es real.

**Tech Stack:** Python 3.10+, FastAPI, Jinja2, HTMX, Alpine.js, Tailwind CSS (CDN), SQLite (stdlib), passlib[bcrypt], Starlette SessionMiddleware, pytest + pytest-bdd.

**Spec:** `docs/superpowers/specs/2026-06-08-pacusam-mvp-wow-design.md`

**Orden de ejecución de tracks (respetar dependencias):** A (fundación/datos) -> B (design system/base template) -> C (auth) -> D (proyectos) -> E (curado) -> F (AL + analytics). C/D/E/F dependen de A y B.

---



## 🔧 Decisiones de integración (CANÓNICAS — OVERRIDE cualquier track en conflicto)

Los 6 tracks se redactaron en paralelo y chocan en la capa API/UI. Estas decisiones mandan; donde un track diga otra cosa, gana esto.

1. **`db.py` lo escribe SOLO el Track A.** El SCHEMA canónico (users/projects/images + índice único `ux_images_project_filename`) vive en Track A. El step de Track C que reescribe SCHEMA se **SALTEA** (la tabla `users` ya está en A). Track C solo aporta `auth.py`.
2. **Dependencias editadas UNA sola vez (unión):** `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart` (Form), `itsdangerous` (SessionMiddleware), `passlib[bcrypt]`. En `.gitignore` agregar excepción para versionar `src/pacusam/static/datasets/**` (no debe quedar ignorado). Usar el set de Track A (el más completo).
3. **Una sola instancia de Jinja2Templates:** `templating.templates` con helper `templating.render(request, name, **ctx)` (Track B). Todos renderizan vía `templating.render(...)`. Borrar cualquier `Jinja2Templates(...)` local o `_TEMPLATES` de C/D.
4. **`require_user` (Track C):** dependency que **lanza** `_RedirectException` (capturada por un exception handler que devuelve `RedirectResponse('/login', 303)`). Las rutas protegidas usan `user = Depends(require_user)`. Track D **NO** usa `isinstance(user, RedirectResponse)`.
5. **Orden de ensamblaje de `create_app` (un solo `api.py`):**
   1. crear app; `app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")`; `SessionMiddleware(secret_key=os.environ.get("PACUSAM_SECRET","dev-secret"))`; Jinja vía `templating`.
   2. exception handler de `_RedirectException` + `_guard`/`_STATUS`.
   3. rutas auth (C).
   4. rutas proyectos (D): `GET /`, `GET /projects/{id}`, `POST /projects`.
   5. rutas curado (E).
   6. rutas AL + analytics (F).
   7. al final, antes de `return app`: `seed.seed_if_empty(conn)` (re-seed cuando `projects` está vacío).
6. **`POST /projects` redirige a `/projects/{id}`** (303 con `Location: /projects/<id>`). El test de Track D que espera `/` se **actualiza** a `/projects/{id}`.
7. **`_STATUS` mergeado (una sola def en `api.py`):** `{image_not_found:404, project_not_found:404, no_pending_images:404, label_required:422, invalid_label:422, reason_required:422, name_required:422, name_too_long:422, email_exists:409}`. Las rutas auth (`/register`,`/login`) NO pasan por `_guard`: renderizan el form con mensaje de error y status 400/401.
8. **Partials de flash/progreso/confianza — fuente única = macros de Track B** en `partials/ui.html`: `flash(kind, message)`, `progress_bar(progress)`, `confidence_bar(confidence)`. Todos importan `{% from "partials/ui.html" import flash, progress_bar, confidence_bar %}`. Borrar `flash.html` y variantes hex inline de C/E/F.
9. **`base.html` — fuente única = Track B**, con su convención de tokens Tailwind: `app, surface, surface2, border, text/text2/text3, accent/accent-hover/accent-tint, approved/approved-tint, rejected/rejected-tint, flag/flag-tint`. Todos los templates extienden este `base.html` y usan estas clases. Borrar el `base.html` competidor de D.
10. **Imágenes reales (CRÍTICO para el wow):** `image_card.html` renderiza `<img src="{{ image.path }}" ...>` (con `image.path = /static/datasets/<pid>/<filename>`) y expone `data-image-id="{{ image.id }}"` en la raíz de la card (para que el parseo de Track F funcione). `StaticFiles` montado en `/static`.
11. **Umbral de confianza — fuente única = macro `confidence_bar` de B** (>=0.90 verde/approved, 0.60–0.90 azul/accent, <0.60 ámbar/flag). `image_card` usa el macro, sin duplicado inline.
12. **Imágenes NO placeholder:** el enfoque `_placeholder_jpeg` de Track A queda **REEMPLAZADO** por la Task de adquisición de datasets reales del Track G. No generar imágenes truchas.
13. **Migración del legacy:** `tests/conftest.py`, `tests/features/curado.feature`, `tests/test_curado.py` y las rutas obsoletas `POST /seed`(solo filenames) y `GET /next` se migran/retiran (Task del Track G) para que `pytest -q` global quede verde con la API nueva (project-scoped).

---

## Track A — Fundación: data layer + classifier mock + seed + datasets

### Task 1: Migrar db.py al esquema nuevo (users/projects/images) con archivo + idempotencia

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/db.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_db.py` (create)

- [ ] **Step 1: Escribir test que falla — esquema, row_factory e idempotencia.**
Crear `tests/test_db.py`:
```python
"""Unit tests de la capa de datos (Track A — fundación)."""
from __future__ import annotations

import sqlite3

from pacusam import db


def test_connect_devuelve_row_factory():
    conn = db.connect(":memory:")
    assert conn.row_factory is sqlite3.Row


def test_connect_crea_las_tres_tablas():
    conn = db.connect(":memory:")
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"users", "projects", "images"} <= names


def test_users_tiene_email_unico():
    conn = db.connect(":memory:")
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
        ("a@b.com", "h", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
            ("a@b.com", "h2", "2026-01-01T00:00:00+00:00"),
        )
        assert False, "debía violar UNIQUE(email)"
    except sqlite3.IntegrityError:
        pass


def test_images_status_default_pending():
    conn = db.connect(":memory:")
    conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES ('u@x.com','h','t')"
    )
    conn.execute(
        "INSERT INTO projects (name, owner_id, labels, created_at) "
        "VALUES ('P', 1, '[\"NORMAL\"]', 't')"
    )
    conn.execute(
        "INSERT INTO images (project_id, filename, path) VALUES (1, 'a.jpg', '/a.jpg')"
    )
    conn.commit()
    row = conn.execute("SELECT status FROM images WHERE id=1").fetchone()
    assert row["status"] == "pending"


def test_connect_es_idempotente_sobre_archivo(tmp_path):
    p = str(tmp_path / "x.db")
    db.connect(p)
    conn2 = db.connect(p)  # segunda apertura no debe romper (CREATE IF NOT EXISTS)
    names = {
        r["name"]
        for r in conn2.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"users", "projects", "images"} <= names


def test_connect_default_usa_env_pacusam_db(tmp_path, monkeypatch):
    p = str(tmp_path / "env.db")
    monkeypatch.setenv("PACUSAM_DB", p)
    conn = db.connect()
    assert conn.execute("SELECT 1").fetchone()[0] == 1
```

- [ ] **Step 2: Correr y ver fallar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_db.py -q`
Salida esperada: errores/fallos porque `projects` y `users` no existen y `connect()` no acepta `None` ni lee `PACUSAM_DB` (ej. `sqlite3.OperationalError: no such table: users`, `FAILED ... test_users_tiene_email_unico`, etc.).

- [ ] **Step 3: Reemplazar `db.py` con el esquema nuevo (código real completo).**
Reemplazar todo el contenido de `src/pacusam/db.py` por:
```python
"""Capa de datos. SQLite a archivo (env PACUSAM_DB) o :memory: en tests.

Esquema del MVP académico PACUSAM: usuarios, proyectos y sus imágenes.
Las tablas se crean con IF NOT EXISTS para que connect() sea idempotente.
"""
from __future__ import annotations

import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS projects (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    owner_id    INTEGER NOT NULL REFERENCES users(id),
    domain      TEXT,
    labels      TEXT NOT NULL,          -- JSON array de strings
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id      INTEGER NOT NULL REFERENCES projects(id),
    filename        TEXT NOT NULL,
    path            TEXT NOT NULL,
    suggested_label TEXT,
    confidence      REAL,
    status          TEXT DEFAULT 'pending',  -- pending | validated | rejected
    final_label     TEXT,
    reject_reason   TEXT,
    shown_at        TEXT,
    validated_at    TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_images_project_filename
    ON images (project_id, filename);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    """Abre conexión y garantiza el esquema.

    `path=None` usa la env var PACUSAM_DB (default 'pacusam.db').
    Pasar ':memory:' explícitamente para tests.
    """
    if path is None:
        path = os.environ.get("PACUSAM_DB", "pacusam.db")
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    conn.commit()
    return conn
```

- [ ] **Step 4: Correr y ver pasar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_db.py -q`
Salida esperada: `6 passed`.

- [ ] **Step 5: Commit.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/db.py tests/test_db.py && git commit -m "feat(foundation): migrar db.py a esquema users/projects/images con archivo e idempotencia"`

---

### Task 2: classifier.suggest(filename, labels) determinista con confianzas mezcladas

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/classifier.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_classifier.py` (create)

- [ ] **Step 1: Escribir test que falla — firma nueva, determinismo, rango y mezcla.**
Crear `tests/test_classifier.py`:
```python
"""Unit tests del stub de Active Learning (Track A — fundación)."""
from __future__ import annotations

from pacusam import classifier

LABELS = ["NORMAL", "PNEUMONIA"]


def test_suggest_elige_una_label_del_proyecto():
    label, conf = classifier.suggest("rx_0001.jpeg", LABELS)
    assert label in LABELS


def test_suggest_confianza_en_rango():
    _, conf = classifier.suggest("rx_0001.jpeg", LABELS)
    assert 0.50 <= conf <= 0.99


def test_suggest_es_determinista():
    a = classifier.suggest("rx_0042.jpeg", LABELS)
    b = classifier.suggest("rx_0042.jpeg", LABELS)
    assert a == b


def test_suggest_respeta_labels_multiclase():
    multi = ["NEUTROPHIL", "EOSINOPHIL", "LYMPHOCYTE", "MONOCYTE"]
    label, _ = classifier.suggest("bccd_0007.jpeg", multi)
    assert label in multi


def test_suggest_genera_mezcla_de_confianzas():
    # Sobre un lote grande debe haber confianzas altas (>0.9) Y bajas (<0.6):
    # eso es lo que alimenta el uncertainty sampling.
    confs = [classifier.suggest(f"img_{i:04d}.jpeg", LABELS)[1] for i in range(100)]
    assert any(c > 0.90 for c in confs), "faltan confianzas altas"
    assert any(c < 0.60 for c in confs), "faltan confianzas bajas"
```

- [ ] **Step 2: Correr y ver fallar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_classifier.py -q`
Salida esperada: `TypeError: suggest() takes 1 positional argument but 2 were given` en todos los tests (la firma vieja es `suggest(filename)`).

- [ ] **Step 3: Reemplazar `classifier.py` (código real completo).**
Reemplazar todo el contenido de `src/pacusam/classifier.py` por:
```python
"""STUB del motor de Active Learning (componente `active_learning`).

Pre-clasificador mockeado y determinista: dado un nombre de archivo y las labels
del proyecto, devuelve una etiqueta sugerida + score de confianza realista.
Determinista a propósito (deriva de un hash del filename) para tests reproducibles.
El modelo REAL (US-15/M3) reemplaza este módulo sin tocar el resto del sistema.
"""
from __future__ import annotations

import hashlib


def suggest(filename: str, labels: list[str]) -> tuple[str, float]:
    """Etiqueta sugerida (∈ labels) + confianza en [0.50, 0.99].

    Determinista por filename. La confianza se distribuye en todo el rango para
    que haya mezcla de altas (>0.9) y bajas (<0.6) — combustible del uncertainty
    sampling de services.queue_next.
    """
    if not labels:
        raise ValueError("labels no puede estar vacío")
    h = int(hashlib.sha256(filename.encode()).hexdigest(), 16)
    label = labels[h % len(labels)]
    # Segundo hash independiente para la confianza, así no correlaciona con la label.
    hc = int(hashlib.sha256((filename + "#conf").encode()).hexdigest(), 16)
    confidence = round(0.50 + (hc % 50) / 100.0, 2)  # 0.50..0.99
    return label, confidence
```

- [ ] **Step 4: Correr y ver pasar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_classifier.py -q`
Salida esperada: `5 passed`.

- [ ] **Step 5: Commit.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/classifier.py tests/test_classifier.py && git commit -m "feat(foundation): classifier.suggest(filename, labels) determinista con confianzas mezcladas"`

---

### Task 3: services.seed_images idempotente por (project_id, filename) con classifier

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_seed_images.py` (create)

Nota: esta tarea solo migra `seed_images` (firma `seed_images(conn, project_id, filenames)`) y agrega un helper `_project_labels`. El resto de funciones de dominio (queue, validate, etc.) son de otro track; este `seed_images` debe convivir con el `services.py` existente sin romperlo (el `validate_image`/`progress` viejos quedan hasta que el track de dominio los reescriba).

- [ ] **Step 1: Escribir test que falla — siembra con sugerencias e idempotencia.**
Crear `tests/test_seed_images.py`:
```python
"""Unit tests de services.seed_images (Track A — fundación)."""
from __future__ import annotations

import json

import pytest

from pacusam import db, services


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    c.execute(
        "INSERT INTO users (email, password_hash, created_at) "
        "VALUES ('demo@pacusam.org','h','2026-01-01T00:00:00+00:00')"
    )
    c.execute(
        "INSERT INTO projects (name, owner_id, labels, created_at) "
        "VALUES (?,?,?,?)",
        ("Radiografías", 1, json.dumps(["NORMAL", "PNEUMONIA"]), "2026-01-01T00:00:00+00:00"),
    )
    c.commit()
    return c


def test_seed_images_inserta_y_devuelve_cantidad(conn):
    n = services.seed_images(conn, 1, ["rx_0001.jpeg", "rx_0002.jpeg", "rx_0003.jpeg"])
    assert n == 3
    rows = conn.execute("SELECT COUNT(*) c FROM images WHERE project_id=1").fetchone()
    assert rows["c"] == 3


def test_seed_images_corre_classifier(conn):
    services.seed_images(conn, 1, ["rx_0001.jpeg"])
    row = conn.execute("SELECT * FROM images WHERE filename='rx_0001.jpeg'").fetchone()
    assert row["suggested_label"] in ("NORMAL", "PNEUMONIA")
    assert 0.50 <= row["confidence"] <= 0.99
    assert row["status"] == "pending"


def test_seed_images_setea_path_bajo_datasets(conn):
    services.seed_images(conn, 1, ["rx_0001.jpeg"])
    row = conn.execute("SELECT path FROM images WHERE filename='rx_0001.jpeg'").fetchone()
    assert row["path"].endswith("rx_0001.jpeg")
    assert "/static/datasets/" in row["path"]


def test_seed_images_idempotente_por_project_filename(conn):
    services.seed_images(conn, 1, ["rx_0001.jpeg", "rx_0002.jpeg"])
    n2 = services.seed_images(conn, 1, ["rx_0001.jpeg", "rx_0002.jpeg", "rx_0003.jpeg"])
    total = conn.execute("SELECT COUNT(*) c FROM images WHERE project_id=1").fetchone()["c"]
    assert total == 3  # no duplica las 2 ya existentes
    assert n2 == 1     # solo rx_0003 es nueva
```

- [ ] **Step 2: Correr y ver fallar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_seed_images.py -q`
Salida esperada: fallos — el `seed_images` viejo tiene firma `(conn, filenames)` y no setea `project_id`/`path`, así que `TypeError` o `sqlite3.IntegrityError: NOT NULL constraint failed: images.project_id`.

- [ ] **Step 3: Reemplazar `seed_images` y agregar helper en `services.py` (código real completo).**
En `src/pacusam/services.py`, asegurar el import de `json` arriba (junto a los imports existentes):
```python
import json
```
Reemplazar la función `seed_images` existente (líneas del `def seed_images(...)` al `return len(filenames)`) por:
```python
def _project_labels(conn, project_id: int) -> list[str]:
    """Labels (JSON array) del proyecto. DomainError si no existe."""
    row = conn.execute(
        "SELECT labels FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if not row:
        raise DomainError("project_not_found", "Proyecto inexistente")
    return json.loads(row["labels"])


def seed_images(conn, project_id: int, filenames: list[str]) -> int:
    """Registra imágenes mockeadas del proyecto en DB, pasando cada una por el
    STUB del clasificador (sugerencia + confianza). Idempotente por
    (project_id, filename): re-sembrar no duplica. Devuelve cuántas se insertaron.

    `path` apunta al archivo servido estáticamente en static/datasets/<project_id>/.
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
        label, conf = classifier.suggest(fn, labels)
        path = f"/static/datasets/{project_id}/{fn}"
        conn.execute(
            "INSERT INTO images (project_id, filename, path, suggested_label, "
            "confidence, status) VALUES (?,?,?,?,?, 'pending')",
            (project_id, fn, path, label, conf),
        )
        inserted += 1
    conn.commit()
    return inserted
```

- [ ] **Step 4: Correr y ver pasar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_seed_images.py -q`
Salida esperada: `4 passed`.

- [ ] **Step 5: Commit.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_seed_images.py && git commit -m "feat(foundation): seed_images(conn, project_id, filenames) idempotente con path a datasets"`

---

### Task 4: requirements + .gitignore para versionar imágenes de datasets (jpeg/png)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/requirements.txt`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/requirements-dev.txt`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/pyproject.toml`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.gitignore`

Tarea de build + verificación (no TDD): agrega deps de auth/templates y deja de ignorar las imágenes de los datasets para que queden versionadas.

- [ ] **Step 1: Agregar `passlib[bcrypt]` y `jinja2` a `requirements.txt`.**
Reemplazar el bloque de runtime de `requirements.txt` por:
```
# Dependencias de runtime (lo que Render instala para correr la app).
# Para desarrollo/tests usar requirements-dev.txt.
fastapi>=0.110
uvicorn[standard]>=0.29
jinja2>=3.1
itsdangerous>=2.1
passlib[bcrypt]>=1.7
python-multipart>=0.0.9
```
(`itsdangerous` lo necesita SessionMiddleware; `python-multipart` los forms HTML.)

- [ ] **Step 2: Agregar las mismas deps a `requirements-dev.txt`.**
Reemplazar el bloque de `requirements-dev.txt` por:
```
# Instalación rápida para desarrollo/tests del MVP:
#   pip install -r requirements-dev.txt
fastapi>=0.110
uvicorn>=0.29
jinja2>=3.1
itsdangerous>=2.1
passlib[bcrypt]>=1.7
python-multipart>=0.0.9
pytest>=8.0
pytest-bdd>=7.0
httpx>=0.27
```

- [ ] **Step 3: Reflejar deps de runtime en `pyproject.toml`.**
En `pyproject.toml`, reemplazar el array `dependencies = [...]` del `[project]` por:
```toml
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "jinja2>=3.1",
    "itsdangerous>=2.1",
    "passlib[bcrypt]>=1.7",
    "python-multipart>=0.0.9",
]
```

- [ ] **Step 4: Permitir versionar las imágenes de datasets en `.gitignore`.**
Reemplazar el bloque `# Datos / artefactos ...` (las primeras líneas hasta `*.h5`) de `.gitignore` por:
```
# Datos / artefactos (no versionar imágenes médicas crudas ni datasets pesados)
data/
*.dcm
*.nii
*.nii.gz
models/
*.ckpt
*.pt
*.pth
*.h5

# EXCEPCIÓN: los datasets curados del demo (jpeg/png chicos) SÍ se versionan,
# así el deploy en Render tiene imágenes sin descargar nada en runtime.
!src/pacusam/static/datasets/
!src/pacusam/static/datasets/**
```

- [ ] **Step 5: Instalar deps nuevas y verificar import.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -c "import jinja2, itsdangerous, passlib.hash, multipart; print('deps ok')"`
Salida esperada: termina con `deps ok` y sin tracebacks.

- [ ] **Step 6: Commit.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add requirements.txt requirements-dev.txt pyproject.toml .gitignore && git commit -m "chore: agregar deps de auth/templates y versionar imágenes de datasets"`

---

### Task 5: Script de descarga de datasets (~100 imágenes por proyecto) a static/datasets

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/scripts/fetch_datasets.py`
- Create (resultado): `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/static/datasets/1/*.jpeg` (chest x-ray) y `.../datasets/2/*.jpeg` (blood cells)

Tarea de script + verificación manual (no TDD). El script baja un subconjunto chico de cada dataset y lo guarda con nombres deterministas (`<proyecto>_<NNNN>.jpeg`). Si una fuente no está disponible, cae a un generador local de imágenes-placebo etiquetables, de modo que el demo SIEMPRE tenga ~100 imágenes por proyecto versionables. Licencias: chest x-ray pneumonia CC BY 4.0; BCCD/blood-cells MIT.

- [ ] **Step 1: Crear el directorio de scripts y los destinos.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && mkdir -p scripts src/pacusam/static/datasets/1 src/pacusam/static/datasets/2`
Salida esperada: sin output (directorios creados).

- [ ] **Step 2: Escribir `scripts/fetch_datasets.py` (código real completo).**
Crear `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/scripts/fetch_datasets.py`:
```python
#!/usr/bin/env python3
"""Descarga (o genera fallback) ~N imágenes por proyecto del demo PACUSAM.

Proyectos:
  1 -> Radiografías de tórax (chest x-ray pneumonia, CC BY 4.0)
  2 -> Células sanguíneas    (BCCD / blood-cells, MIT)

Las imágenes quedan en src/pacusam/static/datasets/<project_id>/<base>_<NNNN>.jpeg
y se VERSIONAN (son chicas). Determinista: si una fuente remota falla,
genera placeholders reproducibles (sin red) para que el demo nunca quede vacío.

Uso:
  python scripts/fetch_datasets.py            # ~100 por proyecto
  python scripts/fetch_datasets.py --count 30 # subset rápido
"""
from __future__ import annotations

import argparse
import hashlib
import io
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASETS = ROOT / "src" / "pacusam" / "static" / "datasets"

# Manifiestos de fuentes públicas (imágenes individuales, no zips gigantes).
# Si una URL falla, el proyecto cae al generador de placeholders.
SOURCES: dict[str, dict] = {
    "1": {
        "base": "rx",
        # Subset chico del chest x-ray dataset (CC BY 4.0) servido como JPEG sueltos.
        "url_template": "https://raw.githubusercontent.com/ieee8023/covid-chestxray-dataset/master/images/{name}",
        "names": [],  # se completa en runtime si hay índice; vacío => placeholder
    },
    "2": {
        "base": "bccd",
        "url_template": "https://raw.githubusercontent.com/Shenggan/BCCD_Dataset/master/BCCD/JPEGImages/{name}",
        "names": [],
    },
}


def _placeholder_jpeg(seed: str, size: int = 128) -> bytes:
    """Genera un JPEG gris determinista (sin dependencias de red ni Pillow).

    Usa el formato PGM->no: para no depender de Pillow, escribimos un PPM mínimo
    convertido a bytes JPEG-like NO sirve; en su lugar generamos un PNG válido
    a mano sería complejo. Solución: requerir Pillow si está, si no PPM .jpeg falso.
    """
    try:
        from PIL import Image  # type: ignore

        h = int(hashlib.sha256(seed.encode()).hexdigest(), 16)
        shade = 40 + (h % 180)
        img = Image.new("L", (size, size), color=shade)
        # bandas para que se distingan visualmente entre sí
        px = img.load()
        for y in range(size):
            for x in range(size):
                px[x, y] = (shade + (x ^ y) % 64) % 256
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=70)
        return buf.getvalue()
    except Exception:
        # Fallback ultra-mínimo: bytes con cabecera JPEG (suficiente para servir el archivo).
        return bytes.fromhex("ffd8ffe000104a46494600010100000100010000ffd9")


def _download(url: str, timeout: float = 8.0) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "pacusam-demo"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            return data if data else None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None


def fetch_project(project_id: str, count: int) -> int:
    cfg = SOURCES[project_id]
    base = cfg["base"]
    out_dir = DATASETS / project_id
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for i in range(count):
        fname = f"{base}_{i:04d}.jpeg"
        dest = out_dir / fname
        if dest.exists() and dest.stat().st_size > 0:
            written += 1
            continue  # idempotente: no re-descarga lo que ya está versionado
        data = None
        names = cfg.get("names") or []
        if i < len(names):
            data = _download(cfg["url_template"].format(name=names[i]))
        if not data:
            data = _placeholder_jpeg(f"{project_id}:{fname}")
        dest.write_bytes(data)
        written += 1
    return written


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=100, help="imágenes por proyecto")
    args = ap.parse_args()
    total = 0
    for pid in SOURCES:
        n = fetch_project(pid, args.count)
        print(f"proyecto {pid}: {n} imágenes en {DATASETS / pid}")
        total += n
    print(f"TOTAL: {total} imágenes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Correr el script (subset rápido para verificar).**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/pip install pillow >/dev/null 2>&1; .venv/bin/python scripts/fetch_datasets.py --count 100`
Salida esperada: tres líneas tipo `proyecto 1: 100 imágenes en .../datasets/1`, `proyecto 2: 100 imágenes ...`, `TOTAL: 200 imágenes`.

- [ ] **Step 4: Verificar que los archivos existen y son JPEG no vacíos.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && ls src/pacusam/static/datasets/1 | head -3 && ls src/pacusam/static/datasets/2 | head -3 && find src/pacusam/static/datasets -name '*.jpeg' | wc -l && find src/pacusam/static/datasets -name '*.jpeg' -size 0 | wc -l`
Salida esperada: nombres `rx_0000.jpeg`/`bccd_0000.jpeg`, conteo total `200`, y `0` archivos vacíos.
Verificación manual: abrir `src/pacusam/static/datasets/1/rx_0000.jpeg` en el visor del SO y confirmar que se abre como imagen.

- [ ] **Step 5: Re-correr para verificar idempotencia (no duplica/no re-baja).**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python scripts/fetch_datasets.py --count 100 && find src/pacusam/static/datasets -name '*.jpeg' | wc -l`
Salida esperada: imprime `TOTAL: 200` igual que antes y el conteo sigue siendo `200`.

- [ ] **Step 6: Commit (script + imágenes versionadas).**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add scripts/fetch_datasets.py src/pacusam/static/datasets && git commit -m "chore: script fetch_datasets + ~100 imágenes por proyecto versionadas"`

---

### Task 6: seed.py — siembra determinista de usuario demo + 2 proyectos + imágenes

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/seed.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_seed.py` (create)

Depende de: `db.py` migrado (Task 1), `classifier.suggest(filename, labels)` (Task 2), `services.seed_images(conn, project_id, filenames)` (Task 3), y de `auth.create_user` (Track auth). Si `auth` aún no existe al ejecutar, `seed.py` cae a un insert directo de usuario con hash de passlib (documentado abajo) para no bloquear el track; cuando `auth.create_user` esté, se usa por preferencia.

- [ ] **Step 1: Escribir test que falla — siembra demo idempotente y determinista.**
Crear `tests/test_seed.py`:
```python
"""Unit tests de seed.py (Track A — fundación)."""
from __future__ import annotations

import json

from pacusam import db, seed


def test_seed_demo_crea_usuario_demo():
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    u = conn.execute(
        "SELECT * FROM users WHERE email = ?", (seed.DEMO_EMAIL,)
    ).fetchone()
    assert u is not None
    assert u["password_hash"]  # hasheada, no vacía


def test_seed_demo_crea_dos_proyectos_con_labels():
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    projs = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
    assert len(projs) == 2
    labels0 = json.loads(projs[0]["labels"])
    assert labels0 == ["NORMAL", "PNEUMONIA"]
    labels1 = json.loads(projs[1]["labels"])
    assert len(labels1) >= 3  # multiclase (células)


def test_seed_demo_registra_imagenes_con_sugerencia():
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    rows = conn.execute("SELECT * FROM images").fetchall()
    assert len(rows) >= 2  # al menos una por proyecto (más si hay archivos)
    for r in rows:
        assert r["suggested_label"]
        assert 0.50 <= r["confidence"] <= 0.99
        assert r["status"] == "pending"


def test_seed_demo_es_idempotente():
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    u1 = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    p1 = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    i1 = conn.execute("SELECT COUNT(*) c FROM images").fetchone()["c"]
    seed.seed_demo(conn)  # segunda corrida no duplica nada
    assert conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == u1
    assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == p1
    assert conn.execute("SELECT COUNT(*) c FROM images").fetchone()["c"] == i1
```

- [ ] **Step 2: Correr y ver fallar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_seed.py -q`
Salida esperada: `ModuleNotFoundError: No module named 'pacusam.seed'` (o `ImportError` al importar `seed`).

- [ ] **Step 3: Escribir `src/pacusam/seed.py` (código real completo).**
Crear `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/seed.py`:
```python
"""Siembra determinista del demo PACUSAM: 1 usuario + 2 proyectos + imágenes.

Idempotente: re-correr no duplica (usuario por email, proyectos por nombre/owner,
imágenes por (project_id, filename) vía services.seed_images).

Las imágenes se toman de src/pacusam/static/datasets/<project_id>/ si existen
(las baja scripts/fetch_datasets.py); si el directorio está vacío usa una lista
mockeada mínima para que el demo no quede sin datos.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from . import services

_STATIC_DATASETS = Path(__file__).parent / "static" / "datasets"

DEMO_EMAIL = "demo@pacusam.org"
DEMO_PASSWORD = "demo1234"

# (nombre, descripción, domain, labels, base de filename mockeado de fallback)
DEMO_PROJECTS = [
    {
        "name": "Radiografías de tórax",
        "description": "Curado de radiografías: detectar neumonía.",
        "domain": "radiologia",
        "labels": ["NORMAL", "PNEUMONIA"],
        "base": "rx",
    },
    {
        "name": "Células sanguíneas",
        "description": "Clasificación de leucocitos en frotis de sangre.",
        "domain": "hematologia",
        "labels": ["NEUTROPHIL", "EOSINOPHIL", "LYMPHOCYTE", "MONOCYTE"],
        "base": "bccd",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_demo_user(conn) -> int:
    """Crea (o devuelve) el usuario demo. Usa auth.create_user si está disponible,
    si no inserta directo con hash de passlib. Idempotente por email."""
    row = conn.execute(
        "SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)
    ).fetchone()
    if row:
        return row["id"]
    try:
        from . import auth  # Track auth

        user = auth.create_user(conn, DEMO_EMAIL, DEMO_PASSWORD)
        return user["id"]
    except (ImportError, AttributeError):
        from passlib.hash import bcrypt

        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
            (DEMO_EMAIL, bcrypt.hash(DEMO_PASSWORD), _now()),
        )
        conn.commit()
        return conn.execute(
            "SELECT id FROM users WHERE email = ?", (DEMO_EMAIL,)
        ).fetchone()["id"]


def _ensure_project(conn, owner_id: int, spec: dict) -> int:
    """Crea (o devuelve) un proyecto por (owner_id, name). Idempotente."""
    row = conn.execute(
        "SELECT id FROM projects WHERE owner_id = ? AND name = ?",
        (owner_id, spec["name"]),
    ).fetchone()
    if row:
        return row["id"]
    conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (
            spec["name"],
            spec["description"],
            owner_id,
            spec["domain"],
            json.dumps(spec["labels"]),
            _now(),
        ),
    )
    conn.commit()
    return conn.execute(
        "SELECT id FROM projects WHERE owner_id = ? AND name = ?",
        (owner_id, spec["name"]),
    ).fetchone()["id"]


def _filenames_for(project_id: int, base: str) -> list[str]:
    """Lista de imágenes a registrar: archivos reales del dataset si existen,
    si no una lista mockeada mínima determinista."""
    d = _STATIC_DATASETS / str(project_id)
    if d.is_dir():
        files = sorted(p.name for p in d.glob("*.jpeg"))
        if files:
            return files
    return [f"{base}_{i:04d}.jpeg" for i in range(6)]


def seed_demo(conn) -> dict:
    """Siembra el demo completo. Devuelve un resumen {user_id, projects, images}."""
    owner_id = _ensure_demo_user(conn)
    project_ids: list[int] = []
    total_images = 0
    for spec in DEMO_PROJECTS:
        pid = _ensure_project(conn, owner_id, spec)
        project_ids.append(pid)
        filenames = _filenames_for(pid, spec["base"])
        total_images += services.seed_images(conn, pid, filenames)
    return {
        "user_id": owner_id,
        "projects": project_ids,
        "images_inserted": total_images,
    }


if __name__ == "__main__":
    from . import db

    conn = db.connect()
    summary = seed_demo(conn)
    print(f"seed demo: {summary}")
```

- [ ] **Step 4: Correr y ver pasar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_seed.py -q`
Salida esperada: `4 passed`.

- [ ] **Step 5: Verificar la siembra end-to-end contra la DB de archivo del demo.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && PACUSAM_DB=/tmp/pacusam_seed_check.db .venv/bin/python -m pacusam.seed && rm -f /tmp/pacusam_seed_check.db`
Salida esperada: una línea `seed demo: {'user_id': 1, 'projects': [1, 2], 'images_inserted': 200}` (o `12` si los datasets no fueron descargados; en cualquier caso > 0).

- [ ] **Step 6: Commit.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/seed.py tests/test_seed.py && git commit -m "feat(foundation): seed.py — siembra determinista de usuario demo + 2 proyectos + imágenes"`

---

### Task 7: Re-seed automático del demo al arrancar (hook en db/api)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/seed.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_seed.py` (extend)

Provee la función `seed_if_empty(conn)` que el Track API llamará en `create_app` (re-seed determinista al arrancar si `projects` está vacía), siguiendo el contrato. Solo siembra cuando no hay proyectos, así no pisa datos existentes.

- [ ] **Step 1: Agregar test que falla — seed_if_empty solo siembra si projects vacía.**
Añadir al final de `tests/test_seed.py`:
```python
def test_seed_if_empty_siembra_cuando_no_hay_proyectos():
    conn = db.connect(":memory:")
    assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 0
    seeded = seed.seed_if_empty(conn)
    assert seeded is True
    assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 2


def test_seed_if_empty_no_siembra_si_ya_hay_proyectos():
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    before = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    seeded = seed.seed_if_empty(conn)  # ya hay datos -> no hace nada
    assert seeded is False
    assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == before
```

- [ ] **Step 2: Correr y ver fallar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_seed.py -q`
Salida esperada: `AttributeError: module 'pacusam.seed' has no attribute 'seed_if_empty'` (2 fallos nuevos, los 4 previos siguen pasando).

- [ ] **Step 3: Agregar `seed_if_empty` en `seed.py` (código real completo).**
En `src/pacusam/seed.py`, insertar esta función justo antes del bloque `if __name__ == "__main__":`:
```python
def seed_if_empty(conn) -> bool:
    """Re-seed determinista al arrancar: siembra el demo solo si no hay proyectos.
    Devuelve True si sembró, False si ya había datos. El Track API la invoca en
    create_app para que el deploy/Render tenga datos al abrir sin pisar lo existente."""
    count = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    if count > 0:
        return False
    seed_demo(conn)
    return True
```

- [ ] **Step 4: Correr y ver pasar.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_seed.py -q`
Salida esperada: `6 passed`.

- [ ] **Step 5: Verificar la suite de Track A completa sigue verde.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_db.py tests/test_classifier.py tests/test_seed_images.py tests/test_seed.py -q`
Salida esperada: `21 passed` (6 db + 5 classifier + 4 seed_images + 6 seed).

- [ ] **Step 6: Commit.**
`cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/seed.py tests/test_seed.py && git commit -m "feat(foundation): seed.seed_if_empty para re-seed determinista al arrancar"`


## Track B — Design system + base template (UI foundation, dependency de C/D/E/F)

### Task 8: Setup de dependencias UI (Jinja2 + passlib) y árbol de templates

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/requirements.txt`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/requirements-dev.txt`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/pyproject.toml`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/.gitkeep`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/.gitkeep`

Track fundación: instala lo que toda la UI necesita (`jinja2` para render server-side, `passlib[bcrypt]` para auth de Track A/C) y crea el árbol de carpetas que el resto de los tracks va a poblar. No hay test unitario acá: es setup de entorno verificado con un import.

- [ ] **Step 1: Agregar jinja2 y passlib a requirements.txt.** Reemplazar el bloque de runtime por:
  ```txt
  # Dependencias de runtime (lo que Render instala para correr la app).
  # Para desarrollo/tests usar requirements-dev.txt.
  fastapi>=0.110
  uvicorn[standard]>=0.29
  jinja2>=3.1
  passlib[bcrypt]>=1.7
  ```
- [ ] **Step 2: Agregar las mismas a requirements-dev.txt.** El bloque completo queda:
  ```txt
  # Instalación rápida para desarrollo/tests del MVP:
  #   pip install -r requirements-dev.txt
  fastapi>=0.110
  uvicorn>=0.29
  jinja2>=3.1
  passlib[bcrypt]>=1.7
  pytest>=8.0
  pytest-bdd>=7.0
  httpx>=0.27
  ```
- [ ] **Step 3: Agregar las deps de runtime a pyproject.toml.** En `[project].dependencies` reemplazar la lista por:
  ```toml
  dependencies = [
      "fastapi>=0.110",
      "uvicorn>=0.29",
      "jinja2>=3.1",
      "passlib[bcrypt]>=1.7",
  ]
  ```
- [ ] **Step 4: Instalar en el venv y verificar import.** Correr:
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/pip install -r /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/requirements-dev.txt
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -c "import jinja2, passlib.hash; print('jinja2', jinja2.__version__, 'ok')"
  ```
  Salida esperada: termina sin error y la última línea imprime `jinja2 3.x.x ok` (antes de esto, el import de `jinja2` fallaba con `ModuleNotFoundError: No module named 'jinja2'`).
- [ ] **Step 5: Crear el árbol de templates con placeholders versionables.** Correr:
  ```bash
  mkdir -p /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials
  touch /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/.gitkeep
  touch /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/.gitkeep
  ```
  Verificar: `ls /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/` lista `.gitkeep`.
- [ ] **Step 6: Commit.**
  ```bash
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow add requirements.txt requirements-dev.txt pyproject.toml src/pacusam/templates/.gitkeep src/pacusam/templates/partials/.gitkeep
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow commit -m "chore: agregar jinja2 + passlib y arbol de templates"
  ```

---

### Task 9: Módulo de templating reusable (Jinja2Templates + helper render)

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templating.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_templating.py`

Centraliza la config de Jinja2 en UN módulo que `api.py` y todos los tracks consumen, en vez de re-instanciar `Jinja2Templates` en cada lado. Expone `templates` (instancia compartida, apuntando a `src/pacusam/templates/`) y `render(request, name, **ctx)` que inyecta `request` y devuelve un `HTMLResponse`. Esto sí es testeable con un test unitario sobre un template de prueba.

- [ ] **Step 1: Escribir test que falla.** Crear `tests/test_templating.py`:
  ```python
  """Unit tests del módulo de templating compartido (Track B)."""
  from __future__ import annotations

  from pathlib import Path

  from starlette.requests import Request

  from pacusam import templating


  def _fake_request() -> Request:
      # Request mínimo: templating sólo necesita el scope para url_for/contexto.
      scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
      return Request(scope)


  def test_templates_dir_apunta_a_carpeta_templates():
      expected = Path(templating.__file__).parent / "templates"
      assert templating.TEMPLATES_DIR == expected
      assert templating.TEMPLATES_DIR.is_dir()


  def test_render_devuelve_html_con_contexto(tmp_path):
      # Escribimos un template temporal y comprobamos que render lo resuelve.
      probe = templating.TEMPLATES_DIR / "_probe.html"
      probe.write_text("<p>hola {{ nombre }}</p>", encoding="utf-8")
      try:
          resp = templating.render(_fake_request(), "_probe.html", nombre="curador")
          assert resp.status_code == 200
          assert "text/html" in resp.headers["content-type"]
          assert b"hola curador" in resp.body
      finally:
          probe.unlink()
  ```
- [ ] **Step 2: Correr y ver fallar.**
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -m pytest /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_templating.py -q
  ```
  Salida esperada: `ModuleNotFoundError: No module named 'pacusam.templating'` (recolección falla, 0 passed).
- [ ] **Step 3: Implementar el módulo.** Crear `src/pacusam/templating.py`:
  ```python
  """Config compartida de Jinja2 para toda la UI (Track B).

  Un solo punto de verdad para `Jinja2Templates`: api.py y los fragmentos HTMX
  importan `templates`/`render` de acá en vez de re-instanciar. Los partials
  (progress_bar, confidence_bar, flash) viven en templates/partials/ y se usan
  vía `{% import %}` desde los templates de cada track.
  """
  from __future__ import annotations

  from pathlib import Path

  from starlette.requests import Request
  from starlette.responses import HTMLResponse
  from starlette.templating import Jinja2Templates

  TEMPLATES_DIR = Path(__file__).parent / "templates"

  templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


  def render(request: Request, name: str, status_code: int = 200, **context) -> HTMLResponse:
      """Renderiza `name` inyectando `request` (Jinja2Templates lo exige) + contexto.

      Devuelve HTMLResponse para que las rutas de página y los fragmentos HTMX
      compartan el mismo helper.
      """
      return templates.TemplateResponse(
          request, name, context, status_code=status_code
      )
  ```
- [ ] **Step 4: Correr y ver pasar.**
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -m pytest /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_templating.py -q
  ```
  Salida esperada: `2 passed`.
- [ ] **Step 5: Commit.**
  ```bash
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow add src/pacusam/templating.py tests/test_templating.py
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow commit -m "feat(ui): modulo de templating compartido (Jinja2Templates + render)"
  ```

---

### Task 10: base.html — layout con design system (CDN HTMX/Alpine/Tailwind + tokens)

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/base.html`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_base_template.py`

El layout raíz que todo template extiende. Carga fonts (Inter / Lora / JetBrains Mono), Tailwind CDN con config inline que mapea la paleta del design system a clases utilitarias (`bg-app`, `text-muted`, `text-accent`, etc.), HTMX y Alpine por CDN. Define bloques `title`, `head_extra`, `sidebar` y `content` que C/D/E/F llenan. Verificación: un test de render confirma que los assets y los tokens están presentes; luego inspección visual con uvicorn.

- [ ] **Step 1: Escribir test que falla.** Crear `tests/test_base_template.py`:
  ```python
  """Verifica que base.html trae el design system completo (Track B)."""
  from __future__ import annotations

  from starlette.requests import Request

  from pacusam import templating


  def _req() -> Request:
      return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


  def _render_base() -> str:
      # Un template hijo mínimo que extiende base, para forzar el render del layout.
      child = templating.TEMPLATES_DIR / "_probe_base.html"
      child.write_text(
          '{% extends "base.html" %}{% block content %}<main>PROBE_BODY</main>{% endblock %}',
          encoding="utf-8",
      )
      try:
          return templating.render(_req(), "_probe_base.html", title="PROBE_TITLE").body.decode()
      finally:
          child.unlink()


  def test_base_carga_cdns_y_fonts():
      html = _render_base()
      assert "cdn.tailwindcss.com" in html
      assert "unpkg.com/htmx.org" in html
      assert "alpinejs" in html  # Alpine CDN (cdn.jsdelivr.net/.../alpinejs)
      assert "Inter" in html and "Lora" in html and "JetBrains+Mono" in html


  def test_base_define_tokens_de_paleta_en_tailwind_config():
      html = _render_base()
      # Colores del design system mapeados a nombres de Tailwind.
      assert "#FCFBF9" in html      # app
      assert "#2563EB" in html      # accent
      assert "#16A34A" in html      # approved
      assert "#DC2626" in html      # rejected
      assert "#D97706" in html      # flag
      assert "tailwind.config" in html


  def test_base_inserta_titulo_y_contenido_del_hijo():
      html = _render_base()
      assert "PROBE_TITLE" in html
      assert "PROBE_BODY" in html
  ```
- [ ] **Step 2: Correr y ver fallar.**
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -m pytest /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_base_template.py -q
  ```
  Salida esperada: falla con `jinja2.exceptions.TemplateNotFound: base.html` (3 errors/failed).
- [ ] **Step 3: Implementar base.html.** Crear `src/pacusam/templates/base.html`:
  ```html
  <!doctype html>
  <html lang="es" class="h-full">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{% block title %}{{ title|default("PACUSAM") }}{% endblock %}</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Lora:wght@500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">

    <script src="https://cdn.tailwindcss.com"></script>
    <script>
      tailwind.config = {
        theme: {
          extend: {
            colors: {
              app:      "#FCFBF9",
              surface:  "#FFFFFF",
              surface2: "#F4F2EE",
              border:   "#E7E4DE",
              ink:      "#1A1A18",
              muted:    "#6B6B66",
              faint:    "#9C9A94",
              accent:   { DEFAULT: "#2563EB", hover: "#1D4ED8", tint: "#EFF4FF" },
              approved: { DEFAULT: "#16A34A", tint: "#ECFDF3" },
              rejected: { DEFAULT: "#DC2626", tint: "#FEF2F2" },
              flag:     { DEFAULT: "#D97706", tint: "#FFFBEB" },
            },
            fontFamily: {
              sans:    ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
              display: ['Lora', 'ui-serif', 'Georgia', 'serif'],
              mono:    ['"JetBrains Mono"', 'ui-monospace', 'monospace'],
            },
            transitionDuration: { DEFAULT: '140ms' },
          },
        },
      };
    </script>
    <style>
      body { font-feature-settings: "cv11", "ss01"; }
      [x-cloak] { display: none !important; }
    </style>

    <script defer src="https://unpkg.com/htmx.org@1.9.12"></script>
    <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>

    {% block head_extra %}{% endblock %}
  </head>
  <body class="h-full bg-app text-ink font-sans antialiased">
    <div class="flex min-h-full">
      {% block sidebar %}{% endblock %}
      <div class="flex-1 flex flex-col min-w-0">
        {% block flash %}{% endblock %}
        {% block content %}{% endblock %}
      </div>
    </div>
  </body>
  </html>
  ```
- [ ] **Step 4: Correr y ver pasar.**
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -m pytest /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_base_template.py -q
  ```
  Salida esperada: `3 passed`.
- [ ] **Step 5: Commit.**
  ```bash
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow add src/pacusam/templates/base.html tests/test_base_template.py
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow commit -m "feat(ui): base.html con design system (CDNs, fonts, tokens Tailwind)"
  ```

---

### Task 11: Partials Jinja reusables — progress_bar, confidence_bar, flash (macros)

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/ui.html`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_partials.py`

Los helpers que C/D/E/F importan con `{% from "partials/ui.html" import progress_bar, confidence_bar, flash %}`. Un solo archivo de macros mantiene el contrato chico y descubrible. `progress_bar(percent)` consume `services.progress()["percent"]`; `confidence_bar(confidence)` consume el `confidence ∈ [0.50,0.99]` de `classifier.suggest`/`queue_next`; `flash(message, kind)` muestra errores de dominio (`kind ∈ {error,success,flag,info}`). Testeable renderizando los macros con contexto.

- [ ] **Step 1: Escribir test que falla.** Crear `tests/test_partials.py`:
  ```python
  """Unit tests de los macros Jinja compartidos (Track B)."""
  from __future__ import annotations

  from starlette.requests import Request

  from pacusam import templating


  def _req() -> Request:
      return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


  def _render(snippet: str, **ctx) -> str:
      # Monta un template efímero que importa los macros y renderiza el snippet.
      probe = templating.TEMPLATES_DIR / "_probe_partials.html"
      probe.write_text(
          '{% from "partials/ui.html" import progress_bar, confidence_bar, flash %}\n'
          + snippet,
          encoding="utf-8",
      )
      try:
          return templating.render(_req(), "_probe_partials.html", **ctx).body.decode()
      finally:
          probe.unlink()


  def test_progress_bar_pinta_porcentaje():
      html = _render("{{ progress_bar(42.5) }}")
      assert "42.5%" in html              # etiqueta legible
      assert "width: 42.5%" in html       # ancho de la barra
      assert 'role="progressbar"' in html


  def test_confidence_bar_alta_es_verde_baja_es_flag():
      alta = _render("{{ confidence_bar(0.95) }}")
      baja = _render("{{ confidence_bar(0.55) }}")
      assert "95%" in alta and "bg-approved" in alta
      assert "55%" in baja and "bg-flag" in baja


  def test_flash_error_muestra_mensaje_y_estilo_rejected():
      html = _render('{{ flash("La etiqueta es obligatoria", "error") }}')
      assert "La etiqueta es obligatoria" in html
      assert "bg-rejected-tint" in html
      assert "text-rejected" in html


  def test_flash_vacio_no_renderiza_nada():
      html = _render('{{ flash("", "error") }}')
      assert "bg-rejected-tint" not in html  # sin mensaje, no hay caja
  ```
- [ ] **Step 2: Correr y ver fallar.**
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -m pytest /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_partials.py -q
  ```
  Salida esperada: falla con `jinja2.exceptions.TemplateNotFound: partials/ui.html` (4 failed).
- [ ] **Step 3: Implementar los macros.** Crear `src/pacusam/templates/partials/ui.html`:
  ```html
  {# Macros UI compartidos (Track B). Importar con:
     {% from "partials/ui.html" import progress_bar, confidence_bar, flash %} #}

  {% macro progress_bar(percent) -%}
    {% set p = '%.1f'|format(percent|float) %}
    <div class="w-full" role="progressbar" aria-valuenow="{{ p }}" aria-valuemin="0" aria-valuemax="100">
      <div class="flex items-center justify-between mb-1">
        <span class="text-xs font-medium text-muted">Progreso</span>
        <span class="text-xs font-mono text-ink">{{ p }}%</span>
      </div>
      <div class="h-2 w-full rounded-full bg-surface2 overflow-hidden">
        <div class="h-full rounded-full bg-accent transition-[width] duration-150 ease-out"
             style="width: {{ p }}%"></div>
      </div>
    </div>
  {%- endmacro %}

  {% macro confidence_bar(confidence) -%}
    {% set pct = (confidence|float * 100)|round|int %}
    {% if confidence|float >= 0.90 %}{% set tone = 'bg-approved' %}{% set txt = 'text-approved' %}
    {% elif confidence|float >= 0.60 %}{% set tone = 'bg-accent' %}{% set txt = 'text-accent' %}
    {% else %}{% set tone = 'bg-flag' %}{% set txt = 'text-flag' %}{% endif %}
    <div class="flex items-center gap-2">
      <div class="h-1.5 flex-1 rounded-full bg-surface2 overflow-hidden">
        <div class="h-full rounded-full {{ tone }} transition-[width] duration-150 ease-out"
             style="width: {{ pct }}%"></div>
      </div>
      <span class="text-xs font-mono {{ txt }} tabular-nums">{{ pct }}%</span>
    </div>
  {%- endmacro %}

  {% macro flash(message, kind='info') -%}
    {% if message %}
      {% if kind == 'error' %}{% set box = 'bg-rejected-tint text-rejected border-rejected/30' %}
      {% elif kind == 'success' %}{% set box = 'bg-approved-tint text-approved border-approved/30' %}
      {% elif kind == 'flag' %}{% set box = 'bg-flag-tint text-flag border-flag/30' %}
      {% else %}{% set box = 'bg-accent-tint text-accent border-accent/30' %}{% endif %}
      <div class="flex items-start gap-2 rounded-lg border px-3 py-2 text-sm {{ box }}"
           role="alert" x-data="{ show: true }" x-show="show" x-cloak>
        <span class="flex-1">{{ message }}</span>
        <button type="button" class="opacity-60 hover:opacity-100 transition" @click="show = false" aria-label="Cerrar">&times;</button>
      </div>
    {% endif %}
  {%- endmacro %}
  ```
- [ ] **Step 4: Correr y ver pasar.**
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -m pytest /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_partials.py -q
  ```
  Salida esperada: `4 passed`.
- [ ] **Step 5: Commit.**
  ```bash
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow add src/pacusam/templates/partials/ui.html tests/test_partials.py
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow commit -m "feat(ui): macros reusables progress_bar/confidence_bar/flash"
  ```

---

### Task 12: Página demo de UI foundation + verificación visual con uvicorn

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/_ui_demo.html`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_ui_demo_page.py`

Cierra el track con una página `/_ui` que ejercita base + los tres macros juntos, para que C/D/E/F vean el design system funcionando y para verificación visual antes de que existan las páginas reales. Es una ruta de andamiaje (prefijo `_`, `include_in_schema=False`); cuando las páginas reales aterricen se puede borrar. El test confirma 200 + HTML; luego se levanta uvicorn y se observa en el browser.

- [ ] **Step 1: Escribir test que falla.** Crear `tests/test_ui_demo_page.py`:
  ```python
  """La página de andamiaje /_ui renderiza el design system (Track B)."""
  from __future__ import annotations

  from fastapi.testclient import TestClient

  from pacusam.api import create_app


  def test_ui_demo_responde_html_con_design_system():
      client = TestClient(create_app(":memory:"))
      r = client.get("/_ui")
      assert r.status_code == 200
      assert "text/html" in r.headers["content-type"]
      body = r.text
      # base.html cargado:
      assert "cdn.tailwindcss.com" in body
      # macros ejercitados:
      assert 'role="progressbar"' in body          # progress_bar
      assert "tabular-nums" in body                 # confidence_bar
      assert "PACUSAM — UI foundation" in body      # contenido propio de la demo
  ```
- [ ] **Step 2: Correr y ver fallar.**
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -m pytest /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_ui_demo_page.py -q
  ```
  Salida esperada: `assert 404 == 200` (la ruta `/_ui` no existe todavía), 1 failed.
- [ ] **Step 3: Crear el template demo.** Crear `src/pacusam/templates/_ui_demo.html`:
  ```html
  {% extends "base.html" %}
  {% from "partials/ui.html" import progress_bar, confidence_bar, flash %}
  {% block title %}UI foundation · PACUSAM{% endblock %}
  {% block content %}
  <main class="mx-auto w-full max-w-3xl px-6 py-10 space-y-8">
    <header class="space-y-1">
      <h1 class="font-display text-2xl text-ink">PACUSAM — UI foundation</h1>
      <p class="text-sm text-muted">Andamiaje del design system (Track B). Borrable cuando aterricen las páginas reales.</p>
    </header>

    <section class="space-y-3">
      <h2 class="text-xs font-semibold uppercase tracking-wide text-faint">Flash / errores</h2>
      {{ flash("Validación guardada", "success") }}
      {{ flash("La etiqueta es obligatoria", "error") }}
      {{ flash("Confianza baja: revisar manualmente", "flag") }}
    </section>

    <section class="space-y-3 rounded-xl border border-border bg-surface p-5">
      <h2 class="text-xs font-semibold uppercase tracking-wide text-faint">Progreso</h2>
      {{ progress_bar(62.5) }}
    </section>

    <section class="space-y-4 rounded-xl border border-border bg-surface p-5">
      <h2 class="text-xs font-semibold uppercase tracking-wide text-faint">Confianza del clasificador</h2>
      <div class="space-y-1"><span class="text-sm text-ink">rx_torax_0001.dcm (alta)</span>{{ confidence_bar(0.95) }}</div>
      <div class="space-y-1"><span class="text-sm text-ink">tc_cerebro_0002.jpg (media)</span>{{ confidence_bar(0.72) }}</div>
      <div class="space-y-1"><span class="text-sm text-ink">rx_torax_0003.png (baja)</span>{{ confidence_bar(0.54) }}</div>
    </section>

    <section class="flex gap-3">
      <button class="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition hover:bg-accent-hover">Validar</button>
      <button class="rounded-lg border border-border bg-surface px-4 py-2 text-sm font-medium text-ink transition hover:bg-surface2">Rechazar</button>
    </section>
  </main>
  {% endblock %}
  ```
- [ ] **Step 4: Conectar Jinja2 en api.py.** En `src/pacusam/api.py` agregar el import del módulo compartido (junto a `from . import db, services`):
  ```python
  from . import db, services, templating
  from fastapi import Request
  ```
  Y registrar la ruta de andamiaje dentro de `create_app`, justo antes de `return app`:
  ```python
      @app.get("/_ui", include_in_schema=False)
      def ui_demo(request: Request):
          return templating.render(request, "_ui_demo.html")
  ```
  (Nota para tracks siguientes: `templating.render` es el helper estándar; C/D/E/F lo usan para todas sus páginas y fragmentos HTMX.)
- [ ] **Step 5: Correr y ver pasar.**
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -m pytest /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_ui_demo_page.py -q
  ```
  Salida esperada: `1 passed`.
- [ ] **Step 6: Verificación visual con uvicorn.** Levantar la app y abrir el browser:
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/uvicorn pacusam.api:app --app-dir /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src --reload --port 8000
  ```
  Abrir `http://127.0.0.1:8000/_ui` y observar: fondo crema (`#FCFBF9`), títulos en serif Lora, tres cajas de flash (verde / roja / ámbar), una barra de progreso azul al 62.5%, tres barras de confianza (verde alta, azul media, ámbar baja con su `%` en mono), y dos botones (azul accent + outline). Confirmar que NO hay errores 500 en la consola de uvicorn ni 404 de fuentes/CDN en la pestaña Network. Cortar con Ctrl+C.
- [ ] **Step 7: Correr toda la suite (no rompimos nada de Leandro).**
  ```bash
  /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/.venv/bin/python -m pytest /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests -q
  ```
  Salida esperada: todos los tests existentes (BDD de curado) + los nuevos del Track B en verde (`N passed`), 0 failed.
- [ ] **Step 8: Commit.**
  ```bash
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow add src/pacusam/templates/_ui_demo.html src/pacusam/api.py tests/test_ui_demo_page.py
  git -C /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow commit -m "feat(ui): pagina demo /_ui que ejercita base + macros (verificacion visual)"
  ```
```


## Track C — Auth vertical (registro/login/logout + guard)

### Task 13: Agregar passlib[bcrypt] a dependencias

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/requirements.txt`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/requirements-dev.txt`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/pyproject.toml`

- [ ] **Step 1: Agregar passlib a requirements.txt.** Editar `requirements.txt` para que quede:
```
# Dependencias de runtime (lo que Render instala para correr la app).
# Para desarrollo/tests usar requirements-dev.txt.
fastapi>=0.110
uvicorn[standard]>=0.29
jinja2>=3.1
itsdangerous>=2.1
passlib[bcrypt]>=1.7
```
(`jinja2` para templates Track B, `itsdangerous` para SessionMiddleware, `passlib[bcrypt]` para hashing.)

- [ ] **Step 2: Agregar passlib a requirements-dev.txt.** Editar para que quede:
```
# Instalación rápida para desarrollo/tests del MVP:
#   pip install -r requirements-dev.txt
fastapi>=0.110
uvicorn>=0.29
jinja2>=3.1
itsdangerous>=2.1
passlib[bcrypt]>=1.7
pytest>=8.0
pytest-bdd>=7.0
httpx>=0.27
```

- [ ] **Step 3: Agregar dependencias a pyproject.toml.** Reemplazar el bloque `dependencies` en `pyproject.toml`:
```toml
dependencies = [
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "jinja2>=3.1",
    "itsdangerous>=2.1",
    "passlib[bcrypt]>=1.7",
]
```

- [ ] **Step 4: Instalar en el venv.** Correr:
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/pip install -r requirements-dev.txt
```
Salida esperada: termina con `Successfully installed ... passlib-1.7.x bcrypt-... itsdangerous-... jinja2-...` (o `Requirement already satisfied` para los ya presentes).

- [ ] **Step 5: Verificar import de passlib.** Correr:
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -c "from passlib.context import CryptContext; print(CryptContext(schemes=['bcrypt']).hash('x')[:4])"
```
Salida esperada: empieza con `$2b$` (prefijo bcrypt). Imprime algo como `$2b$`.

- [ ] **Step 6: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add requirements.txt requirements-dev.txt pyproject.toml && git commit -m "chore: agregar passlib[bcrypt], jinja2 e itsdangerous a dependencias"
```

---

### Task 14: auth.py — hash/verify password (roundtrip TDD)

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_auth.py`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/auth.py`

- [ ] **Step 1: Escribir test que falla — hash roundtrip.** Crear `tests/test_auth.py`:
```python
"""Tests unitarios de la capa de auth (Track C).

No tocan HTTP: prueban hashing y las funciones de dominio de usuarios
sobre una conexión SQLite en memoria.
"""
from __future__ import annotations

import pytest

from pacusam import auth, db


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_hash_password_no_es_plano():
    h = auth.hash_password("secreto123")
    assert h != "secreto123"
    assert h.startswith("$2")  # prefijo bcrypt


def test_verify_password_roundtrip():
    h = auth.hash_password("secreto123")
    assert auth.verify_password("secreto123", h) is True
    assert auth.verify_password("otra-cosa", h) is False
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth.py -q
```
Salida esperada: `ModuleNotFoundError: No module named 'pacusam.auth'` (collection error / 2 errors).

- [ ] **Step 3: Implementación mínima — crear auth.py con hash/verify.** Crear `src/pacusam/auth.py`:
```python
"""Capa de autenticación (Track C).

Hashing de contraseñas con bcrypt (passlib) y operaciones de dominio sobre
la tabla `users`. No conoce HTTP: la capa `api` la envuelve (SessionMiddleware
+ require_user). Errores de negocio via services.DomainError(code).
"""
from __future__ import annotations

from datetime import datetime, timezone

from passlib.context import CryptContext

from .services import DomainError

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str) -> str:
    """Devuelve el hash bcrypt de la contraseña."""
    return _pwd.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """True si la contraseña coincide con el hash."""
    try:
        return _pwd.verify(password, password_hash)
    except ValueError:
        return False
```

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth.py -q
```
Salida esperada: `2 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add tests/test_auth.py src/pacusam/auth.py && git commit -m "feat(auth): hash_password/verify_password con bcrypt"
```

---

### Task 15: db.py — tabla users (schema + idempotencia)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/db.py`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_auth.py`

> Nota de integración: el esquema completo (projects/images extendidos) lo define Track A en `db.py`. Track C solo agrega la tabla `users`. Si el bloque `SCHEMA` ya contiene `users` cuando ensamblás, omití el Step 3 (la tabla ya existe) y mantené solo el test.

- [ ] **Step 1: Escribir test que falla — la tabla users existe.** Agregar al final de `tests/test_auth.py`:
```python
def test_db_tiene_tabla_users(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
    assert {"id", "email", "password_hash", "created_at"} <= cols


def test_db_users_idempotente():
    # connect dos veces sobre el mismo archivo en memoria compartida no rompe
    c1 = db.connect(":memory:")
    c2 = db.connect(":memory:")
    assert c1.execute("PRAGMA table_info(users)").fetchall() is not None
    assert c2.execute("PRAGMA table_info(users)").fetchall() is not None
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth.py -q -k users
```
Salida esperada: `test_db_tiene_tabla_users` falla — el set de columnas está vacío, `AssertionError: assert {'created_at', 'email', 'id', 'password_hash'} <= set()`.

- [ ] **Step 3: Implementación mínima — agregar tabla users a SCHEMA.** En `src/pacusam/db.py`, agregar el bloque `CREATE TABLE users` dentro de `SCHEMA` (antes del cierre de la triple comilla). El `SCHEMA` debe contener:
```python
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS images (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename        TEXT NOT NULL,
    suggested_label TEXT,
    confidence      REAL,
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending | validated | rejected
    final_label     TEXT,
    validated_at    TEXT
);
"""
```
(El `CREATE TABLE IF NOT EXISTS` garantiza idempotencia. `executescript` ya corre en `connect`, sin cambios ahí. La definición canónica de `images`/`projects` es de Track A; acá solo aseguramos `users`.)

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth.py -q -k users
```
Salida esperada: `2 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/db.py tests/test_auth.py && git commit -m "feat(auth): tabla users en el esquema SQLite"
```

---

### Task 16: auth.py — create_user (con email_exists)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/auth.py`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_auth.py`

- [ ] **Step 1: Escribir test que falla — create_user devuelve dict y rechaza duplicados.** Agregar a `tests/test_auth.py`:
```python
def test_create_user_devuelve_dict(conn):
    u = auth.create_user(conn, "ana@hospital.org", "secreto123")
    assert u["id"] >= 1
    assert u["email"] == "ana@hospital.org"
    assert "password_hash" not in u  # no exponemos el hash


def test_create_user_persiste_hash(conn):
    auth.create_user(conn, "ana@hospital.org", "secreto123")
    row = conn.execute("SELECT password_hash FROM users WHERE email=?", ("ana@hospital.org",)).fetchone()
    assert row["password_hash"].startswith("$2")
    assert row["password_hash"] != "secreto123"


def test_create_user_email_duplicado(conn):
    auth.create_user(conn, "ana@hospital.org", "secreto123")
    with pytest.raises(auth.DomainError) as exc:
        auth.create_user(conn, "ana@hospital.org", "otra-pass")
    assert exc.value.code == "email_exists"
```
> `auth.DomainError` se re-exporta desde `services.DomainError` (ya importado en auth.py), por eso `auth.DomainError` resuelve.

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth.py -q -k create_user
```
Salida esperada: `AttributeError: module 'pacusam.auth' has no attribute 'create_user'` (3 failed/errors).

- [ ] **Step 3: Implementación mínima — create_user.** Agregar a `src/pacusam/auth.py` (después de `verify_password`):
```python
import sqlite3


def _user_dict(row) -> dict:
    """Proyección pública de un usuario (sin password_hash)."""
    return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}


def create_user(conn, email: str, password: str) -> dict:
    """Crea un usuario. Lanza DomainError('email_exists') si el email ya existe."""
    try:
        cur = conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
            (email, hash_password(password), _now()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise DomainError("email_exists", "El email ya está registrado")
    row = conn.execute(
        "SELECT id, email, created_at FROM users WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _user_dict(row)
```
Para que `auth.DomainError` exista como atributo del módulo, asegurar el import ya presente `from .services import DomainError` al tope (del Task hash/verify). No hace falta nada más: `DomainError` es nombre del módulo `auth`.

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth.py -q -k create_user
```
Salida esperada: `3 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/auth.py tests/test_auth.py && git commit -m "feat(auth): create_user con DomainError('email_exists') en duplicados"
```

---

### Task 17: auth.py — authenticate y get_user

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/auth.py`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_auth.py`

- [ ] **Step 1: Escribir test que falla — authenticate ok/inválido y get_user.** Agregar a `tests/test_auth.py`:
```python
def test_authenticate_ok(conn):
    creado = auth.create_user(conn, "ana@hospital.org", "secreto123")
    u = auth.authenticate(conn, "ana@hospital.org", "secreto123")
    assert u is not None
    assert u["id"] == creado["id"]
    assert "password_hash" not in u


def test_authenticate_password_invalida(conn):
    auth.create_user(conn, "ana@hospital.org", "secreto123")
    assert auth.authenticate(conn, "ana@hospital.org", "mal") is None


def test_authenticate_email_inexistente(conn):
    assert auth.authenticate(conn, "nadie@hospital.org", "x") is None


def test_get_user_ok(conn):
    creado = auth.create_user(conn, "ana@hospital.org", "secreto123")
    u = auth.get_user(conn, creado["id"])
    assert u["email"] == "ana@hospital.org"


def test_get_user_inexistente(conn):
    assert auth.get_user(conn, 9999) is None
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth.py -q -k "authenticate or get_user"
```
Salida esperada: `AttributeError: module 'pacusam.auth' has no attribute 'authenticate'` (5 failed/errors).

- [ ] **Step 3: Implementación mínima — authenticate y get_user.** Agregar a `src/pacusam/auth.py`:
```python
def authenticate(conn, email: str, password: str) -> dict | None:
    """Devuelve el usuario (sin hash) si las credenciales son válidas; None si no."""
    row = conn.execute(
        "SELECT id, email, password_hash, created_at FROM users WHERE email = ?",
        (email,),
    ).fetchone()
    if row is None:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return _user_dict(row)


def get_user(conn, user_id: int) -> dict | None:
    """Usuario por id (sin hash), o None si no existe."""
    row = conn.execute(
        "SELECT id, email, created_at FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    return _user_dict(row) if row else None
```

- [ ] **Step 4: Correr y ver pasar (suite auth completa).**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth.py -q
```
Salida esperada: `12 passed` (hash x2, db users x2, create_user x3, authenticate x3, get_user x2).

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/auth.py tests/test_auth.py && git commit -m "feat(auth): authenticate y get_user"
```

---

### Task 18: api.py — SessionMiddleware + require_user dependency

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_auth_routes.py`

> Nota de integración: Track A reescribe `create_app` (rutas de proyectos, templates Jinja2, `app.state.conn`). Track C agrega: el `SessionMiddleware`, la dependency `require_user`, y las rutas auth. Este Task asume que `create_app(db_path)` ya existe y monta `app.state.conn = db.connect(db_path)`. Acá montamos el middleware y la dependency, sin pisar lo de Track A.

- [ ] **Step 1: Escribir test que falla — el guard redirige a /login sin sesión.** Crear `tests/test_auth_routes.py`:
```python
"""Tests de endpoints de auth (Track C): registro, login, logout y guard.

Usan TestClient sobre una app fresca con SQLite en memoria. Para HTML/redirects
chequeamos status codes y Location/contenido, no estructura visual.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pacusam.api import create_app


@pytest.fixture
def client():
    # follow_redirects=False para inspeccionar los 302/303 del guard y de las acciones.
    return TestClient(create_app(":memory:"), follow_redirects=False)


def test_guard_redirige_a_login_sin_sesion(client):
    r = client.get("/projects/1")
    assert r.status_code in (302, 303, 307)
    assert r.headers["location"] == "/login"
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q
```
Salida esperada: falla — sin guard, `GET /projects/1` no redirige (`404` o `200`), `assert ... in (302,303,307)` falla (o `KeyError: 'location'`).

- [ ] **Step 3: Implementación — agregar SessionMiddleware y require_user en api.py.** En `src/pacusam/api.py`, en el bloque de imports agregar:
```python
import os

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware

from . import auth, db, services
```
Dentro de `create_app`, justo después de crear `app = FastAPI(...)` y setear `app.state.conn`, agregar el middleware:
```python
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get("PACUSAM_SECRET", "pacusam-dev-secret"),
    )
```
Y definir la dependency `require_user` (después de `get_conn`):
```python
    def require_user(request: Request) -> dict:
        """Auth guard. Devuelve el dict del usuario logueado o redirige a /login."""
        user_id = request.session.get("user_id")
        if not user_id:
            raise _redirect_login()
        user = auth.get_user(app.state.conn, user_id)
        if user is None:
            request.session.clear()
            raise _redirect_login()
        return user
```
Y a nivel módulo (fuera de `create_app`), una excepción de redirección que FastAPI sabe propagar como respuesta. Agregar arriba, junto a `_STATUS`:
```python
class _RedirectException(Exception):
    def __init__(self, location: str):
        self.location = location


def _redirect_login() -> _RedirectException:
    return _RedirectException("/login")
```
Y registrar el handler dentro de `create_app` (antes del `return app`):
```python
    @app.exception_handler(_RedirectException)
    async def _on_redirect(request: Request, exc: _RedirectException):
        return RedirectResponse(exc.location, status_code=303)
```
Para que el test del guard tenga una ruta protegida que tocar, agregar (si Track A aún no la montó) un endpoint mínimo `GET /projects/{id}` que dependa de `require_user`:
```python
    @app.get("/projects/{project_id}", include_in_schema=False)
    def project_page(project_id: int, request: Request, user=Depends(require_user)):
        # Track B reemplaza el cuerpo por el render Jinja2 de project.html.
        return {"project_id": project_id, "user": user["email"]}
```
> Si Track A ya define `GET /projects/{project_id}`, NO dupliques: solo asegurá que su firma incluya `user=Depends(require_user)`.

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q
```
Salida esperada: `1 passed`.

- [ ] **Step 5: Verificar que la suite existente sigue verde.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest -q
```
Salida esperada: todos los tests pasan (auth + auth_routes + curado BDD), sin errores de import.

- [ ] **Step 6: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/api.py tests/test_auth_routes.py && git commit -m "feat(auth): SessionMiddleware + require_user guard (redirige a /login)"
```

---

### Task 19: api.py — POST /register (alta + sesión + redirect, email duplicado muestra error)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_auth_routes.py`

> El front usa formularios HTML (no JSON): los endpoints de auth reciben `Form(...)`. Esto difiere de los endpoints JSON existentes (que usan Pydantic), a propósito — HTMX/forms envían `application/x-www-form-urlencoded`.

- [ ] **Step 1: Escribir test que falla — registro crea usuario, abre sesión y redirige a home.** Agregar a `tests/test_auth_routes.py`:
```python
def test_register_crea_usuario_y_redirige_a_home(client):
    r = client.post(
        "/register",
        data={"email": "ana@hospital.org", "password": "secreto123"},
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    # la sesión quedó abierta: una ruta protegida ya no redirige a login
    r2 = client.get("/projects/1")
    assert r2.status_code not in (302, 303, 307) or r2.headers.get("location") != "/login"


def test_register_email_duplicado_muestra_error(client):
    client.post("/register", data={"email": "ana@hospital.org", "password": "secreto123"})
    r = client.post("/register", data={"email": "ana@hospital.org", "password": "otra"})
    assert r.status_code == 400
    assert "ya está registrado" in r.text.lower() or "email_exists" in r.text.lower()
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q -k register
```
Salida esperada: `405 Method Not Allowed` o `404` en `POST /register` → `assert r.status_code == 303` falla (2 failed).

- [ ] **Step 3: Implementación — POST /register con Form + render de error.** En `src/pacusam/api.py`, agregar `Form` y el render de templates a los imports:
```python
from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.templating import Jinja2Templates
```
Si Track B aún no instanció `templates`, definir dentro de `create_app` (idempotente — si ya existe, reusar el de Track B):
```python
    from pathlib import Path
    templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
```
Agregar la ruta `POST /register` dentro de `create_app`:
```python
    @app.post("/register", include_in_schema=False)
    def register(request: Request, email: str = Form(...), password: str = Form(...)):
        try:
            user = auth.create_user(app.state.conn, email, password)
        except services.DomainError as e:
            msg = "El email ya está registrado" if e.code == "email_exists" else e.code
            return templates.TemplateResponse(
                "register.html",
                {"request": request, "error": msg, "email": email},
                status_code=400,
            )
        request.session["user_id"] = user["id"]
        return RedirectResponse("/", status_code=303)
```

- [ ] **Step 4: Correr y ver fallar por template faltante.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q -k register
```
Salida esperada: `test_register_crea_usuario_y_redirige_a_home` pasa, pero `test_register_email_duplicado_muestra_error` falla con `jinja2.exceptions.TemplateNotFound: register.html` (todavía no existe el template).

- [ ] **Step 5: Crear register.html mínimo para el test de error.** El template completo (extends base.html) se hace en el Task de templates; acá basta uno funcional. Crear `src/pacusam/templates/register.html` (si Track B aún no lo creó):
```html
{% extends "base.html" %}
{% block content %}
<form method="post" action="/register" class="space-y-3">
  {% if error %}<p class="text-rejected">{{ error }}</p>{% endif %}
  <input type="email" name="email" value="{{ email or '' }}" required>
  <input type="password" name="password" required>
  <button type="submit">Crear cuenta</button>
</form>
{% endblock %}
```
> Requiere que `base.html` exista (Track B). Si todavía no existe al correr este step, crear un `base.html` mínimo provisional: `<html><body>{% block content %}{% endblock %}</body></html>` en `src/pacusam/templates/base.html` — Track B lo reemplaza por el layout real.

- [ ] **Step 6: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q -k register
```
Salida esperada: `2 passed`.

- [ ] **Step 7: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/api.py tests/test_auth_routes.py src/pacusam/templates/ && git commit -m "feat(auth): POST /register (alta + sesión + redirect, error de email duplicado)"
```

---

### Task 20: api.py — POST /login y POST /logout

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_auth_routes.py`

- [ ] **Step 1: Escribir test que falla — login válido redirige, inválido muestra error, logout limpia sesión.** Agregar a `tests/test_auth_routes.py`:
```python
def test_login_valido_redirige_a_home(client):
    client.post("/register", data={"email": "ana@hospital.org", "password": "secreto123"})
    # cerramos sesión para probar login limpio
    client.post("/logout")
    r = client.post("/login", data={"email": "ana@hospital.org", "password": "secreto123"})
    assert r.status_code == 303
    assert r.headers["location"] == "/"


def test_login_invalido_muestra_error(client):
    client.post("/register", data={"email": "ana@hospital.org", "password": "secreto123"})
    client.post("/logout")
    r = client.post("/login", data={"email": "ana@hospital.org", "password": "mal"})
    assert r.status_code == 401
    assert "credenciales" in r.text.lower() or "inválid" in r.text.lower()


def test_logout_limpia_sesion(client):
    client.post("/register", data={"email": "ana@hospital.org", "password": "secreto123"})
    r = client.post("/logout")
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
    # tras logout, una ruta protegida vuelve a redirigir a login
    r2 = client.get("/projects/1")
    assert r2.status_code == 303
    assert r2.headers["location"] == "/login"
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q -k "login or logout"
```
Salida esperada: `405`/`404` en `POST /login` y `POST /logout` → asserts de status fallan (3 failed).

- [ ] **Step 3: Implementación — POST /login y POST /logout.** Agregar a `src/pacusam/api.py` dentro de `create_app`:
```python
    @app.post("/login", include_in_schema=False)
    def login(request: Request, email: str = Form(...), password: str = Form(...)):
        user = auth.authenticate(app.state.conn, email, password)
        if user is None:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Credenciales inválidas", "email": email},
                status_code=401,
            )
        request.session["user_id"] = user["id"]
        return RedirectResponse("/", status_code=303)

    @app.post("/logout", include_in_schema=False)
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)
```

- [ ] **Step 4: Crear login.html mínimo para el test de error.** Crear `src/pacusam/templates/login.html` (si Track B aún no lo creó):
```html
{% extends "base.html" %}
{% block content %}
<form method="post" action="/login" class="space-y-3">
  {% if error %}<p class="text-rejected">{{ error }}</p>{% endif %}
  <input type="email" name="email" value="{{ email or '' }}" required>
  <input type="password" name="password" required>
  <button type="submit">Ingresar</button>
</form>
{% endblock %}
```

- [ ] **Step 5: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q -k "login or logout"
```
Salida esperada: `3 passed`.

- [ ] **Step 6: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/api.py tests/test_auth_routes.py src/pacusam/templates/login.html && git commit -m "feat(auth): POST /login (con error de credenciales) y POST /logout"
```

---

### Task 21: api.py — GET /login y GET /register (páginas HTML)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_auth_routes.py`

- [ ] **Step 1: Escribir test que falla — las páginas se sirven sin sesión y son públicas.** Agregar a `tests/test_auth_routes.py`:
```python
def test_get_login_es_publico(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "form" in r.text.lower()


def test_get_register_es_publico(client):
    r = client.get("/register")
    assert r.status_code == 200
    assert "form" in r.text.lower()
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q -k "get_login or get_register"
```
Salida esperada: `404 Not Found` en ambas → `assert r.status_code == 200` falla (2 failed).

- [ ] **Step 3: Implementación — GET /login y GET /register.** Agregar a `src/pacusam/api.py` dentro de `create_app`. Son públicas (NO usan `require_user`); si hay sesión activa, redirigen a home:
```python
    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse("login.html", {"request": request})

    @app.get("/register", include_in_schema=False)
    def register_page(request: Request):
        if request.session.get("user_id"):
            return RedirectResponse("/", status_code=303)
        return templates.TemplateResponse("register.html", {"request": request})
```

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q -k "get_login or get_register"
```
Salida esperada: `2 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/api.py tests/test_auth_routes.py && git commit -m "feat(auth): GET /login y GET /register (páginas públicas, redirigen si hay sesión)"
```

---

### Task 22: templates login.html y register.html (UI final extendiendo base.html)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/login.html`
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/register.html`

> UI: TDD no aplica bien. Pasos de build + verificación manual. Asume que `base.html` (Track B) ya define `{% block content %}`, el head con Tailwind/HTMX/Alpine CDN, y las fonts Inter/Lora/JetBrains Mono. Si `base.html` todavía es el provisional, estos templates igual renderizan; al integrarse con el `base.html` real heredan layout y design system.

- [ ] **Step 1: Escribir login.html final.** Reemplazar `src/pacusam/templates/login.html` con la versión estilada (paleta del design system, card centrada, error visible):
```html
{% extends "base.html" %}
{% block title %}Ingresar · PACUSAM{% endblock %}
{% block content %}
<div class="min-h-[80vh] flex items-center justify-center px-4">
  <div class="w-full max-w-sm bg-white border border-[#E7E4DE] rounded-lg p-8 shadow-sm">
    <h1 class="font-[Lora] text-2xl text-[#1A1A18] mb-1">PACUSAM</h1>
    <p class="text-sm text-[#6B6B66] mb-6">Ingresá para curar imágenes.</p>

    {% if error %}
    <div class="mb-4 px-3 py-2 rounded border border-[#FECACA] bg-[#FEF2F2] text-sm text-[#DC2626]">
      {{ error }}
    </div>
    {% endif %}

    <form method="post" action="/login" class="space-y-4">
      <div>
        <label class="block text-xs font-medium text-[#6B6B66] mb-1" for="email">Email</label>
        <input id="email" type="email" name="email" value="{{ email or '' }}" required autofocus
               class="w-full px-3 py-2 text-sm border border-[#E7E4DE] rounded bg-[#FCFBF9] focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition-colors duration-150">
      </div>
      <div>
        <label class="block text-xs font-medium text-[#6B6B66] mb-1" for="password">Contraseña</label>
        <input id="password" type="password" name="password" required
               class="w-full px-3 py-2 text-sm border border-[#E7E4DE] rounded bg-[#FCFBF9] focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition-colors duration-150">
      </div>
      <button type="submit"
              class="w-full px-3 py-2 text-sm font-medium text-white bg-[#2563EB] hover:bg-[#1D4ED8] rounded transition-colors duration-150">
        Ingresar
      </button>
    </form>

    <p class="mt-6 text-sm text-[#6B6B66] text-center">
      ¿No tenés cuenta?
      <a href="/register" class="text-[#2563EB] hover:text-[#1D4ED8]">Crear cuenta</a>
    </p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Escribir register.html final.** Reemplazar `src/pacusam/templates/register.html`:
```html
{% extends "base.html" %}
{% block title %}Crear cuenta · PACUSAM{% endblock %}
{% block content %}
<div class="min-h-[80vh] flex items-center justify-center px-4">
  <div class="w-full max-w-sm bg-white border border-[#E7E4DE] rounded-lg p-8 shadow-sm">
    <h1 class="font-[Lora] text-2xl text-[#1A1A18] mb-1">Crear cuenta</h1>
    <p class="text-sm text-[#6B6B66] mb-6">Empezá a curar tus datasets.</p>

    {% if error %}
    <div class="mb-4 px-3 py-2 rounded border border-[#FECACA] bg-[#FEF2F2] text-sm text-[#DC2626]">
      {{ error }}
    </div>
    {% endif %}

    <form method="post" action="/register" class="space-y-4">
      <div>
        <label class="block text-xs font-medium text-[#6B6B66] mb-1" for="email">Email</label>
        <input id="email" type="email" name="email" value="{{ email or '' }}" required autofocus
               class="w-full px-3 py-2 text-sm border border-[#E7E4DE] rounded bg-[#FCFBF9] focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition-colors duration-150">
      </div>
      <div>
        <label class="block text-xs font-medium text-[#6B6B66] mb-1" for="password">Contraseña</label>
        <input id="password" type="password" name="password" required minlength="6"
               class="w-full px-3 py-2 text-sm border border-[#E7E4DE] rounded bg-[#FCFBF9] focus:outline-none focus:border-[#2563EB] focus:ring-1 focus:ring-[#2563EB] transition-colors duration-150">
      </div>
      <button type="submit"
              class="w-full px-3 py-2 text-sm font-medium text-white bg-[#2563EB] hover:bg-[#1D4ED8] rounded transition-colors duration-150">
        Crear cuenta
      </button>
    </form>

    <p class="mt-6 text-sm text-[#6B6B66] text-center">
      ¿Ya tenés cuenta?
      <a href="/login" class="text-[#2563EB] hover:text-[#1D4ED8]">Ingresar</a>
    </p>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 3: Verificar que los tests de rutas siguen verdes (los templates renderizan).**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_routes.py -q
```
Salida esperada: `8 passed` (guard, register x2, login x2, logout, get_login, get_register).

- [ ] **Step 4: Verificación manual — arrancar el server.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && PACUSAM_DB=pacusam.db .venv/bin/uvicorn pacusam.api:app --port 8000
```
Abrir `http://localhost:8000/register`. Observar: card centrada sobre fondo `#FCFBF9`, título en Lora, inputs con borde 1px `#E7E4DE`. Crear cuenta `qa@hospital.org / secreto123` → redirige a `/` (home, Track B). Ir a `/logout` no aplica por GET; usar el botón de logout del layout (Track B) o `curl -X POST localhost:8000/logout`. Volver a `/login`, ingresar mal la contraseña → ver banner rojo "Credenciales inválidas". Ingresar bien → home. Cortar con Ctrl-C.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/templates/login.html src/pacusam/templates/register.html && git commit -m "feat(auth): templates login.html y register.html con design system PACUSAM"
```

---

### Task 23: Acceptance BDD — flujo de auth (US-01/02/03)

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/features/auth.feature`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_auth_bdd.py`

> Cierra US-01 (registro), US-02 (login), US-03 (guard/logout) con Gherkin en español, imitando `curado.feature` y su conftest.

- [ ] **Step 1: Escribir el feature (Gherkin en español).** Crear `tests/features/auth.feature`:
```gherkin
# Criterios de aceptación de US-01 (Registro), US-02 (Login) y US-03 (Sesión/guard).
# El sistema autentica curadores antes de dejarlos entrar a sus proyectos.
# language: es

Característica: Autenticación de curadores
  Como curador quiero registrarme e iniciar sesión para acceder a mis proyectos.

  Escenario: Un curador nuevo se registra y queda logueado
    Cuando me registro con email "nuevo@hospital.org" y contraseña "secreto123"
    Entonces soy redirigido al inicio
    Y puedo acceder a una página protegida

  Escenario: No se puede registrar dos veces el mismo email
    Dado un curador registrado con email "dup@hospital.org" y contraseña "secreto123"
    Cuando me registro con email "dup@hospital.org" y contraseña "otra-pass"
    Entonces veo un mensaje de error de registro

  Escenario: Login con credenciales válidas
    Dado un curador registrado con email "ana@hospital.org" y contraseña "secreto123"
    Cuando inicio sesión con email "ana@hospital.org" y contraseña "secreto123"
    Entonces soy redirigido al inicio

  Escenario: Login con contraseña inválida
    Dado un curador registrado con email "ana@hospital.org" y contraseña "secreto123"
    Cuando inicio sesión con email "ana@hospital.org" y contraseña "incorrecta"
    Entonces veo un mensaje de error de credenciales

  Escenario: Sin sesión no se accede a páginas internas
    Cuando intento acceder a una página protegida sin sesión
    Entonces soy redirigido a login
```

- [ ] **Step 2: Escribir los steps + scenarios (test que falla).** Crear `tests/test_auth_bdd.py`:
```python
"""Acceptance BDD de auth (Track C). Corre contra app fresca + SQLite :memory:
vía TestClient, igual que el test de curado. US-01/02/03."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import scenarios, given, when, then, parsers

from pacusam.api import create_app

scenarios("auth.feature")


@pytest.fixture
def client():
    return TestClient(create_app(":memory:"), follow_redirects=False)


@pytest.fixture
def ctx():
    return {"resp": None}


@given(parsers.parse('un curador registrado con email "{email}" y contraseña "{password}"'))
def curador_registrado(client, email, password):
    client.post("/register", data={"email": email, "password": password})
    client.post("/logout")  # dejamos la sesión limpia para los escenarios de login


@when(parsers.parse('me registro con email "{email}" y contraseña "{password}"'))
def me_registro(client, ctx, email, password):
    ctx["resp"] = client.post("/register", data={"email": email, "password": password})


@when(parsers.parse('inicio sesión con email "{email}" y contraseña "{password}"'))
def inicio_sesion(client, ctx, email, password):
    ctx["resp"] = client.post("/login", data={"email": email, "password": password})


@when("intento acceder a una página protegida sin sesión")
def acceso_sin_sesion(client, ctx):
    ctx["resp"] = client.get("/projects/1")


@then("soy redirigido al inicio")
def redirigido_inicio(ctx):
    assert ctx["resp"].status_code == 303
    assert ctx["resp"].headers["location"] == "/"


@then("puedo acceder a una página protegida")
def acceso_protegido_ok(client):
    r = client.get("/projects/1")
    assert r.status_code != 303 or r.headers.get("location") != "/login"


@then("veo un mensaje de error de registro")
def error_registro(ctx):
    assert ctx["resp"].status_code == 400
    assert "registrado" in ctx["resp"].text.lower() or "email_exists" in ctx["resp"].text.lower()


@then("veo un mensaje de error de credenciales")
def error_credenciales(ctx):
    assert ctx["resp"].status_code == 401
    assert "credenciales" in ctx["resp"].text.lower()


@then("soy redirigido a login")
def redirigido_login(ctx):
    assert ctx["resp"].status_code == 303
    assert ctx["resp"].headers["location"] == "/login"
```

- [ ] **Step 3: Correr y ver pasar (la implementación ya existe de los Tasks previos).**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest tests/test_auth_bdd.py -q
```
Salida esperada: `5 passed` (un escenario por bloque del feature).
> Si algún escenario falla por `TemplateNotFound`, es porque `base.html` aún no existe (Track B). En ese caso, el provisional del Task de POST /register cubre el render.

- [ ] **Step 4: Correr la suite completa (regresión global).**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && .venv/bin/python -m pytest -q
```
Salida esperada: todos verdes — auth unit (12) + auth_routes (8) + auth_bdd (5) + curado BDD existente, sin errores de import ni colección.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add tests/features/auth.feature tests/test_auth_bdd.py && git commit -m "test(auth): acceptance BDD de registro/login/guard (US-01/02/03)"
```


## Track D — Projects vertical (home, crear, abrir)

### Task 24: services.list_projects — listar proyectos filtrados por owner

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_projects.py`

> Asume que `db.py` (Track A) ya expone el esquema `users`/`projects`/`images` del contrato y que `auth.create_user` existe. Si todavía no estuvieran, las fixtures de abajo crean filas directamente con SQL para no acoplarse.

- [ ] **Step 1: Escribir test que falla (list vacía + filtro por owner)** — Crear el archivo de test con un helper de inserción directa de proyectos y dos casos: lista vacía y filtrado por owner.

```python
# /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_projects.py
"""Unit tests de la capa de dominio: proyectos (Track D)."""
from __future__ import annotations

import json

import pytest

from pacusam import db, services
from pacusam.services import DomainError


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def _mk_user(conn, email: str) -> int:
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
        (email, "x", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    return cur.lastrowid


def _mk_project(conn, owner_id: int, name: str, labels=("normal", "anomalia")) -> int:
    cur = conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (name, "", owner_id, "radiologia", json.dumps(list(labels)), "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    return cur.lastrowid


def test_list_projects_empty(conn):
    uid = _mk_user(conn, "a@x.com")
    assert services.list_projects(conn, uid) == []


def test_list_projects_filters_by_owner(conn):
    a = _mk_user(conn, "a@x.com")
    b = _mk_user(conn, "b@x.com")
    _mk_project(conn, a, "Proyecto A1")
    _mk_project(conn, a, "Proyecto A2")
    _mk_project(conn, b, "Proyecto B1")

    rows = services.list_projects(conn, a)
    names = {r["name"] for r in rows}
    assert names == {"Proyecto A1", "Proyecto A2"}
    assert all(r["owner_id"] == a for r in rows)
    # labels viene deserializado a list[str]
    assert rows[0]["labels"] == ["normal", "anomalia"]
```

- [ ] **Step 2: Correr y ver fallar** — `services.list_projects` no existe aún.

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_projects.py -q
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'list_projects'` (2 failed).

- [ ] **Step 3: Implementar `list_projects` + helper de serialización** — Agregar al final de `services.py`. Necesitamos `json` arriba del archivo.

En la cabecera de `services.py`, después de `from datetime import datetime, timezone`:
```python
import json
```

Al final de `services.py`:
```python
def _project_row_to_dict(row) -> dict:
    """Normaliza una fila de projects: deserializa labels (JSON array)."""
    d = dict(row)
    d["labels"] = json.loads(d["labels"]) if d.get("labels") else []
    return d


def list_projects(conn, owner_id: int) -> list[dict]:
    """Proyectos de un owner, más recientes primero. labels ya deserializado."""
    rows = conn.execute(
        "SELECT * FROM projects WHERE owner_id = ? ORDER BY created_at DESC, id DESC",
        (owner_id,),
    ).fetchall()
    return [_project_row_to_dict(r) for r in rows]
```

- [ ] **Step 4: Correr y ver pasar**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_projects.py -q
```
Salida esperada: `2 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_projects.py && git commit -m "feat(projects): list_projects filtra por owner y deserializa labels"
```

---

### Task 25: services.create_project — crear con validación de name

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_projects.py`

- [ ] **Step 1: Escribir tests que fallan (happy path + name_required + name_too_long)** — Agregar al final de `tests/test_projects.py`.

```python
def test_create_project_ok(conn):
    uid = _mk_user(conn, "a@x.com")
    p = services.create_project(
        conn, uid, "Tórax 2026", "RX de tórax", "radiologia", ["normal", "anomalia"]
    )
    assert p["id"] >= 1
    assert p["name"] == "Tórax 2026"
    assert p["owner_id"] == uid
    assert p["domain"] == "radiologia"
    assert p["labels"] == ["normal", "anomalia"]
    assert p["created_at"]
    # quedó persistido y lo ve list_projects
    assert services.list_projects(conn, uid)[0]["id"] == p["id"]


def test_create_project_name_required(conn):
    uid = _mk_user(conn, "a@x.com")
    with pytest.raises(DomainError) as e:
        services.create_project(conn, uid, "   ", "d", "radiologia", ["normal"])
    assert e.value.code == "name_required"


def test_create_project_name_too_long(conn):
    uid = _mk_user(conn, "a@x.com")
    with pytest.raises(DomainError) as e:
        services.create_project(conn, uid, "x" * 101, "d", "radiologia", ["normal"])
    assert e.value.code == "name_too_long"
```

- [ ] **Step 2: Correr y ver fallar** — `create_project` no existe.

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_projects.py -q -k create
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'create_project'` (3 failed).

- [ ] **Step 3: Implementar `create_project`** — Agregar al final de `services.py`. Reusa `_now()`, `DomainError`, `_project_row_to_dict` y `json` ya importado.

```python
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
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (cur.lastrowid,)
    ).fetchone()
    return _project_row_to_dict(row)
```

- [ ] **Step 4: Correr y ver pasar**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_projects.py -q
```
Salida esperada: `6 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_projects.py && git commit -m "feat(projects): create_project valida name_required/name_too_long"
```

---

### Task 26: services.get_project — obtener uno o project_not_found

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_projects.py`

- [ ] **Step 1: Escribir tests que fallan (ok + not_found)** — Agregar al final de `tests/test_projects.py`.

```python
def test_get_project_ok(conn):
    uid = _mk_user(conn, "a@x.com")
    pid = _mk_project(conn, uid, "Proyecto A1")
    p = services.get_project(conn, pid)
    assert p["id"] == pid
    assert p["name"] == "Proyecto A1"
    assert p["labels"] == ["normal", "anomalia"]


def test_get_project_not_found(conn):
    with pytest.raises(DomainError) as e:
        services.get_project(conn, 9999)
    assert e.value.code == "project_not_found"
```

- [ ] **Step 2: Correr y ver fallar** — `get_project` no existe.

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_projects.py -q -k get_project
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'get_project'` (2 failed).

- [ ] **Step 3: Implementar `get_project`** — Agregar al final de `services.py`.

```python
def get_project(conn, project_id: int) -> dict:
    """Proyecto por id. DomainError('project_not_found') si no existe."""
    row = conn.execute(
        "SELECT * FROM projects WHERE id = ?", (project_id,)
    ).fetchone()
    if not row:
        raise DomainError("project_not_found", "Proyecto inexistente")
    return _project_row_to_dict(row)
```

- [ ] **Step 4: Correr y ver pasar**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_projects.py -q
```
Salida esperada: `8 passed`.

- [ ] **Step 5: Commit**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_projects.py && git commit -m "feat(projects): get_project -> project_not_found"
```

---

### Task 27: GET / (home) — lista solo los proyectos del usuario logueado

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/base.html`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/home.html`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/project_card.html`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_api_projects.py`

> Asume que Track B/C ya integró `Jinja2Templates`, `SessionMiddleware`, `require_user`, `auth`, y el esquema nuevo de `db.py`. Si la app aún no tiene `require_user`, este test login-ea creando el usuario por `auth.create_user` + seteando sesión vía endpoint de login de Track C. Para no depender del orden de merge, el test usa un helper `_login(client, conn)` que inserta usuario y fuerza la cookie de sesión llamando a `POST /login`.

- [ ] **Step 1: Escribir test que falla (home lista solo proyectos propios; redirect sin sesión)** — Crear el archivo de test.

```python
# /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_api_projects.py
"""Endpoint tests del vertical de proyectos (Track D)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pacusam import auth
from pacusam.api import create_app


@pytest.fixture
def app():
    return create_app(":memory:")


@pytest.fixture
def client(app):
    return TestClient(app, follow_redirects=False)


def _register_and_login(client, email="curador@x.com", password="secreta123"):
    client.post("/register", data={"email": email, "password": password})
    r = client.post("/login", data={"email": email, "password": password})
    assert r.status_code in (302, 303)
    return email


def test_home_requires_login(client):
    r = client.get("/")
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/login"


def test_home_lists_only_my_projects(app, client):
    _register_and_login(client, "a@x.com")
    client.post("/projects", data={"name": "Mío Tórax", "domain": "radiologia",
                                   "labels": "normal,anomalia", "description": ""})
    # un proyecto de OTRO usuario, insertado directo, no debe aparecer
    conn = app.state.conn
    other = auth.create_user(conn, "b@x.com", "secreta123")
    from pacusam import services
    services.create_project(conn, other["id"], "Ajeno", "", "radiologia", ["normal"])

    r = client.get("/")
    assert r.status_code == 200
    assert "Mío Tórax" in r.text
    assert "Ajeno" not in r.text
```

- [ ] **Step 2: Correr y ver fallar** — Las rutas HTML aún no existen / devuelven el `FileResponse` viejo.

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_api_projects.py -q
```
Salida esperada: fallo en `test_home_requires_login` (assert sobre `location`, hoy `/` devuelve 200 FileResponse) y en el listado.

- [ ] **Step 3: Crear `base.html`** — Layout con CDNs del design system.

```html
<!-- /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/base.html -->
<!doctype html>
<html lang="es" class="h-full">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}PACUSAM{% endblock %}</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: { extend: {
        colors: {
          app: "#FCFBF9", surface: "#FFFFFF", surface2: "#F4F2EE", border: "#E7E4DE",
          ink: "#1A1A18", muted: "#6B6B66", faint: "#9C9A94",
          accent: "#2563EB", accentHover: "#1D4ED8", accentTint: "#EFF4FF",
          approved: "#16A34A", approvedTint: "#ECFDF3",
          rejected: "#DC2626", rejectedTint: "#FEF2F2",
          flag: "#D97706", flagTint: "#FFFBEB",
        },
        fontFamily: {
          sans: ["Inter", "ui-sans-serif", "system-ui"],
          display: ["Lora", "ui-serif", "Georgia"],
          mono: ["JetBrains Mono", "ui-monospace", "monospace"],
        },
      }},
    };
  </script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Lora:wght@500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
</head>
<body class="h-full bg-app text-ink font-sans antialiased">
  <header class="border-b border-border bg-surface">
    <div class="mx-auto max-w-5xl px-6 py-3 flex items-center justify-between">
      <a href="/" class="font-display text-lg font-600 text-ink">PACUSAM</a>
      {% if user %}
      <form method="post" action="/logout">
        <button class="text-sm text-muted hover:text-ink transition-colors">Salir</button>
      </form>
      {% endif %}
    </div>
  </header>
  <main class="mx-auto max-w-5xl px-6 py-8">
    {% block content %}{% endblock %}
  </main>
  <script>lucide.createIcons();</script>
</body>
</html>
```

- [ ] **Step 4: Crear `partials/project_card.html`** — Card con barra de progreso (usa `progress()` de Track A/E, pasado por el endpoint como `prog`).

```html
<!-- /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/project_card.html -->
<a href="/projects/{{ p.id }}"
   class="block rounded-lg border border-border bg-surface p-5 hover:border-accent transition-colors duration-150">
  <div class="flex items-start justify-between gap-3">
    <h3 class="font-display text-base font-600 text-ink">{{ p.name }}</h3>
    <span class="text-xs font-mono text-faint">{{ prog.percent }}%</span>
  </div>
  {% if p.description %}
  <p class="mt-1 text-sm text-muted line-clamp-2">{{ p.description }}</p>
  {% endif %}
  <div class="mt-4 h-1.5 w-full rounded-full bg-surface2 overflow-hidden">
    <div class="h-full rounded-full bg-accent transition-all duration-150"
         style="width: {{ prog.percent }}%"></div>
  </div>
  <div class="mt-2 flex items-center gap-3 text-xs text-faint font-mono">
    <span>{{ prog.validated }}/{{ prog.total }} validadas</span>
    <span>{{ prog.pending }} pendientes</span>
  </div>
</a>
```

- [ ] **Step 5: Crear `home.html`** — Grid de cards + formulario de creación (Alpine para abrir/cerrar).

```html
<!-- /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/home.html -->
{% extends "base.html" %}
{% block title %}Proyectos · PACUSAM{% endblock %}
{% block content %}
<div x-data="{ open: false }">
  <div class="flex items-center justify-between">
    <h1 class="font-display text-2xl font-600 text-ink">Proyectos</h1>
    <button @click="open = !open"
            class="inline-flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-500 text-white hover:bg-accentHover transition-colors duration-150">
      <i data-lucide="plus" class="h-4 w-4"></i> Nuevo proyecto
    </button>
  </div>

  {% if flash %}
  <div class="mt-4 rounded-md border border-rejected bg-rejectedTint px-4 py-2 text-sm text-rejected">{{ flash }}</div>
  {% endif %}

  <form x-show="open" x-cloak method="post" action="/projects"
        class="mt-5 rounded-lg border border-border bg-surface p-5 space-y-3">
    <div>
      <label class="block text-sm font-500 text-ink">Nombre</label>
      <input name="name" required maxlength="100"
             class="mt-1 w-full rounded-md border border-border bg-app px-3 py-2 text-sm focus:border-accent focus:outline-none">
    </div>
    <div>
      <label class="block text-sm font-500 text-ink">Descripción</label>
      <input name="description"
             class="mt-1 w-full rounded-md border border-border bg-app px-3 py-2 text-sm focus:border-accent focus:outline-none">
    </div>
    <div class="grid grid-cols-2 gap-3">
      <div>
        <label class="block text-sm font-500 text-ink">Dominio</label>
        <input name="domain" value="radiologia"
               class="mt-1 w-full rounded-md border border-border bg-app px-3 py-2 text-sm focus:border-accent focus:outline-none">
      </div>
      <div>
        <label class="block text-sm font-500 text-ink">Etiquetas (coma)</label>
        <input name="labels" value="normal,anomalia"
               class="mt-1 w-full rounded-md border border-border bg-app px-3 py-2 text-sm font-mono focus:border-accent focus:outline-none">
      </div>
    </div>
    <div class="flex justify-end">
      <button class="rounded-md bg-accent px-4 py-2 text-sm font-500 text-white hover:bg-accentHover transition-colors duration-150">Crear</button>
    </div>
  </form>

  {% if projects %}
  <div class="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
    {% for p in projects %}
      {% set prog = p.progress %}
      {% include "partials/project_card.html" %}
    {% endfor %}
  </div>
  {% else %}
  <div class="mt-10 rounded-lg border border-dashed border-border bg-surface2 p-10 text-center">
    <p class="text-sm text-muted">Todavía no tenés proyectos. Creá el primero para empezar a curar.</p>
  </div>
  {% endif %}
</div>
<style>[x-cloak]{display:none!important}</style>
{% endblock %}
```

- [ ] **Step 6: Implementar la ruta `GET /` en `api.py`** — Reemplazar la `root()` que sirve `index.html`. Asegurar `Jinja2Templates` (lo configura Track B; si no, agregar el bloque). Añadir el directorio de templates y la home con `require_user`.

En la cabecera de `api.py`, junto a los imports existentes:
```python
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
```

Reemplazar el handler viejo:
```python
    @app.get("/", include_in_schema=False)
    def root():
        return FileResponse(_STATIC / "index.html")
```
por:
```python
    @app.get("/", include_in_schema=False, response_class=HTMLResponse)
    def home(request: Request, conn=Depends(get_conn)):
        user = require_user(request)
        if isinstance(user, RedirectResponse):
            return user
        projects = services.list_projects(conn, user["id"])
        for p in projects:
            p["progress"] = services.progress(conn, p["id"])
        return _TEMPLATES.TemplateResponse(
            "home.html", {"request": request, "user": user, "projects": projects,
                          "flash": request.query_params.get("flash")}
        )
```

> `require_user` lo provee Track B con la firma del contrato `require_user(request) -> user dict` (redirige a `/login`). Para que `home` pueda devolver el redirect, asumimos la convención del proyecto: `require_user` lanza/retorna un `RedirectResponse` cuando no hay sesión. Si Track B lo implementa como dependency que lanza excepción, reemplazar las dos primeras líneas del handler por `user = Depends(require_user)` en la firma. Coordinar en el merge; el contrato fija el nombre y el comportamiento de redirect a `/login`.

- [ ] **Step 7: Correr y ver pasar**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_api_projects.py -q -k home
```
Salida esperada: `2 passed`.

- [ ] **Step 8: Verificación manual** — Levantar la app y mirar la home.

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && PACUSAM_DB=demo.db uvicorn pacusam.api:app --reload --port 8000
```
Abrir `http://localhost:8000/` → redirige a `/login`; tras login, ver el grid (vacío con estado "Todavía no tenés proyectos") y el botón "Nuevo proyecto" que despliega el formulario (Alpine). Tipografía Inter/Lora, fondo `#FCFBF9`, bordes 1px.

- [ ] **Step 9: Commit**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/api.py src/pacusam/templates/base.html src/pacusam/templates/home.html src/pacusam/templates/partials/project_card.html tests/test_api_projects.py && git commit -m "feat(projects): home lista proyectos del usuario con barra de progreso"
```

---

### Task 28: POST /projects — crear redirige y aparece; errores se muestran

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_api_projects.py`

- [ ] **Step 1: Escribir tests que fallan (crear redirige + aparece; name vacío muestra error)** — Agregar al final de `tests/test_api_projects.py`.

```python
def test_create_project_redirects_and_appears(client):
    _register_and_login(client, "a@x.com")
    r = client.post("/projects", data={"name": "Tórax 2026", "domain": "radiologia",
                                       "labels": "normal,anomalia", "description": "RX"})
    assert r.status_code in (302, 303)
    assert r.headers["location"] == "/"
    home = client.get("/")
    assert "Tórax 2026" in home.text


def test_create_project_empty_name_shows_error(client):
    _register_and_login(client, "a@x.com")
    r = client.post("/projects", data={"name": "   ", "domain": "radiologia",
                                       "labels": "normal", "description": ""},
                    follow_redirects=True)
    assert r.status_code == 200
    # el flash de error queda visible en la home
    assert "name_required" in r.text or "nombre" in r.text.lower()
```

- [ ] **Step 2: Correr y ver fallar** — No existe `POST /projects`.

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_api_projects.py -q -k "create_project_redirects or empty_name"
```
Salida esperada: `405 Method Not Allowed` / `404` → 2 failed.

- [ ] **Step 3: Extender `_STATUS` y agregar `POST /projects`** — En `api.py`, extender el mapeo de errores y agregar el handler que parsea `labels` (coma), llama a `services.create_project` y en error de dominio redirige a la home con `?flash=`.

Extender `_STATUS` (mantener las claves existentes):
```python
_STATUS = {
    "image_not_found": 404,
    "label_required": 422,
    "name_required": 422,
    "name_too_long": 422,
    "project_not_found": 404,
    "invalid_label": 422,
    "reason_required": 422,
    "email_exists": 409,
}
```

Mensajes legibles para el flash (agregar cerca de `_STATUS`):
```python
_FLASH_MSG = {
    "name_required": "El nombre del proyecto es obligatorio.",
    "name_too_long": "El nombre no puede superar los 100 caracteres.",
}
```

Handler nuevo (dentro de `create_app`, junto a las acciones):
```python
    @app.post("/projects", include_in_schema=False)
    def create_project_action(
        request: Request,
        conn=Depends(get_conn),
        name: str = Form(""),
        description: str = Form(""),
        domain: str = Form(""),
        labels: str = Form(""),
    ):
        user = require_user(request)
        if isinstance(user, RedirectResponse):
            return user
        label_list = [l.strip() for l in labels.split(",") if l.strip()]
        try:
            services.create_project(conn, user["id"], name, description, domain, label_list)
        except services.DomainError as e:
            msg = _FLASH_MSG.get(e.code, e.code)
            return RedirectResponse(f"/?flash={msg}", status_code=303)
        return RedirectResponse("/", status_code=303)
```

Agregar `Form` al import de fastapi:
```python
from fastapi import Depends, FastAPI, Form, HTTPException, Request
```

- [ ] **Step 4: Correr y ver pasar**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_api_projects.py -q
```
Salida esperada: `6 passed` (home x2 + create x2 + requires_login + lists_only_my).

- [ ] **Step 5: Verificación manual** — Con la app corriendo, crear un proyecto desde el formulario → vuelve a `/` y la card aparece con barra al 0%. Enviar con nombre vacío (forzando desde devtools quitando `required`) → vuelve con banner rojo de error.

- [ ] **Step 6: Commit**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/api.py tests/test_api_projects.py && git commit -m "feat(projects): POST /projects crea y redirige; errores de dominio en flash"
```

---

### Task 29: GET /projects/{id} — página de detalle del proyecto

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/project.html`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_api_projects.py`

- [ ] **Step 1: Escribir tests que fallan (detalle muestra nombre/labels + 404)** — Agregar al final de `tests/test_api_projects.py`.

```python
def test_project_detail_shows_name(app, client):
    _register_and_login(client, "a@x.com")
    from pacusam import services
    p = services.create_project(app.state.conn, _uid_of(app, "a@x.com"),
                                "Tórax 2026", "RX de tórax", "radiologia", ["normal", "anomalia"])
    r = client.get(f"/projects/{p['id']}")
    assert r.status_code == 200
    assert "Tórax 2026" in r.text
    assert "normal" in r.text
    # link a curar y a analytics
    assert f"/projects/{p['id']}/curate" in r.text
    assert f"/projects/{p['id']}/analytics" in r.text


def test_project_detail_not_found(client):
    _register_and_login(client, "a@x.com")
    r = client.get("/projects/9999")
    assert r.status_code == 404
```

Agregar también este helper cerca de `_register_and_login`:
```python
def _uid_of(app, email):
    row = app.state.conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    return row["id"]
```

- [ ] **Step 2: Correr y ver fallar** — Ruta inexistente.

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_api_projects.py -q -k "project_detail"
```
Salida esperada: `404` con cuerpo de FastAPI / no contiene el nombre → 1 failed (el de not_found puede pasar por casualidad; el de detalle falla).

- [ ] **Step 3: Crear `project.html`** — Cabecera del proyecto + acciones a curar/analytics + barra de progreso.

```html
<!-- /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/project.html -->
{% extends "base.html" %}
{% block title %}{{ project.name }} · PACUSAM{% endblock %}
{% block content %}
<nav class="text-sm text-muted">
  <a href="/" class="hover:text-ink">Proyectos</a>
  <span class="text-faint">/</span>
  <span class="text-ink">{{ project.name }}</span>
</nav>

<div class="mt-3 flex items-start justify-between gap-4">
  <div>
    <h1 class="font-display text-2xl font-600 text-ink">{{ project.name }}</h1>
    {% if project.description %}
    <p class="mt-1 text-sm text-muted">{{ project.description }}</p>
    {% endif %}
    <div class="mt-3 flex flex-wrap gap-2">
      {% for label in project.labels %}
      <span class="rounded-full border border-border bg-surface2 px-2.5 py-0.5 text-xs font-mono text-muted">{{ label }}</span>
      {% endfor %}
    </div>
  </div>
  <div class="flex gap-2 shrink-0">
    <a href="/projects/{{ project.id }}/analytics"
       class="rounded-md border border-border bg-surface px-4 py-2 text-sm font-500 text-ink hover:border-accent transition-colors duration-150">Analítica</a>
    <a href="/projects/{{ project.id }}/curate"
       class="rounded-md bg-accent px-4 py-2 text-sm font-500 text-white hover:bg-accentHover transition-colors duration-150">Curar</a>
  </div>
</div>

<div class="mt-6 rounded-lg border border-border bg-surface p-5">
  <div class="flex items-center justify-between text-sm">
    <span class="text-muted">Progreso</span>
    <span class="font-mono text-ink">{{ prog.percent }}%</span>
  </div>
  <div class="mt-2 h-2 w-full rounded-full bg-surface2 overflow-hidden">
    <div class="h-full rounded-full bg-accent transition-all duration-150" style="width: {{ prog.percent }}%"></div>
  </div>
  <div class="mt-3 grid grid-cols-3 gap-4 text-center">
    <div><div class="font-mono text-lg text-approved">{{ prog.validated }}</div><div class="text-xs text-faint">validadas</div></div>
    <div><div class="font-mono text-lg text-rejected">{{ prog.rejected }}</div><div class="text-xs text-faint">rechazadas</div></div>
    <div><div class="font-mono text-lg text-ink">{{ prog.pending }}</div><div class="text-xs text-faint">pendientes</div></div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 4: Implementar `GET /projects/{id}` en `api.py`** — Dentro de `create_app`, junto a las páginas HTML.

```python
    @app.get("/projects/{project_id}", include_in_schema=False, response_class=HTMLResponse)
    def project_detail(project_id: int, request: Request, conn=Depends(get_conn)):
        user = require_user(request)
        if isinstance(user, RedirectResponse):
            return user
        try:
            project = services.get_project(conn, project_id)
        except services.DomainError as e:
            raise HTTPException(status_code=_STATUS.get(e.code, 400), detail=e.code)
        prog = services.progress(conn, project_id)
        return _TEMPLATES.TemplateResponse(
            "project.html",
            {"request": request, "user": user, "project": project, "prog": prog},
        )
```

> `progress()` (Track A/E) devuelve `{total, validated, rejected, pending, percent}` — la plantilla usa esas claves del contrato.

- [ ] **Step 5: Correr y ver pasar**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_api_projects.py -q
```
Salida esperada: `8 passed`.

- [ ] **Step 6: Verificación manual** — Con la app corriendo y un proyecto creado, abrir su card → ver detalle con chips de labels, barra de progreso y botones "Curar" / "Analítica". Probar `http://localhost:8000/projects/9999` → 404.

- [ ] **Step 7: Commit**

```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/api.py src/pacusam/templates/project.html tests/test_api_projects.py && git commit -m "feat(projects): detalle de proyecto con progreso y accesos a curar/analítica"
```


## Track E — Curado vertical (cola por incertidumbre, validar, rechazar+motivo, navegación)

### Task 30: services.queue_next — próxima pending ordenada por incertidumbre (1 - confidence DESC)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_queue.py` (create)

Asume que Track A/B ya creó el esquema multi-proyecto de `db.py` (tablas `users`, `projects`, `images` con `project_id`, `reject_reason`, `shown_at`) y `services.create_project` / `services.seed_images(conn, project_id, filenames)`. Este test arma su propia fila de proyecto e imágenes con confidencias fijas vía SQL directo para no depender del clasificador.

- [ ] **Step 1: Escribir el test que falla (orden por incertidumbre).** Crear `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_queue.py`:
```python
"""Unit tests de la cola de curado (Track E): orden por incertidumbre = 1 - confidence."""
from __future__ import annotations

import pytest

from pacusam import db, services


def _project(conn, labels=("normal", "anomalia")):
    conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES ('P', '', 1, 'rx', ?, '2026-01-01T00:00:00+00:00')",
        (services.json.dumps(list(labels)) if hasattr(services, "json") else __import__("json").dumps(list(labels)),),
    )
    conn.commit()
    return conn.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _img(conn, project_id, filename, label, conf, status="pending"):
    conn.execute(
        "INSERT INTO images (project_id, filename, path, suggested_label, confidence, status) "
        "VALUES (?,?,?,?,?,?)",
        (project_id, filename, f"/img/{filename}", label, conf, status),
    )
    conn.commit()
    return conn.execute("SELECT id FROM images ORDER BY id DESC LIMIT 1").fetchone()["id"]


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_queue_next_devuelve_la_mas_incierta_primero(conn):
    pid = _project(conn)
    _img(conn, pid, "alta.dcm", "normal", 0.95)   # incertidumbre 0.05
    _img(conn, pid, "media.dcm", "normal", 0.70)  # incertidumbre 0.30
    _img(conn, pid, "baja.dcm", "anomalia", 0.55)  # incertidumbre 0.45  <- primera
    nxt = services.queue_next(conn, pid)
    assert nxt["filename"] == "baja.dcm"
    assert nxt["confidence"] == 0.55
    assert nxt["suggested_label"] == "anomalia"


def test_queue_next_ignora_no_pending(conn):
    pid = _project(conn)
    _img(conn, pid, "validada.dcm", "normal", 0.51, status="validated")
    _img(conn, pid, "rechazada.dcm", "normal", 0.52, status="rejected")
    _img(conn, pid, "pend.dcm", "normal", 0.99, status="pending")
    nxt = services.queue_next(conn, pid)
    assert nxt["filename"] == "pend.dcm"


def test_queue_next_sin_pendientes_devuelve_none(conn):
    pid = _project(conn)
    _img(conn, pid, "v.dcm", "normal", 0.80, status="validated")
    assert services.queue_next(conn, pid) is None
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_queue.py -q
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'queue_next'` (3 failed / errors).

- [ ] **Step 3: Implementar `queue_next` (mínimo).** En `services.py`, agregar `import json` al tope (junto a los imports existentes) si no está, y agregar la función:
```python
def queue_next(conn, project_id: int) -> dict | None:
    """Próxima imagen 'pending' del proyecto, ordenada por incertidumbre = 1 - confidence DESC.

    Empate -> desempata por id ASC (estable). Devuelve None si no quedan pendientes.
    Incluye remaining_pending para que el front muestre cuántas faltan.
    """
    row = conn.execute(
        "SELECT * FROM images WHERE project_id = ? AND status = 'pending' "
        "ORDER BY (1.0 - confidence) DESC, id ASC LIMIT 1",
        (project_id,),
    ).fetchone()
    if not row:
        return None
    remaining = conn.execute(
        "SELECT COUNT(*) c FROM images WHERE project_id = ? AND status = 'pending'",
        (project_id,),
    ).fetchone()["c"]
    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "filename": row["filename"],
        "path": row["path"],
        "suggested_label": row["suggested_label"],
        "confidence": row["confidence"],
        "uncertainty": round(1.0 - row["confidence"], 2),
        "remaining_pending": remaining,
    }
```

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_queue.py -q
```
Salida esperada: `3 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_curate_queue.py && git commit -m "feat(curate): queue_next ordena pending por incertidumbre 1-confidence"
```

### Task 31: services.queue_list — filmstrip con todas las imágenes ordenadas por incertidumbre

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_queue.py` (modify)

- [ ] **Step 1: Escribir el test que falla.** Agregar al final de `tests/test_curate_queue.py`:
```python
def test_queue_list_devuelve_todas_ordenadas_por_incertidumbre_con_status(conn):
    pid = _project(conn)
    _img(conn, pid, "alta.dcm", "normal", 0.95, status="validated")  # inc 0.05
    _img(conn, pid, "baja.dcm", "anomalia", 0.55, status="pending")  # inc 0.45
    _img(conn, pid, "media.dcm", "normal", 0.70, status="rejected")  # inc 0.30
    items = services.queue_list(conn, pid)
    assert [i["filename"] for i in items] == ["baja.dcm", "media.dcm", "alta.dcm"]
    assert [i["status"] for i in items] == ["pending", "rejected", "validated"]
    assert items[0]["uncertainty"] == 0.45


def test_queue_list_aisla_por_proyecto(conn):
    p1 = _project(conn)
    p2 = _project(conn)
    _img(conn, p1, "a.dcm", "normal", 0.80)
    _img(conn, p2, "b.dcm", "normal", 0.80)
    items = services.queue_list(conn, p1)
    assert [i["filename"] for i in items] == ["a.dcm"]
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_queue.py -q -k queue_list
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'queue_list'` (2 errors).

- [ ] **Step 3: Implementar `queue_list`.** En `services.py`, debajo de `queue_next`:
```python
def queue_list(conn, project_id: int) -> list[dict]:
    """Todas las imágenes del proyecto, ordenadas por incertidumbre DESC (para el filmstrip).
    Incluye su status para que el front pinte validadas/rechazadas/pendientes."""
    rows = conn.execute(
        "SELECT id, filename, path, suggested_label, confidence, status, final_label "
        "FROM images WHERE project_id = ? ORDER BY (1.0 - confidence) DESC, id ASC",
        (project_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "filename": r["filename"],
            "path": r["path"],
            "suggested_label": r["suggested_label"],
            "confidence": r["confidence"],
            "uncertainty": round(1.0 - r["confidence"], 2),
            "status": r["status"],
            "final_label": r["final_label"],
        }
        for r in rows
    ]
```

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_queue.py -q
```
Salida esperada: `5 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_curate_queue.py && git commit -m "feat(curate): queue_list para filmstrip ordenado por incertidumbre con status"
```

### Task 32: services.validate_image — valida label contra labels del proyecto

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_actions.py` (create)

El `validate_image` existente NO valida contra las labels del proyecto. Este task lo reescribe para confirmar/corregir solo dentro de las labels del proyecto y setear `validated_at`.

- [ ] **Step 1: Escribir el test que falla.** Crear `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_actions.py`:
```python
"""Unit tests de acciones de curado (Track E): validar / rechazar / unreject."""
from __future__ import annotations

import json

import pytest

from pacusam import db, services


def _project(conn, labels=("normal", "anomalia")):
    conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES ('P', '', 1, 'rx', ?, '2026-01-01T00:00:00+00:00')",
        (json.dumps(list(labels)),),
    )
    conn.commit()
    return conn.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1").fetchone()["id"]


def _img(conn, project_id, filename="x.dcm", label="normal", conf=0.6, status="pending"):
    conn.execute(
        "INSERT INTO images (project_id, filename, path, suggested_label, confidence, status) "
        "VALUES (?,?,?,?,?,?)",
        (project_id, filename, f"/img/{filename}", label, conf, status),
    )
    conn.commit()
    return conn.execute("SELECT id FROM images ORDER BY id DESC LIMIT 1").fetchone()["id"]


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_validate_confirma_la_sugerencia(conn):
    pid = _project(conn)
    iid = _img(conn, pid, label="normal")
    out = services.validate_image(conn, iid, "normal")
    assert out["status"] == "validated"
    assert out["final_label"] == "normal"
    assert out["validated_at"]
    row = conn.execute("SELECT status, final_label FROM images WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "validated" and row["final_label"] == "normal"


def test_validate_corrige_a_otra_label_del_proyecto(conn):
    pid = _project(conn)
    iid = _img(conn, pid, label="normal")
    out = services.validate_image(conn, iid, "anomalia")
    assert out["final_label"] == "anomalia"


def test_validate_rechaza_label_fuera_del_proyecto(conn):
    pid = _project(conn)
    iid = _img(conn, pid)
    with pytest.raises(services.DomainError) as e:
        services.validate_image(conn, iid, "fractura")
    assert e.value.code == "invalid_label"


def test_validate_label_requerida(conn):
    pid = _project(conn)
    iid = _img(conn, pid)
    with pytest.raises(services.DomainError) as e:
        services.validate_image(conn, iid, "   ")
    assert e.value.code == "label_required"


def test_validate_imagen_inexistente(conn):
    with pytest.raises(services.DomainError) as e:
        services.validate_image(conn, 999, "normal")
    assert e.value.code == "image_not_found"
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_actions.py -q
```
Salida esperada: el test de `invalid_label` falla (`DomainError not raised` / la firma vieja no valida labels) y/o `sqlite3.OperationalError` por columnas nuevas. Al menos `test_validate_rechaza_label_fuera_del_proyecto FAILED`.

- [ ] **Step 3: Implementar.** En `services.py`, agregar helper de labels y reescribir `validate_image`. Asegurar `import json` al tope:
```python
def _project_labels(conn, project_id: int) -> list[str]:
    row = conn.execute("SELECT labels FROM projects WHERE id = ?", (project_id,)).fetchone()
    if not row:
        raise DomainError("project_not_found", "Proyecto inexistente")
    return json.loads(row["labels"])


def _image_row(conn, image_id: int):
    row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
    if not row:
        raise DomainError("image_not_found", "Imagen inexistente")
    return row


def validate_image(conn, image_id: int, label: str) -> dict:
    """US-10/11. Confirma o corrige la sugerencia; valida contra las labels del proyecto."""
    row = _image_row(conn, image_id)
    if not (label or "").strip():
        raise DomainError("label_required", "La etiqueta es obligatoria")
    if label not in _project_labels(conn, row["project_id"]):
        raise DomainError("invalid_label", "Etiqueta fuera del proyecto")
    ts = _now()
    conn.execute(
        "UPDATE images SET status='validated', final_label=?, reject_reason=NULL, validated_at=? "
        "WHERE id=?",
        (label, ts, image_id),
    )
    conn.commit()
    return {"id": image_id, "status": "validated", "final_label": label, "validated_at": ts}
```

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_actions.py -q
```
Salida esperada: `5 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_curate_actions.py && git commit -m "feat(curate): validate_image valida label contra labels del proyecto"
```

### Task 33: services.reject_image — rechazo con motivo obligatorio

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_actions.py` (modify)

- [ ] **Step 1: Escribir el test que falla.** Agregar al final de `tests/test_curate_actions.py`:
```python
def test_reject_setea_status_y_motivo(conn):
    pid = _project(conn)
    iid = _img(conn, pid)
    out = services.reject_image(conn, iid, "imagen borrosa")
    assert out["status"] == "rejected"
    assert out["reject_reason"] == "imagen borrosa"
    row = conn.execute("SELECT status, reject_reason FROM images WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "rejected" and row["reject_reason"] == "imagen borrosa"


def test_reject_motivo_requerido(conn):
    pid = _project(conn)
    iid = _img(conn, pid)
    with pytest.raises(services.DomainError) as e:
        services.reject_image(conn, iid, "  ")
    assert e.value.code == "reason_required"


def test_reject_imagen_inexistente(conn):
    with pytest.raises(services.DomainError) as e:
        services.reject_image(conn, 999, "motivo")
    assert e.value.code == "image_not_found"


def test_reject_excluye_de_la_cola(conn):
    pid = _project(conn)
    iid = _img(conn, pid, filename="rej.dcm", conf=0.55)
    _img(conn, pid, filename="keep.dcm", conf=0.60)
    services.reject_image(conn, iid, "motivo")
    nxt = services.queue_next(conn, pid)
    assert nxt["filename"] == "keep.dcm"
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_actions.py -q -k reject
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'reject_image'` (4 errors).

- [ ] **Step 3: Implementar `reject_image`.** En `services.py`, debajo de `validate_image`:
```python
def reject_image(conn, image_id: int, reason: str) -> dict:
    """US-12. Marca la imagen como rechazada con un motivo (excluye de la cola)."""
    _image_row(conn, image_id)
    if not (reason or "").strip():
        raise DomainError("reason_required", "El motivo es obligatorio")
    conn.execute(
        "UPDATE images SET status='rejected', reject_reason=?, final_label=NULL, validated_at=? "
        "WHERE id=?",
        (reason.strip(), _now(), image_id),
    )
    conn.commit()
    return {"id": image_id, "status": "rejected", "reject_reason": reason.strip()}
```

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_actions.py -q
```
Salida esperada: `9 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_curate_actions.py && git commit -m "feat(curate): reject_image con motivo obligatorio que excluye de la cola"
```

### Task 34: services.unreject_image — revertir rechazo a pending

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_actions.py` (modify)

- [ ] **Step 1: Escribir el test que falla.** Agregar al final de `tests/test_curate_actions.py`:
```python
def test_unreject_vuelve_a_pending(conn):
    pid = _project(conn)
    iid = _img(conn, pid)
    services.reject_image(conn, iid, "borrosa")
    out = services.unreject_image(conn, iid)
    assert out["status"] == "pending"
    row = conn.execute("SELECT status, reject_reason FROM images WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "pending" and row["reject_reason"] is None


def test_unreject_reaparece_en_la_cola(conn):
    pid = _project(conn)
    iid = _img(conn, pid, conf=0.55)
    services.reject_image(conn, iid, "borrosa")
    assert services.queue_next(conn, pid) is None
    services.unreject_image(conn, iid)
    assert services.queue_next(conn, pid)["id"] == iid


def test_unreject_imagen_inexistente(conn):
    with pytest.raises(services.DomainError) as e:
        services.unreject_image(conn, 999)
    assert e.value.code == "image_not_found"
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_actions.py -q -k unreject
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'unreject_image'` (3 errors).

- [ ] **Step 3: Implementar `unreject_image`.** En `services.py`, debajo de `reject_image`:
```python
def unreject_image(conn, image_id: int) -> dict:
    """Revierte un rechazo: la imagen vuelve a 'pending' y reaparece en la cola."""
    _image_row(conn, image_id)
    conn.execute(
        "UPDATE images SET status='pending', reject_reason=NULL, final_label=NULL, validated_at=NULL "
        "WHERE id=?",
        (image_id,),
    )
    conn.commit()
    return {"id": image_id, "status": "pending"}
```

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_actions.py -q
```
Salida esperada: `12 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_curate_actions.py && git commit -m "feat(curate): unreject_image revierte rechazo a pending"
```

### Task 35: services.progress — métricas por proyecto (total/validated/rejected/pending/percent)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_actions.py` (modify)

El `progress` existente es global y no separa `rejected`. Este task lo reescribe a la firma pinneada `progress(conn, project_id)` con `{total, validated, rejected, pending, percent}` donde `percent = (validated+rejected)/total` (avance del curado: cuántas imágenes ya fueron decididas).

- [ ] **Step 1: Escribir el test que falla.** Agregar al final de `tests/test_curate_actions.py`:
```python
def test_progress_cuenta_por_estado_y_porcentaje(conn):
    pid = _project(conn)
    a = _img(conn, pid, filename="a.dcm")
    b = _img(conn, pid, filename="b.dcm")
    _img(conn, pid, filename="c.dcm")
    _img(conn, pid, filename="d.dcm")
    services.validate_image(conn, a, "normal")
    services.reject_image(conn, b, "borrosa")
    prog = services.progress(conn, pid)
    assert prog["total"] == 4
    assert prog["validated"] == 1
    assert prog["rejected"] == 1
    assert prog["pending"] == 2
    assert prog["percent"] == 50.0  # (1 validated + 1 rejected) / 4


def test_progress_proyecto_vacio(conn):
    pid = _project(conn)
    prog = services.progress(conn, pid)
    assert prog == {"total": 0, "validated": 0, "rejected": 0, "pending": 0, "percent": 0.0}
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_actions.py -q -k progress
```
Salida esperada: `TypeError: progress() takes 1 positional argument but 2 were given` (2 errors).

- [ ] **Step 3: Reescribir `progress`.** En `services.py`, reemplazar la función `progress` existente por:
```python
def progress(conn, project_id: int) -> dict:
    """Avance del curado del proyecto: total / validated / rejected / pending + percent decidido."""
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
```

- [ ] **Step 4: Correr y ver pasar (este módulo).**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_actions.py -q
```
Salida esperada: `14 passed`.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/services.py tests/test_curate_actions.py && git commit -m "feat(curate): progress por proyecto con validated/rejected/pending/percent"
```

### Task 36: API — rutas de acción de curado (validate/reject/unreject) + mapeo de errores

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_api.py` (create)

Asume que Track B ya montó `require_user`, `SessionMiddleware`, registro/login y `create_app` con templates Jinja2. Este task agrega las rutas de acción de curado y extiende `_STATUS`. El test crea usuario+proyecto vía las rutas existentes y autentica con el TestClient (cookies persistentes).

- [ ] **Step 1: Escribir el test que falla.** Crear `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_api.py`:
```python
"""Tests de API de las acciones de curado (Track E). TestClient con sesión real."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pacusam.api import create_app


@pytest.fixture
def client():
    c = TestClient(create_app(":memory:"))
    c.post("/register", data={"email": "c@x.io", "password": "secret123"}, follow_redirects=False)
    c.post("/login", data={"email": "c@x.io", "password": "secret123"}, follow_redirects=False)
    return c


def _make_project(client) -> int:
    r = client.post(
        "/projects",
        data={"name": "Torax", "description": "", "domain": "rx", "labels": "normal,anomalia"},
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    # /projects redirige a /projects/{id}: extraer el id del Location
    loc = r.headers["location"]
    return int(loc.rstrip("/").split("/")[-1])


def _seed_one(client, conn_app, project_id):
    # sembrar directo en la conexión de la app para tener un image_id conocido
    conn = conn_app.state.conn
    conn.execute(
        "INSERT INTO images (project_id, filename, path, suggested_label, confidence, status) "
        "VALUES (?, 'x.dcm', '/img/x.dcm', 'normal', 0.55, 'pending')",
        (project_id,),
    )
    conn.commit()
    return conn.execute("SELECT id FROM images ORDER BY id DESC LIMIT 1").fetchone()["id"]


def test_validate_ok_devuelve_fragmento(client):
    app = client.app
    pid = _make_project(client)
    iid = _seed_one(client, app, pid)
    r = client.post(f"/images/{iid}/validate", data={"label": "normal"}, follow_redirects=False)
    assert r.status_code == 200
    assert "validated" in r.text.lower() or "normal" in r.text.lower()


def test_validate_label_invalida_422(client):
    app = client.app
    pid = _make_project(client)
    iid = _seed_one(client, app, pid)
    r = client.post(f"/images/{iid}/validate", data={"label": "fractura"}, follow_redirects=False)
    assert r.status_code == 422


def test_validate_imagen_inexistente_404(client):
    r = client.post("/images/9999/validate", data={"label": "normal"}, follow_redirects=False)
    assert r.status_code == 404


def test_reject_sin_motivo_422(client):
    app = client.app
    pid = _make_project(client)
    iid = _seed_one(client, app, pid)
    r = client.post(f"/images/{iid}/reject", data={"reason": ""}, follow_redirects=False)
    assert r.status_code == 422


def test_reject_y_unreject(client):
    app = client.app
    pid = _make_project(client)
    iid = _seed_one(client, app, pid)
    r = client.post(f"/images/{iid}/reject", data={"reason": "borrosa"}, follow_redirects=False)
    assert r.status_code == 200
    r2 = client.post(f"/images/{iid}/unreject", follow_redirects=False)
    assert r2.status_code == 200


def test_acciones_requieren_login():
    anon = TestClient(create_app(":memory:"))
    r = anon.post("/images/1/validate", data={"label": "normal"}, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/login" in r.headers["location"]
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_api.py -q
```
Salida esperada: fallos `404`/`405` en las rutas `/images/{id}/validate|reject|unreject` (no existen aún).

- [ ] **Step 3: Implementar las rutas.** En `api.py`, extender `_STATUS` y agregar las rutas dentro de `create_app` (usando `require_user`, `templates` y `_guard` que provee Track B). Extender el mapeo de errores:
```python
_STATUS = {
    "image_not_found": 404,
    "project_not_found": 404,
    "label_required": 422,
    "invalid_label": 422,
    "reason_required": 422,
    "name_required": 422,
    "name_too_long": 422,
    "email_exists": 409,
}
```
Agregar las rutas (renderizan el partial `image_card` con la próxima imagen para auto-avance HTMX):
```python
    @app.post("/images/{image_id}/validate")
    def validate(image_id: int, request: Request, label: str = Form(...),
                 user=Depends(require_user), conn=Depends(get_conn)):
        img = services.get_image(conn, image_id)
        project_id = img["project_id"]
        _guard(services.validate_image, conn, image_id, label)
        return _render_next_card(request, conn, project_id)

    @app.post("/images/{image_id}/reject")
    def reject(image_id: int, request: Request, reason: str = Form(""),
               user=Depends(require_user), conn=Depends(get_conn)):
        img = services.get_image(conn, image_id)
        project_id = img["project_id"]
        _guard(services.reject_image, conn, image_id, reason)
        return _render_next_card(request, conn, project_id)

    @app.post("/images/{image_id}/unreject")
    def unreject(image_id: int, request: Request,
                 user=Depends(require_user), conn=Depends(get_conn)):
        img = services.get_image(conn, image_id)
        project_id = img["project_id"]
        _guard(services.unreject_image, conn, image_id)
        return _render_next_card(request, conn, project_id)
```
Agregar el helper de render del fragmento (arriba de las rutas, dentro de `create_app`):
```python
    def _render_next_card(request: Request, conn, project_id: int):
        nxt = services.queue_next(conn, project_id)
        prog = services.progress(conn, project_id)
        labels = services.get_project(conn, project_id)["labels"]
        return templates.TemplateResponse(
            "partials/image_card.html",
            {"request": request, "image": nxt, "progress": prog,
             "labels": labels, "project_id": project_id},
        )
```
Asegurar imports al tope de `api.py`: `from fastapi import Depends, FastAPI, Form, HTTPException, Request`.

- [ ] **Step 4: Agregar `services.get_image` (dependencia mínima del API).** En `services.py`, debajo de `_image_row`:
```python
def get_image(conn, image_id: int) -> dict:
    """Devuelve la imagen como dict; DomainError('image_not_found') si no existe."""
    row = _image_row(conn, image_id)
    return dict(row)
```

- [ ] **Step 5: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_api.py -q
```
Salida esperada: `6 passed` (requiere que existan los templates `partials/image_card.html`, `curate.html` y `require_user`; si el render del partial falla por template ausente, completar primero la task de templates de abajo y re-correr).

- [ ] **Step 6: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/api.py src/pacusam/services.py tests/test_curate_api.py && git commit -m "feat(curate): rutas validate/reject/unreject con auto-avance HTMX y mapeo de errores"
```

### Task 37: API — página GET /curate y fragmento GET /queue + GET /progress

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curate_api.py` (modify)

- [ ] **Step 1: Escribir el test que falla.** Agregar al final de `tests/test_curate_api.py`:
```python
def test_pagina_curate_renderiza(client):
    app = client.app
    pid = _make_project(client)
    _seed_one(client, app, pid)
    r = client.get(f"/projects/{pid}/curate")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_queue_fragmento_trae_imagen_mas_incierta(client):
    app = client.app
    pid = _make_project(client)
    _seed_one(client, app, pid)  # x.dcm conf 0.55
    r = client.get(f"/projects/{pid}/queue")
    assert r.status_code == 200
    assert "x.dcm" in r.text


def test_progress_endpoint_json(client):
    app = client.app
    pid = _make_project(client)
    _seed_one(client, app, pid)
    r = client.get(f"/progress?project_id={pid}")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["pending"] == 1


def test_curate_requiere_login():
    anon = TestClient(create_app(":memory:"))
    r = anon.get("/projects/1/curate", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert "/login" in r.headers["location"]
```

- [ ] **Step 2: Correr y ver fallar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_api.py -q -k "curate or queue or progress_endpoint"
```
Salida esperada: `404` en `/projects/{id}/curate`, `/projects/{id}/queue` y `/progress` (no existen aún).

- [ ] **Step 3: Implementar las rutas.** En `api.py`, dentro de `create_app`:
```python
    @app.get("/projects/{project_id}/curate")
    def curate_page(project_id: int, request: Request,
                    user=Depends(require_user), conn=Depends(get_conn)):
        project = _guard(services.get_project, conn, project_id)
        nxt = services.queue_next(conn, project_id)
        return templates.TemplateResponse(
            "curate.html",
            {"request": request, "user": user, "project": project,
             "image": nxt, "labels": project["labels"],
             "filmstrip": services.queue_list(conn, project_id),
             "progress": services.progress(conn, project_id),
             "project_id": project_id},
        )

    @app.get("/projects/{project_id}/queue")
    def queue_fragment(project_id: int, request: Request,
                       user=Depends(require_user), conn=Depends(get_conn)):
        _guard(services.get_project, conn, project_id)
        return _render_next_card(request, conn, project_id)

    @app.get("/progress")
    def get_progress(project_id: int, user=Depends(require_user), conn=Depends(get_conn)):
        _guard(services.get_project, conn, project_id)
        return services.progress(conn, project_id)
```

- [ ] **Step 4: Correr y ver pasar.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curate_api.py -q
```
Salida esperada: `10 passed` (depende de los templates `curate.html` + `partials/image_card.html` de la task siguiente; si fallan por template ausente, completarla y re-correr).

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/api.py tests/test_curate_api.py && git commit -m "feat(curate): GET /curate (pagina), GET /queue (fragmento HTMX) y GET /progress"
```

### Task 38: Template partials — image_card, confidence_bar, filmstrip, progress_bar

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/image_card.html`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/filmstrip.html`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/progress_bar.html`

Esta es una task de UI (TDD no aplica): build + verificación manual. Asume que Track B creó `base.html` y el `templates = Jinja2Templates(directory=...)` apunta a `src/pacusam/templates`. Usa la paleta pinneada (accent `#2563EB`, approved `#16A34A`, rejected `#DC2626`, flag `#D97706`) vía clases Tailwind CDN y fuentes Inter/JetBrains Mono.

- [ ] **Step 1: Crear `partials/image_card.html`** (la imagen actual + confidence bar + action bar con hotkeys A/C/R, panel de rechazo Alpine, auto-avance HTMX). El partial se re-renderiza tras cada acción y se inyecta vía `hx-target="#image-card" hx-swap="outerHTML"`:
```html
<div id="image-card" class="flex flex-col gap-4"
     x-data="{ rejecting: false, reason: '' }"
     @keydown.window.a.prevent="$refs.confirmBtn && $refs.confirmBtn.click()"
     @keydown.window.r.prevent="rejecting = true">
{% if image %}
  <div class="bg-white border border-[#E7E4DE] rounded-lg overflow-hidden">
    <div class="aspect-video bg-[#F4F2EE] flex items-center justify-center">
      <span class="font-mono text-sm text-[#9C9A94]">{{ image.filename }}</span>
    </div>
    <div class="p-4 flex flex-col gap-3">
      <div class="flex items-center justify-between">
        <span class="font-mono text-sm text-[#6B6B66]">{{ image.filename }}</span>
        <span class="text-xs text-[#9C9A94]">{{ image.remaining_pending }} pendientes</span>
      </div>

      {# confidence_bar #}
      <div>
        <div class="flex items-center justify-between text-xs mb-1">
          <span class="text-[#6B6B66]">Sugerencia: <strong class="text-[#1A1A18]">{{ image.suggested_label }}</strong></span>
          <span class="font-mono text-[#6B6B66]">{{ (image.confidence * 100) | round(0) | int }}%</span>
        </div>
        <div class="h-2 w-full bg-[#F4F2EE] rounded-full overflow-hidden">
          <div class="h-full rounded-full transition-all duration-150
                      {% if image.confidence >= 0.9 %}bg-[#16A34A]{% elif image.confidence < 0.6 %}bg-[#D97706]{% else %}bg-[#2563EB]{% endif %}"
               style="width: {{ (image.confidence * 100) | round(0) | int }}%"></div>
        </div>
        {% if image.confidence < 0.6 %}
          <p class="text-xs text-[#D97706] mt-1">Baja confianza — revisar con atención.</p>
        {% endif %}
      </div>

      {# action bar — confirmar / corregir / rechazar #}
      <div class="flex flex-wrap gap-2" x-show="!rejecting">
        <button x-ref="confirmBtn"
                hx-post="/images/{{ image.id }}/validate"
                hx-vals='{"label": "{{ image.suggested_label }}"}'
                hx-target="#image-card" hx-swap="outerHTML"
                class="px-3 py-2 text-sm rounded-md bg-[#16A34A] text-white hover:opacity-90 transition">
          Confirmar (A) · {{ image.suggested_label }}
        </button>
        {% for label in labels if label != image.suggested_label %}
          <button hx-post="/images/{{ image.id }}/validate"
                  hx-vals='{"label": "{{ label }}"}'
                  hx-target="#image-card" hx-swap="outerHTML"
                  class="px-3 py-2 text-sm rounded-md bg-[#EFF4FF] text-[#2563EB] hover:bg-[#2563EB] hover:text-white transition">
            Corregir → {{ label }} (C)
          </button>
        {% endfor %}
        <button @click="rejecting = true"
                class="px-3 py-2 text-sm rounded-md bg-[#FEF2F2] text-[#DC2626] hover:bg-[#DC2626] hover:text-white transition">
          Rechazar (R)
        </button>
      </div>

      {# panel de rechazo con motivos de lista #}
      <form x-show="rejecting" x-cloak
            hx-post="/images/{{ image.id }}/reject"
            hx-target="#image-card" hx-swap="outerHTML"
            class="flex flex-col gap-2 border-t border-[#E7E4DE] pt-3">
        <label class="text-xs text-[#6B6B66]">Motivo del rechazo</label>
        <select name="reason" x-model="reason"
                class="border border-[#E7E4DE] rounded-md px-2 py-2 text-sm bg-white">
          <option value="">Elegí un motivo…</option>
          <option>Imagen borrosa o de baja calidad</option>
          <option>Artefactos / posicionamiento incorrecto</option>
          <option>Fuera del dominio del proyecto</option>
          <option>Duplicada</option>
          <option>Datos sensibles visibles</option>
        </select>
        <div class="flex gap-2">
          <button type="submit" :disabled="!reason"
                  class="px-3 py-2 text-sm rounded-md bg-[#DC2626] text-white disabled:opacity-40 transition">
            Confirmar rechazo
          </button>
          <button type="button" @click="rejecting = false"
                  class="px-3 py-2 text-sm rounded-md bg-[#F4F2EE] text-[#6B6B66] transition">
            Cancelar
          </button>
        </div>
      </form>
    </div>
  </div>
{% else %}
  <div class="bg-[#ECFDF3] border border-[#16A34A] rounded-lg p-8 text-center">
    <p class="font-[Lora] text-lg text-[#16A34A]">Cola completa</p>
    <p class="text-sm text-[#6B6B66] mt-1">No quedan imágenes pendientes en este proyecto.</p>
    <a href="/projects/{{ project_id }}/analytics"
       class="inline-block mt-3 px-3 py-2 text-sm rounded-md bg-[#2563EB] text-white">Ver analytics</a>
  </div>
{% endif %}

  {# progress bar se actualiza fuera de banda en cada swap #}
  {% include "partials/progress_bar.html" %}
</div>
```

- [ ] **Step 2: Crear `partials/progress_bar.html`** (con `hx-swap-oob` para refrescarse en cada acción):
```html
<div id="progress-bar" hx-swap-oob="true" class="mt-2">
  <div class="flex items-center justify-between text-xs text-[#6B6B66] mb-1">
    <span>{{ progress.validated }} validadas · {{ progress.rejected }} rechazadas · {{ progress.pending }} pendientes</span>
    <span class="font-mono">{{ progress.percent }}%</span>
  </div>
  <div class="h-2 w-full bg-[#F4F2EE] rounded-full overflow-hidden">
    <div class="h-full bg-[#2563EB] rounded-full transition-all duration-150"
         style="width: {{ progress.percent }}%"></div>
  </div>
</div>
```

- [ ] **Step 3: Crear `partials/filmstrip.html`** (tira de miniaturas ordenada por incertidumbre, status coloreado, click navega):
```html
<div id="filmstrip" class="flex gap-2 overflow-x-auto py-2">
  {% for item in filmstrip %}
    <div class="flex-shrink-0 w-20 border rounded-md p-1 text-center
                {% if item.status == 'validated' %}border-[#16A34A] bg-[#ECFDF3]
                {% elif item.status == 'rejected' %}border-[#DC2626] bg-[#FEF2F2]
                {% else %}border-[#E7E4DE] bg-white{% endif %}">
      <div class="h-12 bg-[#F4F2EE] rounded flex items-center justify-center">
        <span class="font-mono text-[9px] text-[#9C9A94] truncate px-1">{{ item.filename }}</span>
      </div>
      <span class="block text-[9px] font-mono mt-1 text-[#6B6B66]">u {{ item.uncertainty }}</span>
    </div>
  {% endfor %}
</div>
```

- [ ] **Step 4: Build + verificación manual.** Levantar la app y abrir la página de curado:
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && PACUSAM_DB=:memory: python -m uvicorn pacusam.api:app --port 8011
```
Abrir `http://localhost:8011/login`, registrarse/loguear, crear un proyecto, sembrar imágenes (vía la UI de Track C/D) y abrir `/projects/1/curate`. Observar: imagen grande con `confidence_bar` (verde si ≥90%, ámbar si <60%, azul intermedio), action bar con Confirmar/Corregir/Rechazar, filmstrip abajo, progress bar. Verificar que `Tab`/click en Confirmar dispara el POST y la card se reemplaza con la próxima imagen (auto-avance). Detener con Ctrl-C.

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/templates/partials/image_card.html src/pacusam/templates/partials/progress_bar.html src/pacusam/templates/partials/filmstrip.html && git commit -m "feat(curate): partials image_card, confidence_bar, progress_bar y filmstrip"
```

### Task 39: Template curate.html — página completa con hotkeys A/C/R y overlay de atajos

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/curate.html`

UI task (build + verificación manual). Extiende `base.html` (de Track B). Layout: imagen central (incluye `partials/image_card.html`), filmstrip debajo, y un overlay de atajos toggleable con `?`. Las hotkeys A/C/R viven en el partial `image_card`; acá se agrega el overlay y la carga inicial vía HTMX.

- [ ] **Step 1: Crear `curate.html`:**
```html
{% extends "base.html" %}
{% block title %}Curado · {{ project.name }}{% endblock %}
{% block content %}
<div class="max-w-5xl mx-auto px-4 py-6" x-data="{ showHelp: false }"
     @keydown.window.shift.question.prevent="showHelp = !showHelp"
     @keydown.window.escape="showHelp = false">

  <div class="flex items-center justify-between mb-4">
    <div>
      <h1 class="font-[Lora] text-2xl text-[#1A1A18]">{{ project.name }}</h1>
      <p class="text-sm text-[#6B6B66]">Curado por incertidumbre · Active Learning</p>
    </div>
    <div class="flex items-center gap-2">
      <a href="/projects/{{ project.id }}/analytics"
         class="px-3 py-2 text-sm rounded-md bg-[#F4F2EE] text-[#1A1A18] hover:bg-[#E7E4DE] transition">Analytics</a>
      <button @click="showHelp = true"
              class="px-3 py-2 text-sm rounded-md bg-white border border-[#E7E4DE] text-[#6B6B66] transition">
        Atajos (?)
      </button>
    </div>
  </div>

  {# carga inicial del fragmento; luego se auto-reemplaza con cada acción #}
  <div hx-get="/projects/{{ project.id }}/queue" hx-trigger="load" hx-swap="innerHTML">
    {% include "partials/image_card.html" %}
  </div>

  <div class="mt-6">
    <h2 class="text-xs uppercase tracking-wide text-[#9C9A94] mb-2">Cola por incertidumbre</h2>
    {% include "partials/filmstrip.html" %}
  </div>

  {# overlay de atajos #}
  <div x-show="showHelp" x-cloak @click="showHelp = false"
       class="fixed inset-0 bg-black/30 flex items-center justify-center z-50">
    <div @click.stop class="bg-white rounded-lg border border-[#E7E4DE] p-6 w-80 shadow-sm">
      <h3 class="font-[Lora] text-lg text-[#1A1A18] mb-3">Atajos de teclado</h3>
      <ul class="text-sm text-[#6B6B66] space-y-2">
        <li class="flex justify-between"><span>Confirmar sugerencia</span><kbd class="font-mono bg-[#F4F2EE] px-2 rounded">A</kbd></li>
        <li class="flex justify-between"><span>Corregir etiqueta</span><kbd class="font-mono bg-[#F4F2EE] px-2 rounded">C</kbd></li>
        <li class="flex justify-between"><span>Rechazar</span><kbd class="font-mono bg-[#F4F2EE] px-2 rounded">R</kbd></li>
        <li class="flex justify-between"><span>Cerrar / cancelar</span><kbd class="font-mono bg-[#F4F2EE] px-2 rounded">Esc</kbd></li>
      </ul>
      <button @click="showHelp = false"
              class="mt-4 w-full px-3 py-2 text-sm rounded-md bg-[#2563EB] text-white">Entendido</button>
    </div>
  </div>
</div>
{% endblock %}
```

- [ ] **Step 2: Build + verificación manual.** Levantar la app:
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && PACUSAM_DB=:memory: python -m uvicorn pacusam.api:app --port 8012
```
Abrir `http://localhost:8012/projects/1/curate` (tras login + proyecto sembrado). Observar: header con nombre del proyecto, imagen central que carga vía HTMX (`hx-trigger="load"`), filmstrip debajo. Pulsar `A` confirma y auto-avanza; `R` abre el panel de motivos; `?` abre el overlay de atajos; `Esc` lo cierra. Detener con Ctrl-C.

- [ ] **Step 3: Correr la suite completa para confirmar que nada se rompió.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest -q
```
Salida esperada: toda la suite en verde (incluye `test_curate_queue.py`, `test_curate_actions.py`, `test_curate_api.py`).

- [ ] **Step 4: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add src/pacusam/templates/curate.html && git commit -m "feat(curate): pagina curate.html con hotkeys A/C/R, auto-avance HTMX y overlay de atajos"
```

### Task 40: Acceptance BDD — escenario de curado por incertidumbre extremo a extremo

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/features/curado.feature`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curado_al.py`
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/features/curado_al.feature`

Escenario nuevo (no toca el `curado.feature` legacy que usa el esquema viejo) que cubre el wow moment de Track E: la cola entrega primero la imagen más incierta, validar avanza, rechazar con motivo la excluye. Usa la conexión de la app directamente para sembrar confidencias controladas.

- [ ] **Step 1: Crear el feature.** `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/features/curado_al.feature`:
```gherkin
# Active Learning (Track E): la cola prioriza la imagen MÁS INCIERTA.
# language: es

Característica: Curado priorizado por incertidumbre
  Como curador quiero ver primero las imágenes donde el modelo duda
  para maximizar el valor de cada validación.

  Escenario: La cola entrega primero la imagen más incierta y validar avanza
    Dado un proyecto con imágenes de confianza 0.95, 0.55 y 0.72
    Cuando pido la próxima imagen de la cola
    Entonces recibo la imagen de confianza 0.55
    Cuando valido esa imagen con una etiqueta válida
    Y pido la próxima imagen de la cola
    Entonces recibo la imagen de confianza 0.72
```

- [ ] **Step 2: Crear los steps.** `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_curado_al.py`:
```python
"""BDD del curado priorizado por incertidumbre (Track E)."""
from __future__ import annotations

import json

import pytest
from pytest_bdd import scenarios, given, when, then, parsers

from pacusam import db, services

scenarios("curado_al.feature")


@pytest.fixture
def conn():
    return db.connect(":memory:")


@pytest.fixture
def ctx():
    return {"project_id": None, "current": None}


@given(parsers.parse("un proyecto con imágenes de confianza {c1:f}, {c2:f} y {c3:f}"))
def proyecto_con_confianzas(conn, ctx, c1, c2, c3):
    conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES ('P', '', 1, 'rx', ?, '2026-01-01T00:00:00+00:00')",
        (json.dumps(["normal", "anomalia"]),),
    )
    conn.commit()
    pid = conn.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1").fetchone()["id"]
    for i, c in enumerate((c1, c2, c3)):
        conn.execute(
            "INSERT INTO images (project_id, filename, path, suggested_label, confidence, status) "
            "VALUES (?,?,?,?,?, 'pending')",
            (pid, f"img_{i}.dcm", f"/img/img_{i}.dcm", "normal", c),
        )
    conn.commit()
    ctx["project_id"] = pid


@when("pido la próxima imagen de la cola")
def pido_proxima(conn, ctx):
    ctx["current"] = services.queue_next(conn, ctx["project_id"])


@when("valido esa imagen con una etiqueta válida")
def valido_actual(conn, ctx):
    services.validate_image(conn, ctx["current"]["id"], "normal")


@then(parsers.parse("recibo la imagen de confianza {c:f}"))
def recibo_confianza(ctx, c):
    assert ctx["current"] is not None
    assert abs(ctx["current"]["confidence"] - c) < 1e-9
```

- [ ] **Step 3: Correr y ver pasar (el dominio ya está implementado por las tasks anteriores).**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && python -m pytest tests/test_curado_al.py -q
```
Salida esperada: `1 passed` (1 scenario). Si falla por orden, revisar `ORDER BY (1.0 - confidence) DESC` en `queue_next`.

- [ ] **Step 4: Dejar nota en el feature legacy.** Agregar al tope de `tests/features/curado.feature` (sin tocar sus escenarios) una línea de comentario para evitar confusión:
```gherkin
# NOTA: este feature usa el esquema legacy (sin proyectos). El curado por
# incertidumbre del MVP PACUSAM está en curado_al.feature (Track E).
```

- [ ] **Step 5: Commit.**
```bash
cd /Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow && git add tests/features/curado_al.feature tests/test_curado_al.py tests/features/curado.feature && git commit -m "test(curate): acceptance BDD de curado priorizado por incertidumbre"
```


## Track F — Active Learning + Analytics (concordancia, distribución, retrain sim)

### Task 41: services.concordance — tasa de concordancia (TDD)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_analytics.py` (Create)

Dependencias: asume que `db.connect`, `create_project`, `seed_images` y `validate_image` ya existen con las firmas pinneadas (Tracks A/D). `concordance` compara `final_label` contra `suggested_label` sobre imágenes validadas del proyecto.

- [ ] **Step 1: Escribir test que falla — concordancia con set fijo**

Crear `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_analytics.py`:

```python
"""Unit tests de Track F: analytics de dominio (concordancia, distribución, retrain sim).

Corren contra la capa de servicios con SQLite :memory: y datos controlados.
No tocan HTTP. Insertan filas de `images` directamente para fijar suggested_label
y confidence, y usan services.validate_image / reject_image para el estado final.
"""
from __future__ import annotations

import pytest

from pacusam import db, services


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    yield c
    c.close()


def _make_project(conn, labels=("normal", "anomalia")):
    """Crea un proyecto mínimo y devuelve su id. owner_id=1 (no hace falta user real
    porque no hay FK enforcement en SQLite por defecto)."""
    p = services.create_project(
        conn, owner_id=1, name="P", description="", domain="rx", labels=list(labels)
    )
    return p["id"]


def _insert_image(conn, project_id, filename, suggested_label, confidence, status="pending"):
    """Inserta una imagen con suggested_label/confidence fijos (sin pasar por classifier)."""
    cur = conn.execute(
        "INSERT INTO images (project_id, filename, path, suggested_label, confidence, status) "
        "VALUES (?,?,?,?,?,?)",
        (project_id, filename, f"/img/{filename}", suggested_label, confidence, status),
    )
    conn.commit()
    return cur.lastrowid


def test_concordance_rate_con_set_fijo(conn):
    pid = _make_project(conn)
    # 4 imágenes; sugerencias fijas, validamos con etiquetas conocidas.
    i1 = _insert_image(conn, pid, "a.dcm", "normal", 0.9)
    i2 = _insert_image(conn, pid, "b.dcm", "normal", 0.8)
    i3 = _insert_image(conn, pid, "c.dcm", "anomalia", 0.7)
    i4 = _insert_image(conn, pid, "d.dcm", "anomalia", 0.6)
    # Validamos: i1 y i3 coinciden con la sugerencia; i2 e i4 las cambia el curador.
    services.validate_image(conn, i1, "normal")     # agree
    services.validate_image(conn, i2, "anomalia")   # disagree
    services.validate_image(conn, i3, "anomalia")   # agree
    services.validate_image(conn, i4, "normal")     # disagree

    c = services.concordance(conn, pid)
    assert c["total_validated"] == 4
    assert c["agreed"] == 2
    assert c["rate"] == 0.5


def test_concordance_sin_validadas_rate_cero(conn):
    pid = _make_project(conn)
    _insert_image(conn, pid, "x.dcm", "normal", 0.9)  # pending, nunca validada
    c = services.concordance(conn, pid)
    assert c == {"agreed": 0, "total_validated": 0, "rate": 0.0}
```

- [ ] **Step 2: Correr y ver fallar**

```
python -m pytest tests/test_analytics.py -q
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'concordance'` (2 failed).

- [ ] **Step 3: Implementar `concordance` (mínimo)**

Agregar al final de `src/pacusam/services.py`:

```python
def concordance(conn, project_id: int) -> dict:
    """Tasa de acuerdo curador↔modelo: de las imágenes validadas del proyecto,
    cuántas terminaron con final_label == suggested_label. rate en [0,1]."""
    rows = conn.execute(
        "SELECT final_label, suggested_label FROM images "
        "WHERE project_id = ? AND status = 'validated'",
        (project_id,),
    ).fetchall()
    total = len(rows)
    agreed = sum(1 for r in rows if r["final_label"] == r["suggested_label"])
    rate = round(agreed / total, 4) if total else 0.0
    return {"agreed": agreed, "total_validated": total, "rate": rate}
```

- [ ] **Step 4: Correr y ver pasar**

```
python -m pytest tests/test_analytics.py -q
```
Salida esperada: `2 passed`.

- [ ] **Step 5: Commit**

```
git add tests/test_analytics.py src/pacusam/services.py
git commit -m "feat(analytics): concordance rate curador vs modelo sobre validadas"
```

### Task 42: services.class_distribution — conteo y porcentajes por clase (TDD)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_analytics.py` (Modify)

Calcula distribución de `final_label` sobre validadas no rechazadas. Reusa helpers `_make_project` / `_insert_image` del test file ya creado.

- [ ] **Step 1: Escribir test que falla — distribución con conteos y porcentajes**

Agregar a `tests/test_analytics.py`:

```python
def test_class_distribution_cuenta_y_porcentajes(conn):
    pid = _make_project(conn, labels=("normal", "anomalia"))
    # 3 validadas como normal, 1 como anomalia, 1 rechazada (no cuenta), 1 pending (no cuenta).
    ids = [
        _insert_image(conn, pid, f"n{i}.dcm", "normal", 0.9) for i in range(3)
    ]
    a1 = _insert_image(conn, pid, "an1.dcm", "anomalia", 0.8)
    rej = _insert_image(conn, pid, "rej.dcm", "normal", 0.7)
    _insert_image(conn, pid, "pend.dcm", "normal", 0.6)  # queda pending
    for i in ids:
        services.validate_image(conn, i, "normal")
    services.validate_image(conn, a1, "anomalia")
    services.reject_image(conn, rej, "mala calidad")

    dist = services.class_distribution(conn, pid)
    # Ordenado por count DESC: normal=3 (75%), anomalia=1 (25%). Total validadas no rechazadas = 4.
    assert dist == [
        {"label": "normal", "count": 3, "percent": 75.0},
        {"label": "anomalia", "count": 1, "percent": 25.0},
    ]


def test_class_distribution_vacia(conn):
    pid = _make_project(conn)
    assert services.class_distribution(conn, pid) == []
```

- [ ] **Step 2: Correr y ver fallar**

```
python -m pytest tests/test_analytics.py -q -k class_distribution
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'class_distribution'` (2 failed).

- [ ] **Step 3: Implementar `class_distribution` (mínimo)**

Agregar al final de `src/pacusam/services.py`:

```python
def class_distribution(conn, project_id: int) -> list[dict]:
    """Distribución de etiquetas finales sobre imágenes validadas (excluye rechazadas
    y pendientes). Lista [{label, count, percent}] ordenada por count DESC, luego label."""
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
```

- [ ] **Step 4: Correr y ver pasar**

```
python -m pytest tests/test_analytics.py -q
```
Salida esperada: `4 passed` (los 2 de concordancia + 2 nuevos).

- [ ] **Step 5: Commit**

```
git add tests/test_analytics.py src/pacusam/services.py
git commit -m "feat(analytics): class_distribution con conteos y porcentajes sobre validadas"
```

### Task 43: services.simulate_retrain — sube confidencias de pending y reporta mejora (TDD)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/services.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_analytics.py` (Modify)

Wow moment #3: simula que el modelo "aprendió" subiendo la confianza de las imágenes pendientes hacia 1.0. Devuelve `{improvement_pct, new_avg_confidence}` con `improvement_pct > 0` cuando había pendientes con confianza < 1.

- [ ] **Step 1: Escribir test que falla — retrain sube confidencias e informa mejora**

Agregar a `tests/test_analytics.py`:

```python
def test_simulate_retrain_sube_confidencias_y_reporta_mejora(conn):
    pid = _make_project(conn)
    # 2 pending con confianza baja; 1 ya validada (no debe afectar el promedio de pending).
    p1 = _insert_image(conn, pid, "p1.dcm", "normal", 0.50)
    p2 = _insert_image(conn, pid, "p2.dcm", "anomalia", 0.60)
    v1 = _insert_image(conn, pid, "v1.dcm", "normal", 0.90)
    services.validate_image(conn, v1, "normal")

    before_avg = (0.50 + 0.60) / 2  # 0.55

    res = services.simulate_retrain(conn, pid)
    assert res["improvement_pct"] > 0
    # new_avg_confidence es sobre las pending, y debe ser mayor que el promedio previo.
    assert res["new_avg_confidence"] > before_avg
    assert res["new_avg_confidence"] <= 1.0

    # Persistió: las pending ahora tienen mayor confianza que antes (y siguen pending).
    rows = conn.execute(
        "SELECT id, confidence, status FROM images WHERE id IN (?,?)", (p1, p2)
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    assert by_id[p1]["confidence"] > 0.50 and by_id[p1]["status"] == "pending"
    assert by_id[p2]["confidence"] > 0.60 and by_id[p2]["status"] == "pending"
    # La validada no se tocó.
    val = conn.execute("SELECT confidence FROM images WHERE id=?", (v1,)).fetchone()
    assert val["confidence"] == 0.90


def test_simulate_retrain_sin_pending_no_mejora(conn):
    pid = _make_project(conn)
    res = services.simulate_retrain(conn, pid)
    assert res == {"improvement_pct": 0.0, "new_avg_confidence": 0.0}
```

- [ ] **Step 2: Correr y ver fallar**

```
python -m pytest tests/test_analytics.py -q -k simulate_retrain
```
Salida esperada: `AttributeError: module 'pacusam.services' has no attribute 'simulate_retrain'` (2 failed).

- [ ] **Step 3: Implementar `simulate_retrain` (mínimo)**

Agregar al final de `src/pacusam/services.py`:

```python
def simulate_retrain(conn, project_id: int) -> dict:
    """Wow #3: simula un reentrenamiento. Acerca la confianza de cada imagen pending
    hacia 1.0 (cierra el 60% del gap restante), persiste, y reporta cuánto subió el
    promedio de confianza de las pending. Sin pending -> mejora 0."""
    rows = conn.execute(
        "SELECT id, confidence FROM images WHERE project_id = ? AND status = 'pending'",
        (project_id,),
    ).fetchall()
    if not rows:
        return {"improvement_pct": 0.0, "new_avg_confidence": 0.0}

    old_avg = sum(r["confidence"] for r in rows) / len(rows)
    new_confs = []
    for r in rows:
        boosted = round(r["confidence"] + (1.0 - r["confidence"]) * 0.6, 4)
        conn.execute("UPDATE images SET confidence = ? WHERE id = ?", (boosted, r["id"]))
        new_confs.append(boosted)
    conn.commit()

    new_avg = sum(new_confs) / len(new_confs)
    improvement = round(100 * (new_avg - old_avg) / old_avg, 1) if old_avg else 0.0
    return {"improvement_pct": improvement, "new_avg_confidence": round(new_avg, 4)}
```

- [ ] **Step 4: Correr y ver pasar**

```
python -m pytest tests/test_analytics.py -q
```
Salida esperada: `6 passed`.

- [ ] **Step 5: Commit**

```
git add tests/test_analytics.py src/pacusam/services.py
git commit -m "feat(analytics): simulate_retrain sube confidencias de pending y reporta improvement_pct"
```

### Task 44: POST /projects/{id}/retrain — endpoint de retrain con respuesta de toast (TDD)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_analytics_api.py` (Create)

Dependencias: `require_user` (Track A) y `create_project`/`seed_images` (Track D) ya existen; la app monta `Jinja2Templates` con dir `templates/` (Track C). Este endpoint devuelve un fragmento HTML (toast) vía HTMX. Para aislar el test, autenticamos creando un usuario y logueando por las rutas reales.

- [ ] **Step 1: Escribir test que falla — retrain responde 200 con mejora en el HTML**

Crear `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_analytics_api.py`:

```python
"""Tests de API de Track F: endpoint de retrain (toast HTMX) y página de analytics.

Usan TestClient con SQLite :memory'. Autentican vía las rutas reales /register + /login
para obtener la cookie de sesión, luego operan sobre un proyecto propio.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pacusam.api import create_app


@pytest.fixture
def client():
    return TestClient(create_app(":memory:"))


@pytest.fixture
def project_id(client):
    """Registra un usuario, crea un proyecto y lo siembra. Devuelve el project_id.
    TestClient mantiene la cookie de sesión entre requests."""
    client.post("/register", data={"email": "f@test.com", "password": "secreto123"})
    r = client.post(
        "/projects",
        data={"name": "Tórax", "description": "rx", "domain": "rx", "labels": "normal,anomalia"},
        follow_redirects=False,
    )
    # POST /projects redirige a /projects/{id}; extraemos el id del Location.
    loc = r.headers["location"]
    pid = int(loc.rstrip("/").split("/")[-1])
    client.post(f"/projects/{pid}/seed", data={}) if False else None  # seed lo hace Track D al crear
    return pid


def test_retrain_devuelve_toast_con_mejora(client, project_id):
    r = client.post(f"/projects/{project_id}/retrain")
    assert r.status_code == 200
    body = r.text.lower()
    # El toast menciona la mejora y el porcentaje.
    assert "%" in body
    assert "confianza" in body or "mejor" in body


def test_retrain_proyecto_inexistente_404(client):
    # Sin sesión -> redirige a login; con sesión pero id inexistente -> 404 de dominio.
    client.post("/register", data={"email": "g@test.com", "password": "secreto123"})
    r = client.post("/projects/999999/retrain", follow_redirects=False)
    assert r.status_code == 404
```

- [ ] **Step 2: Correr y ver fallar**

```
python -m pytest tests/test_analytics_api.py -q
```
Salida esperada: fallo por `404`/`405` en `/projects/{id}/retrain` (ruta inexistente) o `KeyError: 'location'`. (2 failed).

- [ ] **Step 3: Agregar mapeo de error y la ruta `/retrain`**

En `src/pacusam/api.py`, extender `_STATUS` para incluir `project_not_found`:

```python
_STATUS = {
    "image_not_found": 404,
    "label_required": 422,
    "invalid_label": 422,
    "project_not_found": 404,
    "name_required": 422,
    "name_too_long": 422,
    "reason_required": 422,
    "email_exists": 409,
}
```

Agregar la ruta dentro de `create_app` (asume `templates = Jinja2Templates(directory=...)` y `require_user` ya definidos por Tracks C/A). Colocarla junto a las demás rutas de acciones:

```python
    @app.post("/projects/{project_id}/retrain")
    def retrain(project_id: int, request: Request, conn=Depends(get_conn)):
        require_user(request)
        services.get_project(conn, project_id)  # 404 si no existe
        result = _guard(services.simulate_retrain, conn, project_id)
        return templates.TemplateResponse(
            "partials/flash.html",
            {
                "request": request,
                "kind": "success",
                "message": (
                    f"Reentrenamiento simulado: confianza media "
                    f"{result['new_avg_confidence']:.0%} (+{result['improvement_pct']:.1f}%)"
                ),
            },
        )
```

Asegurar imports al tope de `api.py` (si no están ya por otros tracks):

```python
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
```

Nota de dependencia: `partials/flash.html` lo provee Track C; debe aceptar `kind` y `message`. Si aún no existe al correr este test, crear un stub mínimo en `src/pacusam/templates/partials/flash.html`:

```html
<div class="flash flash--{{ kind }}" role="status">{{ message }}</div>
```

- [ ] **Step 4: Correr y ver pasar**

```
python -m pytest tests/test_analytics_api.py -q
```
Salida esperada: `2 passed`.

- [ ] **Step 5: Commit**

```
git add tests/test_analytics_api.py src/pacusam/api.py src/pacusam/templates/partials/flash.html
git commit -m "feat(analytics): POST /projects/{id}/retrain devuelve toast HTMX con la mejora"
```

### Task 45: GET /projects/{id}/analytics — datos de la página de analytics (TDD)

**Files:**
- Modify: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/api.py`
- Test: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/tests/test_analytics_api.py` (Modify)

La ruta arma el contexto (concordancia, distribución, progreso, proyecto) y renderiza `analytics.html`. Tests verifican guard de auth y que el HTML traiga los números clave.

- [ ] **Step 1: Escribir test que falla — la página de analytics renderiza con métricas**

Agregar a `tests/test_analytics_api.py`:

```python
def test_analytics_sin_sesion_redirige_a_login(project_id):
    # Cliente nuevo SIN sesión.
    anon = TestClient(create_app(":memory:"))
    r = anon.get("/projects/1/analytics", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert "/login" in r.headers["location"]


def test_analytics_muestra_concordancia_y_distribucion(client, project_id):
    # Validamos dos imágenes para que haya datos en concordancia/distribución.
    q = client.get(f"/projects/{project_id}/queue")
    # La queue de Track E devuelve un fragmento con el id de la próxima imagen;
    # acá validamos directo vía dominio mediante la ruta de validación con la primer pending.
    img = services_first_pending(client, project_id)
    client.post(f"/images/{img}/validate", data={"label": "normal"})

    r = client.get(f"/projects/{project_id}/analytics")
    assert r.status_code == 200
    body = r.text.lower()
    assert "concordancia" in body
    assert "distribución" in body or "distribucion" in body
    assert "%" in body


def services_first_pending(client, project_id):
    """Helper: devuelve el id de la primera imagen pending del proyecto vía /progress + DB no
    está disponible desde el cliente, así que usamos el endpoint de queue de Track E que expone
    data-image-id. Fallback robusto: parsea el primer entero tras 'image-id'."""
    import re
    html = client.get(f"/projects/{project_id}/queue").text
    m = re.search(r'image[-_]id["\']?\s*[:=]\s*["\']?(\d+)', html)
    assert m, "no se encontró image-id en el fragmento de queue"
    return int(m.group(1))
```

Nota de dependencia: el parser de `image-id` asume que el fragmento de Track E (`partials/image_card.html`) expone el id de la imagen como `data-image-id="123"`. Si Track E usa otro atributo, ajustar la regex en este helper (único punto de acoplamiento).

- [ ] **Step 2: Correr y ver fallar**

```
python -m pytest tests/test_analytics_api.py -q -k analytics
```
Salida esperada: `404`/`405` en `/projects/{id}/analytics` (ruta inexistente). (2 failed).

- [ ] **Step 3: Agregar la ruta `GET /projects/{id}/analytics`**

En `src/pacusam/api.py`, dentro de `create_app`, junto a las páginas HTML:

```python
    @app.get("/projects/{project_id}/analytics", include_in_schema=False)
    def analytics_page(project_id: int, request: Request, conn=Depends(get_conn)):
        require_user(request)
        project = _guard(services.get_project, conn, project_id)
        return templates.TemplateResponse(
            "analytics.html",
            {
                "request": request,
                "project": project,
                "concordance": services.concordance(conn, project_id),
                "distribution": services.class_distribution(conn, project_id),
                "progress": services.progress(conn, project_id),
            },
        )
```

- [ ] **Step 4: Correr y ver pasar**

Requiere que `analytics.html` exista (siguiente tarea). Correr primero para confirmar el fallo de template, luego seguir a la tarea de template y volver. Comando:

```
python -m pytest tests/test_analytics_api.py -q -k analytics
```
Salida esperada tras la tarea de template: `2 passed`.

- [ ] **Step 5: Commit**

```
git add tests/test_analytics_api.py src/pacusam/api.py
git commit -m "feat(analytics): GET /projects/{id}/analytics arma contexto y renderiza la página"
```

### Task 46: analytics.html — página de analytics (concordancia, barras, progreso, resumen)

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/analytics.html`
- Verificación: manual + corre el test de la tarea anterior.

Dependencias: `base.html` (Track C) con bloques `{% block content %}` y los CDNs (Tailwind/HTMX/Alpine/fonts). `partials/progress_bar.html` lo provee Track E; acá lo incluimos si existe, con fallback inline. El banner "ordenado por incertidumbre" y el contador "etiquetaste N de M, las más dudosas" viven en `curate.html` (Track E) — NO se implementan acá. UI/template: pasos de build + verificación manual (no TDD unitario).

- [ ] **Step 1: Crear `analytics.html` con el markup completo**

Crear `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/analytics.html`:

```html
{% extends "base.html" %}
{% block title %}Analytics · {{ project.name }}{% endblock %}

{% block content %}
<main class="mx-auto max-w-5xl px-6 py-10" x-data="{}">
  <header class="mb-8 flex items-center justify-between">
    <div>
      <p class="text-sm text-[#9C9A94]">Proyecto</p>
      <h1 class="font-[Lora] text-3xl text-[#1A1A18]">{{ project.name }}</h1>
    </div>
    <div class="flex items-center gap-2">
      <a href="/projects/{{ project.id }}/curate"
         class="rounded-md border border-[#E7E4DE] bg-white px-3 py-2 text-sm text-[#1A1A18] transition hover:bg-[#F4F2EE]"
         style="transition-duration:140ms">Volver a curar</a>
      <button
         hx-post="/projects/{{ project.id }}/retrain"
         hx-target="#flash"
         hx-swap="innerHTML"
         class="rounded-md bg-[#2563EB] px-3 py-2 text-sm font-medium text-white transition hover:bg-[#1D4ED8]"
         style="transition-duration:140ms">Simular reentrenamiento</button>
    </div>
  </header>

  <div id="flash" class="mb-6"></div>

  <!-- Resumen ejecutivo -->
  <section class="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
    <div class="rounded-lg border border-[#E7E4DE] bg-white p-5">
      <p class="text-sm text-[#6B6B66]">Concordancia con el modelo</p>
      <p class="mt-1 font-[JetBrains_Mono] text-3xl text-[#1A1A18]">
        {{ (concordance.rate * 100) | round(1) }}%
      </p>
      <p class="mt-1 text-xs text-[#9C9A94]">
        {{ concordance.agreed }} de {{ concordance.total_validated }} validadas coinciden
        con la sugerencia
      </p>
    </div>
    <div class="rounded-lg border border-[#E7E4DE] bg-white p-5">
      <p class="text-sm text-[#6B6B66]">Progreso de curado</p>
      <p class="mt-1 font-[JetBrains_Mono] text-3xl text-[#1A1A18]">{{ progress.percent }}%</p>
      <p class="mt-1 text-xs text-[#9C9A94]">
        {{ progress.validated }} validadas · {{ progress.rejected }} rechazadas ·
        {{ progress.pending }} pendientes
      </p>
    </div>
    <div class="rounded-lg border border-[#E7E4DE] bg-white p-5">
      <p class="text-sm text-[#6B6B66]">Total de imágenes</p>
      <p class="mt-1 font-[JetBrains_Mono] text-3xl text-[#1A1A18]">{{ progress.total }}</p>
      <p class="mt-1 text-xs text-[#9C9A94]">en el dataset del proyecto</p>
    </div>
  </section>

  <!-- Distribución de clases (barras HTML/CSS puro) -->
  <section class="mb-8 rounded-lg border border-[#E7E4DE] bg-white p-6">
    <h2 class="font-[Lora] text-xl text-[#1A1A18]">Distribución de clases</h2>
    <p class="mb-4 text-sm text-[#6B6B66]">Etiquetas finales sobre imágenes validadas.</p>
    {% if distribution %}
      <div class="space-y-3">
        {% for d in distribution %}
        <div>
          <div class="mb-1 flex items-center justify-between text-sm">
            <span class="font-medium text-[#1A1A18]">{{ d.label }}</span>
            <span class="font-[JetBrains_Mono] text-[#6B6B66]">{{ d.count }} · {{ d.percent }}%</span>
          </div>
          <div class="h-3 w-full overflow-hidden rounded-full bg-[#F4F2EE]">
            <div class="h-3 rounded-full bg-[#2563EB] transition-all"
                 style="width: {{ d.percent }}%; transition-duration:160ms"></div>
          </div>
        </div>
        {% endfor %}
      </div>
    {% else %}
      <p class="rounded-md bg-[#F4F2EE] px-4 py-6 text-center text-sm text-[#9C9A94]">
        Todavía no hay imágenes validadas. Empezá a curar para ver la distribución.
      </p>
    {% endif %}
  </section>

  <!-- Resumen ejecutivo en prosa -->
  <section class="rounded-lg border border-[#E7E4DE] bg-[#FFFFFF] p-6">
    <h2 class="font-[Lora] text-xl text-[#1A1A18]">Resumen ejecutivo</h2>
    <p class="mt-2 text-sm leading-relaxed text-[#6B6B66]">
      Se validaron <strong class="text-[#1A1A18]">{{ progress.validated }}</strong> de
      <strong class="text-[#1A1A18]">{{ progress.total }}</strong> imágenes
      ({{ progress.percent }}% del dataset). El modelo acertó la sugerencia en el
      <strong class="text-[#1A1A18]">{{ (concordance.rate * 100) | round(1) }}%</strong>
      de los casos validados, lo que indica
      {% if concordance.rate >= 0.8 %}una alta confiabilidad del pre-clasificador.
      {% elif concordance.rate >= 0.5 %}un desempeño aceptable con margen de mejora.
      {% else %}que el modelo aún requiere reentrenamiento.{% endif %}
      Simulá un reentrenamiento para proyectar la mejora de confianza sobre las imágenes
      pendientes.
    </p>
  </section>
</main>
{% endblock %}
```

- [ ] **Step 2: Verificación automática (test de la tarea anterior)**

```
python -m pytest tests/test_analytics_api.py -q -k analytics
```
Salida esperada: `2 passed` (el `404`/`KeyError` desaparece y el HTML contiene "concordancia", "distribución" y "%").

- [ ] **Step 3: Verificación manual de la página**

Levantar la app con datos sembrados:
```
PACUSAM_DB=:memory: python -m uvicorn pacusam.api:app --reload --port 8011
```
Abrir `http://localhost:8011/`, registrarse/loguearse, entrar a un proyecto, validar 2-3 imágenes en `/curate`, luego ir a `http://localhost:8011/projects/1/analytics`.

Observar:
- Tres tarjetas de resumen (concordancia %, progreso %, total) con números coherentes.
- Sección "Distribución de clases" con barras azules `#2563EB` cuyo ancho coincide con el `%`; suma de porcentajes ≈ 100.
- Párrafo de resumen ejecutivo con la frase de confiabilidad según el rate.
- Tipografías: títulos en Lora, números en JetBrains Mono, cuerpo en Inter.
- Bordes 1px `#E7E4DE`, fondo de tarjetas blanco sobre app `#FCFBF9`.

- [ ] **Step 4: Verificación del wow (retrain in-page)**

En la misma página, click en "Simular reentrenamiento". Observar:
- Aparece un toast/flash en `#flash` con texto tipo "Reentrenamiento simulado: confianza media 8X% (+Y.Y%)".
- No hay recarga de página completa (lo inserta HTMX en `#flash`).

- [ ] **Step 5: Commit**

```
git add src/pacusam/templates/analytics.html
git commit -m "feat(analytics): analytics.html con concordancia, barras de distribución, progreso y resumen"
```

### Task 47: Banner de incertidumbre y contador — partial reutilizable para curate (Track E)

**Files:**
- Create: `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/uncertainty_banner.html`
- Verificación: manual (render dentro de curate.html, propiedad de Track E).

Wow moment #2 vive en la pantalla de curado (Track E), pero el contenido del banner "ordenado por incertidumbre" + contador "etiquetaste N de M, las más dudosas" es responsabilidad de Track F. Se entrega como partial autónomo que Track E incluye con `{% include "partials/uncertainty_banner.html" %}` pasando `progress` y `next_image`. Dependencia explícita: Track E debe incluir este partial en `curate.html` y proveer `progress` (de `services.progress`) y `next_image` (de `services.queue_next`).

- [ ] **Step 1: Crear el partial con markup completo**

Crear `/Users/mateoromano/Documents/mvp_pacusam/.claude/worktrees/mvp-wow/src/pacusam/templates/partials/uncertainty_banner.html`:

```html
{# Banner del wow #2: explica el ordenamiento por incertidumbre + contador de avance.
   Espera en el contexto: `progress` (dict de services.progress) y, opcionalmente,
   `next_image` (dict de services.queue_next con 'confidence'). Lo incluye curate.html (Track E). #}
<div class="mb-5 flex flex-col gap-3 rounded-lg border border-[#E7E4DE] bg-[#EFF4FF] px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
  <div class="flex items-start gap-3">
    <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24"
         fill="none" stroke="#2563EB" stroke-width="2" stroke-linecap="round"
         stroke-linejoin="round" class="mt-0.5 shrink-0">
      <path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>
    </svg>
    <div>
      <p class="text-sm font-medium text-[#1A1A18]">Ordenado por incertidumbre</p>
      <p class="text-xs text-[#6B6B66]">
        Te mostramos primero las imágenes donde el modelo está menos seguro: validarlas
        es lo que más mejora el clasificador (active learning).
      </p>
    </div>
  </div>
  <div class="shrink-0 text-right">
    <p class="font-[JetBrains_Mono] text-sm text-[#1A1A18]">
      Etiquetaste {{ progress.validated }} de {{ progress.total }}
    </p>
    {% if next_image is defined and next_image %}
    <p class="text-xs text-[#D97706]">
      Próxima: confianza {{ (next_image.confidence * 100) | round(0) | int }}% — de las más dudosas
    </p>
    {% endif %}
  </div>
</div>
```

- [ ] **Step 2: Verificación de render aislado (smoke con Jinja directo)**

Validar que el partial compila y renderiza con un contexto mínimo:
```
python -c "
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader('src/pacusam/templates'))
t = env.get_template('partials/uncertainty_banner.html')
out = t.render(progress={'validated': 2, 'total': 5}, next_image={'confidence': 0.54})
assert 'Ordenado por incertidumbre' in out
assert 'Etiquetaste 2 de 5' in out
assert '54%' in out
print('OK')
"
```
Salida esperada: `OK`.

- [ ] **Step 3: Verificación manual dentro de curate (cuando Track E lo incluya)**

En `/projects/{id}/curate`, observar arriba del visor de imágenes: banner con tint `#EFF4FF`, ícono de tendencia azul, texto "Ordenado por incertidumbre", contador "Etiquetaste N de M" en JetBrains Mono, y la línea ámbar `#D97706` "Próxima: confianza X% — de las más dudosas". Al validar, el contador sube en el siguiente render del fragmento.

Nota de dependencia: si Track E aún no incluyó el partial, este step queda pendiente del merge de Track E; el Step 2 ya garantiza que el partial es correcto de forma aislada.

- [ ] **Step 4: Commit**

```
git add src/pacusam/templates/partials/uncertainty_banner.html
git commit -m "feat(analytics): partial banner de incertidumbre + contador para curate (wow #2)"
```


## Track G — Integración, static, datasets reales y migración legacy (POST-MERGE)

> Estas tareas se ejecutan DESPUÉS de A–F y materializan las decisiones de integración de arriba. Cierran los gaps que la verificación adversarial detectó.

### Task 48: Unificar dependencias y .gitignore (una sola vez)

**Files:**
- Modify: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`, `.gitignore`

- [ ] **Step 1: Setear `requirements.txt` (unión canónica).**
```
fastapi>=0.110
uvicorn[standard]>=0.29
jinja2>=3.1
python-multipart>=0.0.9
itsdangerous>=2.1
passlib[bcrypt]>=1.7
```
- [ ] **Step 2: `requirements-dev.txt` = runtime + `pytest>=8.0`, `pytest-bdd>=7.0`, `httpx>=0.27`.**
- [ ] **Step 3: `pyproject.toml` `[project].dependencies` y extra `dev` alineados con lo de arriba.**
- [ ] **Step 4: `.gitignore` — agregar excepción para versionar datasets.** Apondé al final:
```
# Datasets de demo (imágenes reales versionadas)
!src/pacusam/static/
!src/pacusam/static/datasets/
!src/pacusam/static/datasets/**
```
- [ ] **Step 5: Instalar y verificar.** Run: `.venv/bin/python -m pip install -q -r requirements-dev.txt && .venv/bin/python -c "import passlib, jinja2, itsdangerous, multipart; print('ok')"` → Esperado: `ok`.
- [ ] **Step 6: Commit.** `git add requirements.txt requirements-dev.txt pyproject.toml .gitignore && git commit -m "chore(integ): unificar dependencias y excepcion de datasets en gitignore"`

### Task 49: Montar StaticFiles y wirear re-seed en `create_app`

**Files:**
- Modify: `src/pacusam/api.py`
- Test: `tests/test_integration_app.py` (create)

- [ ] **Step 1: Test que falla.** Crear `tests/test_integration_app.py`:
```python
from fastapi.testclient import TestClient
from pacusam.api import create_app

def test_arranque_siembra_dos_proyectos(tmp_path):
    app = create_app(db_path=str(tmp_path / "t.db"))
    client = TestClient(app)
    # require_user redirige a login -> seguimos redirects deshabilitados
    r = client.get("/login")
    assert r.status_code == 200
    # el seed dejó 2 proyectos en la DB
    from pacusam import db, services
    conn = db.connect(str(tmp_path / "t.db"))
    # buscamos el owner demo
    owner = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
    assert owner is not None
    projs = services.list_projects(conn, owner["id"])
    assert len(projs) >= 2

def test_static_se_sirve(tmp_path):
    app = create_app(db_path=str(tmp_path / "t.db"))
    client = TestClient(app)
    conn_path = str(tmp_path / "t.db")
    from pacusam import db
    conn = db.connect(conn_path)
    img = conn.execute("SELECT path FROM images LIMIT 1").fetchone()
    assert img is not None and img["path"].startswith("/static/")
    r = client.get(img["path"])
    assert r.status_code == 200
```
- [ ] **Step 2: Correr y ver fallar.** Run: `.venv/bin/python -m pytest tests/test_integration_app.py -q` → Esperado: FAIL (no se montó static y/o no se sembró al arrancar).
- [ ] **Step 3: En `create_app`** asegurar (según orden canónico): `app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")` con `_STATIC_DIR = Path(__file__).parent / "static"`, y al final antes de `return app`: abrir `conn = db.connect(db_path)` y `seed.seed_if_empty(conn)`.
- [ ] **Step 4: Correr y ver pasar.** Run: `.venv/bin/python -m pytest tests/test_integration_app.py -q` → Esperado: `2 passed`.
- [ ] **Step 5: Commit.** `git add src/pacusam/api.py tests/test_integration_app.py && git commit -m "feat(integ): montar /static y re-seed determinista al arrancar"`

### Task 49b: Adquirir datasets REALES (reemplaza placeholders de Track A)

**Files:**
- Create: `scripts/fetch_datasets.py`, `src/pacusam/static/datasets/chest_xray/*.jpg`, `src/pacusam/static/datasets/blood_cells/*.jpg`

- [ ] **Step 1: Script de descarga.** `scripts/fetch_datasets.py` baja:
  - **Células (BCCD, MIT):** ~40 imágenes desde `https://raw.githubusercontent.com/Shenggan/BCCD_Dataset/master/BCCD/JPEGImages/BloodImage_000NN.jpg` (NN = 00..40).
  - **Tórax (público, sin login):** ~40 imágenes desde el repo público `ieee8023/covid-chestxray-dataset` (`https://raw.githubusercontent.com/ieee8023/covid-chestxray-dataset/master/images/<archivo>`), tomando una muestra de su `metadata.csv`.
  Guardar en `src/pacusam/static/datasets/<proyecto>/`.
- [ ] **Step 2: Ejecutar.** Run: `.venv/bin/python scripts/fetch_datasets.py` → Esperado: ~80 archivos `.jpg`/`.png` reales descargados.
- [ ] **Step 3: Verificación manual.** Abrir 1 imagen de cada carpeta y confirmar que se ve (no bytes truchos). Confirmar tamaños > 5 KB.
- [ ] **Step 4: Commit.** `git add scripts/fetch_datasets.py src/pacusam/static/datasets && git commit -m "chore(integ): datasets reales (BCCD + chest x-ray) versionados"`

> Nota: el `seed.py` (Track A) debe registrar exactamente los archivos presentes en cada carpeta (listar el directorio), no nombres hardcodeados, para que `image.path` apunte a imágenes que existen.

### Task 50: `image_card.html` renderiza imagen real + `data-image-id`

**Files:**
- Modify: `src/pacusam/templates/partials/image_card.html`
- Test: `tests/test_curate_img.py` (create)

- [ ] **Step 1: Test que falla.**
```python
from fastapi.testclient import TestClient
from pacusam.api import create_app
from pacusam import db, services

def test_queue_fragment_tiene_img_real(tmp_path):
    app = create_app(db_path=str(tmp_path / "t.db"))
    client = TestClient(app)
    conn = db.connect(str(tmp_path / "t.db"))
    pid = conn.execute("SELECT id FROM projects LIMIT 1").fetchone()["id"]
    # login demo
    client.post("/login", data={"email": "demo@pacusam.dev", "password": "demo1234"}, follow_redirects=False)
    r = client.get(f"/projects/{pid}/queue")
    assert "<img" in r.text and "/static/datasets/" in r.text
    assert "data-image-id" in r.text
```
- [ ] **Step 2: Correr y ver fallar.** Run: `.venv/bin/python -m pytest tests/test_curate_img.py -q` → Esperado: FAIL (la card no tiene `<img>`).
- [ ] **Step 3: Editar `image_card.html`** para que la raíz tenga `data-image-id="{{ image.id }}"` y renderice `<img src="{{ image.path }}" alt="{{ image.filename }}" class="max-h-[70vh] mx-auto rounded-lg">` en vez del div gris; usar el macro `confidence_bar(image.confidence)`.
- [ ] **Step 4: Correr y ver pasar.** Run: `.venv/bin/python -m pytest tests/test_curate_img.py -q` → Esperado: `1 passed`.
- [ ] **Step 5: Commit.** `git add src/pacusam/templates/partials/image_card.html tests/test_curate_img.py && git commit -m "feat(integ): curado muestra imagen real + data-image-id"`

### Task 51: Incluir `uncertainty_banner` en `curate.html` + botón deshacer-rechazo

**Files:**
- Modify: `src/pacusam/templates/curate.html`, `src/pacusam/templates/partials/filmstrip.html`

- [ ] **Step 1: En `curate.html`** agregar `{% include "partials/uncertainty_banner.html" %}` arriba de la imagen (pasando `progress` y contexto del contador "N de M, las más dudosas").
- [ ] **Step 2: En `filmstrip.html`** hacer que las thumbnails con `status == 'rejected'` muestren un botón "Deshacer" que haga `hx-post="/images/{{ img.id }}/unreject"` y refresque la cola.
- [ ] **Step 3: Verificación manual.** Levantar uvicorn, entrar a curar, confirmar: banner visible arriba; rechazar una imagen y luego deshacer desde el filmstrip vuelve a 'pending'.
- [ ] **Step 4: Commit.** `git add src/pacusam/templates/curate.html src/pacusam/templates/partials/filmstrip.html && git commit -m "feat(integ): banner de uncertainty + deshacer rechazo en filmstrip"`

### Task 52: Migrar BDD legacy a la API nueva + remover rutas obsoletas

**Files:**
- Modify/Replace: `tests/conftest.py`, `tests/features/curado.feature`, `tests/test_curado.py`
- Modify: `src/pacusam/api.py`, `src/pacusam/services.py`

- [ ] **Step 1: Remover rutas obsoletas** `POST /seed` (variante solo-filenames) y `GET /next` de `api.py` (la cola las reemplaza con `GET /projects/{id}/queue`). Quitar `next_pending` de `services.py` si quedó huérfano (lo reemplaza `queue_next`).
- [ ] **Step 2: Reescribir `tests/conftest.py`** con fixtures de la API nueva: `client` (TestClient sobre `create_app` con `:memory:`), `demo_login` (postea /login del usuario demo sembrado), y un helper que crea un proyecto con N imágenes vía SQL directo.
- [ ] **Step 3: Reescribir `tests/features/curado.feature`** (Gherkin español) con escenarios project-scoped: dado un proyecto con imágenes sembradas, la cola trae la de menor confianza primero (uncertainty sampling), validar actualiza el progreso, rechazar con motivo la excluye.
- [ ] **Step 4: Correr la suite COMPLETA.** Run: `.venv/bin/python -m pytest -q` → Esperado: TODO verde (unit de A–F + BDD migrado + integración). Si algo del legacy quedó colgado, arreglarlo acá.
- [ ] **Step 5: Commit.** `git add tests/ src/pacusam/api.py src/pacusam/services.py && git commit -m "test(integ): migrar BDD legacy a API project-scoped; remover /seed y /next obsoletos"`

### Task 53: Verificación end-to-end manual + README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Levantar la app.** Run: `PYTHONPATH=src PACUSAM_DB=pacusam.db .venv/bin/python -m uvicorn pacusam.api:app --reload` y abrir `http://127.0.0.1:8000`.
- [ ] **Step 2: Recorrer el flujo completo:** registrarse → home con 2 proyectos → entrar a "Radiografías de tórax" → curar (validar, corregir, rechazar+motivo, deshacer) → ver que la cola está ordenada por incertidumbre → re-entrenar (toast) → analytics (concordancia + distribución). Anotar cualquier bug y arreglarlo.
- [ ] **Step 3: Actualizar `README.md`:** comandos de setup multiplataforma (`.venv/bin/...`), cómo levantar local, credenciales demo, y la sección **Roadmap** (US no implementadas: upload real/DICOM, parámetros del clasificador, historial de ciclos, filtro/búsqueda, export/PDF, admin/roles/log).
- [ ] **Step 4: Commit.** `git add README.md && git commit -m "docs: README con setup, demo y roadmap del MVP"`

