# PACUSAM — Bundles A/B/C/D Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Subir el rigor científico y el sello profesional de la demo PACUSAM con 4 bundles inspirados en Kaapana/MONAI/CVAT/OHIF, todo mockeado sobre el schema actual (sin DICOM ni ML real).

**Architecture:** Se extiende el MVP existente (FastAPI + Jinja2 + HTMX + Alpine + Tailwind + SQLite). Toda la lógica nueva vive en `services.py` (dominio, testeable), se expone en `api.py` (rutas, con `require_user` + `_owned_project` + `_guard`), y se renderiza con templates/partials reusando los macros de `partials/ui.html` y los tokens de `static/css/tokens.css`. Nada rompe los **174 tests existentes**.

**Tech Stack:** Python 3.10+, FastAPI, Jinja2, HTMX, Alpine.js, Tailwind (tokens.css), SQLite (stdlib), pytest/pytest-bdd.

**Contexto de código (firmas reales a respetar):**
- `services.py`: `queue_next(conn, project_id)`, `queue_list(conn, project_id, label=None)`, `validate_image(conn, image_id, label)`, `reject_image(conn, image_id, reason)`, `unreject_image(conn, image_id)`, `progress(conn, project_id)`, `concordance(conn, project_id)`, `class_distribution(conn, project_id)`, `simulate_retrain(conn, project_id)`, `record_cycle(conn, project_id, images_used, avg_before, avg_after, improvement_pct)`, `list_cycles(conn, project_id)`, `export_rows/export_summary(conn, project_id)`, `label_counts(conn, project_id)`, `time_saved(conn, project_id)`. Reusar `DomainError(code)`.
- `db.py`: tablas `users`, `projects`, `images` (id, project_id, filename, path, suggested_label, confidence, status [pending|validated|rejected], final_label, reject_reason, shown_at, validated_at), `al_cycles` (id, project_id, created_at, images_used, avg_conf_before, avg_conf_after, improvement_pct). `connect(path=None)` con WAL.
- `api.py`: `create_app`, `require_user` (Depends, lanza `_RedirectException`), `_owned_project(conn, project_id, user)`, `_guard`, `_STATUS`, `_render_next_card(request, conn, project_id, label=None)`, rutas `/projects/{id}/curate|queue|analytics|retrain|export.csv|export.json`. Render vía `templating.render`.
- `templates/`: `base.html`, `partials/ui.html` (macros `flash`, `progress_bar`, `confidence_bar`, `filter_chips`), `image_card.html`, `filmstrip.html`, `analytics.html`, `curate.html`, etc.
- venv: `.venv/bin/python`. Correr tests: `PYTHONPATH=src .venv/bin/python -m pytest -q`.

**Reglas de integración (LEY):** No romper los 174 tests. Parámetros nuevos en funciones existentes van OPCIONALES al final con default que preserva el comportamiento actual. Sin em-dashes en UI, acentos correctos. Render siempre vía `templating.render`. Commits frecuentes, uno por tarea.

---

## Bundle A — Rigor de Active Learning (MONAI Label)

### Task A1: Estrategia de sampling en la cola (Uncertainty / Random / Sequential)

**Files:**
- Modify: `src/pacusam/services.py`
- Modify: `src/pacusam/api.py`
- Test: `tests/test_strategy.py` (create)

- [ ] **Step 1: Test que falla.** Crear `tests/test_strategy.py`:
```python
from pacusam import db, services

def _seed(conn):
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at) VALUES ('P',1,'[\"X\",\"Y\"]','t')")
    # 3 pending con confidencias distintas
    for i,(fn,c) in enumerate([("a.jpg",0.95),("b.jpg",0.55),("c.jpg",0.75)]):
        conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence) VALUES (1,?,?,?,?)",
                     (fn,"/s/"+fn,"X",c))
    conn.commit()

def test_uncertainty_trae_la_menos_confiada_primero():
    conn = db.connect(":memory:"); _seed(conn)
    item = services.queue_next(conn, 1, strategy="uncertainty")
    assert item["filename"] == "b.jpg"   # 0.55 -> mayor incertidumbre

def test_sequential_trae_por_id():
    conn = db.connect(":memory:"); _seed(conn)
    item = services.queue_next(conn, 1, strategy="sequential")
    assert item["filename"] == "a.jpg"   # menor id

def test_random_es_determinista_por_seed():
    conn = db.connect(":memory:"); _seed(conn)
    a = services.queue_next(conn, 1, strategy="random", seed=42)
    b = services.queue_next(conn, 1, strategy="random", seed=42)
    assert a["id"] == b["id"]

def test_default_sigue_siendo_uncertainty():
    conn = db.connect(":memory:"); _seed(conn)
    assert services.queue_next(conn, 1)["filename"] == "b.jpg"
```
- [ ] **Step 2: Correr y ver fallar.** `PYTHONPATH=src .venv/bin/python -m pytest tests/test_strategy.py -q` → FAIL (queue_next no acepta strategy).
- [ ] **Step 3: Implementar.** En `services.py`, extender `queue_next` y `queue_list` con `strategy="uncertainty"` y `seed=None` opcionales al final. El `ORDER BY` según strategy:
  - `uncertainty`: `ORDER BY (1.0 - COALESCE(confidence,0.5)) DESC, id ASC` (comportamiento actual).
  - `sequential`: `ORDER BY id ASC`.
  - `random`: `ORDER BY (substr(filename,1,8) || ?) ` no — usar Python: traer las pending y ordenar con `random.Random(seed).shuffle`. Mantener `seed` para determinismo en test. Si `seed is None`, usar un orden estable por hash del filename (sin random global, que está prohibido en este entorno: usar `hashlib.md5(filename).hexdigest()`).
  Mantener la firma vieja funcionando (default uncertainty).
- [ ] **Step 4: Correr y ver pasar.** `... pytest tests/test_strategy.py -q` → 4 passed.
- [ ] **Step 5: API.** En `api.py`, `/projects/{id}/queue` acepta `strategy` (query param, default "uncertainty") y se lo pasa a `_render_next_card` → `queue_next`/`queue_list`. Validar strategy ∈ {uncertainty, random, sequential}; si no, usar uncertainty. Pasar `active_strategy` al contexto del card.
- [ ] **Step 6: Commit.** `git add src/pacusam/services.py src/pacusam/api.py tests/test_strategy.py && git commit -m "feat(al): estrategia de sampling uncertainty/random/sequential en la cola"`

### Task A2: F1/AUC por ciclo de Active Learning

**Files:**
- Modify: `src/pacusam/db.py`, `src/pacusam/services.py`
- Test: `tests/test_cycle_metrics.py` (create)

- [ ] **Step 1: Test que falla.**
```python
from pacusam import db, services

def test_simulate_retrain_registra_f1_auc_creciente():
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at) VALUES ('P',1,'[\"X\",\"Y\"]','t')")
    for i in range(6):
        conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence,status) VALUES (1,?,?,?,?,?)",
                     (f"i{i}.jpg",f"/s/i{i}.jpg","X",0.6,"pending"))
    conn.commit()
    services.simulate_retrain(conn, 1)
    c = services.list_cycles(conn, 1)
    assert "f1" in c[-1] and "auc" in c[-1]
    assert 0.5 <= c[-1]["f1"] <= 0.99
```
- [ ] **Step 2: Correr y ver fallar.** FAIL (list_cycles no devuelve f1/auc).
- [ ] **Step 3: Implementar.** En `db.py` agregar a `al_cycles` columnas `f1 REAL`, `auc REAL` (CREATE TABLE incluye; para DBs viejas no hay migración: es MVP, re-seed). En `services.record_cycle(...)` agregar params `f1=None, auc=None` (opcionales) y guardarlos. En `simulate_retrain`, calcular determinísticamente por número de ciclo `n` (1-based, contar ciclos previos +1): `f1 = round(min(0.82 + 0.04*n, 0.97), 3)`, `auc = round(min(0.85 + 0.035*n, 0.98), 3)`, y pasarlos a `record_cycle`. `list_cycles` ya devuelve todas las columnas (incluye f1/auc).
- [ ] **Step 4: Correr y ver pasar.** 1 passed. Correr `pytest -q` GLOBAL → re-seed de tests cubre el schema nuevo; verificar verde.
- [ ] **Step 5: Seed.** En `seed.py`, los 2 ciclos sembrados por proyecto deben incluir f1/auc crecientes (ej. ciclo1 f1=0.86 auc=0.88; ciclo2 f1=0.90 auc=0.92). Verificar test_seed sigue verde.
- [ ] **Step 6: Commit.** `git add src/pacusam/db.py src/pacusam/services.py src/pacusam/seed.py tests/test_cycle_metrics.py && git commit -m "feat(al): F1/AUC por ciclo (deterministico, creciente)"`

### Task A3: Umbral de re-entrenamiento por proyecto (UmbralAlcanzado)

**Files:**
- Modify: `src/pacusam/db.py`, `src/pacusam/services.py`, `src/pacusam/seed.py`
- Test: `tests/test_threshold.py` (create)

- [ ] **Step 1: Test que falla.**
```python
from pacusam import db, services

def test_threshold_status():
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at,retrain_threshold) VALUES ('P',1,'[\"X\"]','t',10)")
    for i in range(12):
        st = "validated" if i < 6 else "pending"
        conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label) VALUES (1,?,?,?,?,?,?)",
                     (f"i{i}.jpg",f"/s/i{i}.jpg","X",0.6,st,"X" if st=="validated" else None))
    conn.commit()
    t = services.threshold_status(conn, 1)
    assert t["threshold"] == 10 and t["validated"] == 6 and t["remaining"] == 4 and t["reached"] is False
```
- [ ] **Step 2: Correr y ver fallar.** FAIL.
- [ ] **Step 3: Implementar.** En `db.py`, `projects` agrega `retrain_threshold INTEGER DEFAULT 10`. En `services.py` agregar `threshold_status(conn, project_id) -> dict` con `{threshold, validated, remaining (max(0, threshold-validated)), reached (validated>=threshold)}`. En `seed.py`, setear `retrain_threshold` (ej. 20) en los proyectos demo.
- [ ] **Step 4: Correr y ver pasar.** 1 passed; `pytest -q` GLOBAL verde.
- [ ] **Step 5: Commit.** `git add -p` los 4 archivos relevantes y `git commit -m "feat(al): umbral de re-entrenamiento por proyecto + threshold_status"`

### Task A4: UI del Bundle A (entropy, selector de estrategia, sparkline F1, contador de umbral)

**Files:**
- Modify: `src/pacusam/templates/partials/image_card.html`, `curate.html`, `analytics.html`, `partials/filmstrip.html`

- [ ] **Step 1: Entropy en el card y filmstrip.** En `image_card.html`, junto a la barra de confianza, mostrar `Epistemic uncertainty (entropy): {{ image.uncertainty }}` en mono. Cambiar el banner de "Ordenado por incertidumbre" a incluir `Estrategia: {{ active_strategy|default('uncertainty')|capitalize }} · Monte Carlo Dropout (simulado)`. En `filmstrip.html` el `u {{ item.uncertainty }}` ya está; agregar `title` tooltip "1 - confianza, proxy de entropía".
- [ ] **Step 2: Selector de estrategia.** En `curate.html` topbar, un `<select>` Alpine con Uncertainty/Random/Secuencial que hace `hx-get="/projects/{{ project.id }}/queue?strategy=..."` `hx-target="#image-card" hx-swap="outerHTML"`. Resaltar la activa.
- [ ] **Step 3: Sparkline F1/AUC en analytics.** En la sección "Ciclos de aprendizaje activo" de `analytics.html`, sobre el timeline, dibujar un `<svg>` inline con una `<polyline>` de los puntos F1 por ciclo (coords calculadas en Jinja: x = índice escalado, y = (1-f1) escalado). Mostrar "F1 {{ cycles[0].f1 }} → {{ cycles[-1].f1 }}" como métrica estrella. Sin librería.
- [ ] **Step 4: Contador de umbral.** En `image_card.html` (panel izq), mostrar `{{ progress.validated }} de {{ threshold.threshold }} validadas hasta el próximo re-entrenamiento` con mini-barra. (Pasar `threshold=services.threshold_status(...)` al contexto del card desde `_render_next_card`.) En el else-branch (cola completa / umbral) ya hay confetti; si `threshold.reached`, el copy dice "UmbralAlcanzado: el modelo se re-entrena" + botón a `/retrain`.
- [ ] **Step 5: Verificación.** Levantar uvicorn, entrar a curar: ver entropy, cambiar estrategia (la cola se reordena), ver el contador de umbral; en analytics ver el sparkline F1. `pytest -q` GLOBAL verde.
- [ ] **Step 6: Commit.** `git add src/pacusam/templates && git commit -m "feat(al-ui): entropy, selector de estrategia, sparkline F1/AUC, contador de umbral"`

---

## Bundle B — Calidad y A/B (CVAT + white paper)

### Task B1: Conflictos, matriz de confusión y precision/recall

**Files:**
- Modify: `src/pacusam/services.py`
- Test: `tests/test_quality.py` (create)

- [ ] **Step 1: Test que falla.**
```python
from pacusam import db, services

def _seed_validated(conn, pairs):
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at) VALUES ('P',1,'[\"X\",\"Y\"]','t')")
    for i,(sug,fin) in enumerate(pairs):
        conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label,validated_at) VALUES (1,?,?,?,?, 'validated', ?, 't')",
                     (f"i{i}.jpg",f"/s/i{i}.jpg",sug,0.8,fin))
    conn.commit()

def test_conflicts_lista_discordancias():
    conn = db.connect(":memory:"); _seed_validated(conn, [("X","X"),("X","Y"),("Y","Y")])
    c = services.conflicts(conn, 1)
    assert len(c) == 1 and c[0]["suggested_label"] == "X" and c[0]["final_label"] == "Y"

def test_confusion_matrix():
    conn = db.connect(":memory:"); _seed_validated(conn, [("X","X"),("X","Y"),("Y","Y")])
    m = services.confusion_matrix(conn, 1)
    assert m["labels"] == ["X","Y"]
    assert m["matrix"][0][0] == 1 and m["matrix"][0][1] == 1 and m["matrix"][1][1] == 1

def test_quality_metrics():
    conn = db.connect(":memory:"); _seed_validated(conn, [("X","X"),("X","Y"),("Y","Y")])
    q = services.quality_metrics(conn, 1)
    assert 0 <= q["accuracy"] <= 1 and "per_class" in q
```
- [ ] **Step 2: Correr y ver fallar.** FAIL.
- [ ] **Step 3: Implementar en `services.py`:**
  - `conflicts(conn, project_id)`: validadas con `final_label != suggested_label`, devuelve list con `{id, filename, path, suggested_label, final_label, confidence}`.
  - `confusion_matrix(conn, project_id)`: labels = `json.loads(project.labels)` ordenadas; `matrix[i][j]` = # validadas con suggested=labels[i] y final=labels[j]. Devuelve `{labels, matrix}`.
  - `quality_metrics(conn, project_id)`: sobre validadas, `accuracy` = concordancia (final==suggested)/total; `per_class` = lista de `{label, precision, recall}` tratando `final_label` como ground truth y `suggested_label` como predicción (precision = TP/(TP+FP), recall = TP/(TP+FN); manejar div/0 → 0.0).
- [ ] **Step 4: Correr y ver pasar.** 3 passed; `pytest -q` GLOBAL verde.
- [ ] **Step 5: Commit.** `git add src/pacusam/services.py tests/test_quality.py && git commit -m "feat(quality): conflicts + confusion_matrix + precision/recall"`

### Task B2: A/B y dataset health (servicios)

**Files:**
- Modify: `src/pacusam/services.py`
- Test: `tests/test_ab_health.py` (create)

- [ ] **Step 1: Test que falla.**
```python
from pacusam import db, services

def test_ab_summary_usa_baseline_manual():
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at) VALUES ('P',1,'[\"X\"]','t')")
    for i in range(10):
        conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label,shown_at,validated_at) VALUES (1,?,?,?,?, 'validated','X','t','t')",
                     (f"i{i}.jpg",f"/s/i{i}.jpg","X",0.8))
    conn.commit()
    ab = services.ab_summary(conn, 1)
    assert ab["manual_seconds"] > ab["al_seconds"] and ab["saved_pct"] > 0

def test_dataset_health_detecta_desbalance():
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at) VALUES ('P',1,'[\"X\",\"Y\"]','t')")
    for i in range(9):
        conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence,status,final_label,validated_at) VALUES (1,?,?,?,0.8,'validated',?, 't')",
                     (f"i{i}.jpg",f"/s/i{i}.jpg","X","X" if i<8 else "Y"))
    conn.commit()
    h = services.dataset_health(conn, 1)
    assert h["status"] in ("rojo","amarillo") and h["minority"]["label"] == "Y"
```
- [ ] **Step 2: Correr y ver fallar.** FAIL.
- [ ] **Step 3: Implementar:**
  - `ab_summary(conn, project_id)`: reusar `time_saved` (al_seconds/manual_seconds/saved_pct) + agregar `throughput_al` (img/hora con 3s/img) y `throughput_manual` (con 30s/img) y `concordance` (de `concordance()`). Devuelve dict para la tabla A/B.
  - `dataset_health(conn, project_id)`: sobre `class_distribution`, calcular ratio minoritaria/total; `status`: verde si min_pct>=33 (o 1/n*0.8), amarillo si >=15, rojo si <15; devolver `{status, minority:{label,percent}, message}`.
- [ ] **Step 4: Correr y ver pasar.** 2 passed; GLOBAL verde.
- [ ] **Step 5: Commit.** `git add src/pacusam/services.py tests/test_ab_health.py && git commit -m "feat(quality): ab_summary + dataset_health"`

### Task B3: UI del Bundle B (analytics: conflictos, matriz, A/B, salud)

**Files:**
- Modify: `src/pacusam/api.py` (contexto analytics), `src/pacusam/templates/analytics.html`

- [ ] **Step 1: Contexto.** En `analytics_page` de `api.py`, pasar `conflicts=services.conflicts(...)`, `confusion=services.confusion_matrix(...)`, `quality=services.quality_metrics(...)`, `ab=services.ab_summary(...)`, `health=services.dataset_health(...)`.
- [ ] **Step 2: Matriz de confusión.** Sección en `analytics.html`: tabla NxN (`confusion.labels` x `confusion.labels`) con Tailwind; la diagonal en `bg-approved-tint`, off-diagonal con valor>0 en `bg-rejected-tint`. Encabezados "Sugerido (filas) vs Final (columnas)".
- [ ] **Step 3: Conflictos.** Lista de cards de `conflicts`: thumbnail + "Modelo dijo <b>{{ c.suggested_label }}</b>, curador dijo <b>{{ c.final_label }}</b>". Si vacío: "Sin conflictos: el modelo coincidió con todas tus validaciones."
- [ ] **Step 4: Tabla A/B.** Tabla 2 columnas (Manual vs PACUSAM-AL) con filas: tiempo total, throughput (img/h), concordancia, con `ab`. Nota: "consistente con MONAI Label (50-80% de reducción)".
- [ ] **Step 5: Semáforo de salud.** Card con punto de color (`health.status`) + `health.message`. Recalcular "based on selection" no requerido (MVP); mostrar sobre el dataset completo.
- [ ] **Step 6: precision/recall.** Mini-tabla por clase de `quality.per_class` (label, precision, recall, accuracy global arriba).
- [ ] **Step 7: Verificación.** uvicorn → analytics muestra matriz, conflictos, A/B, salud, precision/recall con datos reales del seed. `pytest -q` GLOBAL verde.
- [ ] **Step 8: Commit.** `git add src/pacusam/api.py src/pacusam/templates/analytics.html && git commit -m "feat(quality-ui): matriz de confusion, conflictos, tabla A/B, salud de dataset"`

---

## Bundle C — Sello clínico-pro (OHIF + Kaapana)

### Task C1: Visor estilo OHIF (zoom/pan/invert/window-level) sobre la imagen

**Files:**
- Modify: `src/pacusam/templates/partials/image_card.html`, `base.html` (estilos del viewer si hace falta)

- [ ] **Step 1: Implementar (Alpine, sin backend).** Envolver el `<img>` del card en un contenedor `x-data="viewer()"` con: `scale` (zoom, rueda + botones +/-), `tx/ty` (pan por drag), `invert` (toggle), `brightness`/`contrast` (sliders Window/Level que mapean a `filter: brightness() contrast() invert()`), `reset`. Toolbar flotante con iconos lucide (zoom-in, zoom-out, move, contrast, sun, rotate-ccw). Hotkeys: `+`/`-` zoom, `i` invert, `r` reset (que NO colisionen con A/C/R de curado: usar las teclas del viewer solo cuando el mouse está sobre la imagen, o teclas distintas como `=`/`-`/`i`/`0`). Definir `function viewer(){...}` en un `<script>` en `base.html` (global, reusable).
- [ ] **Step 2: Metadata clínica mock.** Debajo o al costado del viewer, un bloque "Metadata" en mono con campos plausibles hardcodeados/derivados: `Modality: {{ 'CR' if project.domain=='chest_xray' else 'SM' }}`, `Dimensions`, `Pixel spacing` (mock), `Study date` (mock). Da aire DICOM sin pydicom.
- [ ] **Step 3: Verificación.** uvicorn → en curado, zoom con rueda, pan con drag, invert con botón, sliders W/L cambian brightness/contrast, reset vuelve. Confirmar que A/C/R de curado siguen funcionando. `pytest -q` GLOBAL verde (es UI, no debería tocar tests).
- [ ] **Step 4: Commit.** `git add src/pacusam/templates && git commit -m "feat(viewer): visor estilo OHIF (zoom/pan/invert/window-level) + metadata clinica mock"`

### Task C2: Gallery view + multiselect + bulk-validate

**Files:**
- Modify: `src/pacusam/services.py`, `src/pacusam/api.py`
- Create: `src/pacusam/templates/gallery.html`, `src/pacusam/templates/partials/gallery_grid.html`
- Test: `tests/test_bulk.py` (create)

- [ ] **Step 1: Test que falla (bulk validate).**
```python
from pacusam import db, services

def test_bulk_validate_confirma_la_sugerencia():
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at) VALUES ('P',1,'[\"X\",\"Y\"]','t')")
    ids = []
    for i in range(3):
        cur = conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence) VALUES (1,?,?,?,?)",
                           (f"i{i}.jpg",f"/s/i{i}.jpg","X",0.95))
        ids.append(cur.lastrowid)
    conn.commit()
    n = services.bulk_validate(conn, ids)
    assert n == 3
    assert services.progress(conn, 1)["validated"] == 3
```
- [ ] **Step 2: Correr y ver fallar.** FAIL.
- [ ] **Step 3: Implementar.** `services.bulk_validate(conn, image_ids)`: para cada id llama la lógica de `validate_image` con su propio `suggested_label` (confirma la sugerencia); devuelve la cantidad validada. (Reusar `validate_image` por id.) `services.gallery(conn, project_id, q=None, label=None)`: reusa `queue_list` (todas, con filtro de label) + filtro opcional `q` (LIKE sobre filename) — ver Task C3 para `q`.
- [ ] **Step 4: Correr y ver pasar.** 1 passed; GLOBAL verde.
- [ ] **Step 5: API + templates.** `GET /projects/{id}/gallery` (página `gallery.html`) lista la grilla (`gallery_grid.html`) con checkbox por imagen (Alpine set de ids). Botón "Aprobar seleccionadas" y "Aprobar todas con confianza >90%" → `POST /projects/{id}/bulk-validate` (Form/JSON con lista de ids) → `services.bulk_validate` → redirige/re-renderiza la grilla + toast "N aprobadas". Link a Gallery desde el proyecto y desde curate. Proteger con `_owned_project`.
- [ ] **Step 6: Verificación + Commit.** uvicorn: seleccionar varias, aprobar en lote, ver progreso subir. `pytest -q` verde. `git add ... && git commit -m "feat(gallery): vista grilla + multiselect + aprobar en lote"`

### Task C3: Búsqueda por id/nombre (US-18)

**Files:**
- Modify: `src/pacusam/services.py`, `src/pacusam/api.py`, `src/pacusam/templates/gallery.html`
- Test: agregar a `tests/test_bulk.py` o `tests/test_search.py` (create)

- [ ] **Step 1: Test que falla.**
```python
from pacusam import db, services

def test_gallery_busca_por_nombre_parcial():
    conn = db.connect(":memory:")
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at) VALUES ('P',1,'[\"X\"]','t')")
    for fn in ["rx_0001.jpg","rx_0002.jpg","bccd_5.jpg"]:
        conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence) VALUES (1,?,?,?,0.7)",(fn,"/s/"+fn,"X"))
    conn.commit()
    r = services.gallery(conn, 1, q="rx_000")
    assert len(r) == 2
    assert services.gallery(conn, 1, q="zzz") == []
```
- [ ] **Step 2: Correr y ver fallar.** FAIL.
- [ ] **Step 3: Implementar.** `services.gallery(conn, project_id, q=None, label=None)` filtra con `WHERE filename LIKE '%'||?||'%'` cuando `q`. En `api.py`, `GET /projects/{id}/gallery?q=&label=` pasa ambos. En `gallery.html`, input con `hx-get` `hx-trigger="keyup changed delay:300ms"` que recarga `gallery_grid.html`. Mensaje "Sin resultados" si vacío.
- [ ] **Step 4: Correr y ver pasar + Commit.** 2 passed; GLOBAL verde. `git add ... && git commit -m "feat(gallery): busqueda por id/nombre (US-18)"`

---

## Bundle D — Admin y trazabilidad (Kaapana roles)

### Task D1: Roles de usuario

**Files:**
- Modify: `src/pacusam/db.py`, `src/pacusam/auth.py`, `src/pacusam/seed.py`, `src/pacusam/api.py`
- Test: `tests/test_roles.py` (create)

- [ ] **Step 1: Test que falla.**
```python
from pacusam import db, auth

def test_create_user_default_curador_y_admin_explicito():
    conn = db.connect(":memory:")
    u = auth.create_user(conn, "c@x.com", "secreto1")
    assert u["role"] == "curador"
    a = auth.create_user(conn, "a@x.com", "secreto1", role="admin")
    assert a["role"] == "admin"
```
- [ ] **Step 2: Correr y ver fallar.** FAIL (users no tiene role / create_user no acepta role).
- [ ] **Step 3: Implementar.** `db.py` `users` agrega `role TEXT NOT NULL DEFAULT 'curador'`. `auth.create_user(conn, email, password, role="curador")` lo guarda y lo devuelve en el dict; `authenticate`/`get_user` devuelven `role`. En `seed.py`, sembrar un admin demo `admin@pacusam.org` / `admin1234` con role admin (además del curador demo). `require_user` ya devuelve el user dict (incluye role); guardarlo accesible para los templates (pasar `user` con role al contexto).
- [ ] **Step 4: Correr y ver pasar.** 1 passed; GLOBAL verde (re-seed cubre schema).
- [ ] **Step 5: Commit.** `git add ... && git commit -m "feat(admin): roles de usuario (curador/admin) + admin demo"`

### Task D2: Log de actividad (US-28)

**Files:**
- Modify: `src/pacusam/db.py`, `src/pacusam/services.py`, `src/pacusam/api.py`
- Test: `tests/test_activity.py` (create)

- [ ] **Step 1: Test que falla.**
```python
from pacusam import db, services

def test_log_y_listado_de_actividad():
    conn = db.connect(":memory:")
    services.log_activity(conn, user_id=1, action="validate", image_id=5, project_id=1)
    rows = services.list_activity(conn)
    assert rows[0]["action"] == "validate" and rows[0]["image_id"] == 5
```
- [ ] **Step 2: Correr y ver fallar.** FAIL.
- [ ] **Step 3: Implementar.** `db.py`: tabla `activity_log(id, user_id, action, image_id, project_id, created_at)`. `services.log_activity(conn, user_id, action, image_id=None, project_id=None)` inserta con timestamp; `services.list_activity(conn, user_id=None, action=None, limit=200)` lista filtrable (orden desc). Llamar `log_activity` desde las rutas `validate`/`reject`/`unreject`/`create_project`/`retrain` en `api.py` (con el user de sesión). No romper sus tests (la firma de las funciones de dominio no cambia; el log se hace en la capa API).
- [ ] **Step 4: Correr y ver pasar.** 1 passed; GLOBAL verde.
- [ ] **Step 5: Commit.** `git add ... && git commit -m "feat(admin): log de actividad (US-28) + escritura desde rutas"`

### Task D3: Vistas admin + gating de menús (US-26/27)

**Files:**
- Modify: `src/pacusam/api.py`, `src/pacusam/templates/base.html` (nav), `home.html`
- Create: `src/pacusam/templates/admin.html`

- [ ] **Step 1: Gating + ruta admin.** Dependency `require_admin` (basada en `require_user` + chequeo `user.role=='admin'`, sino 403/redirect a home con flash). `GET /admin` (página `admin.html`) visible solo para admin: lista de usuarios (email, role) y el **log de actividad** (`services.list_activity`) con filtros por usuario/acción (query params). Link "Administración" en el nav/home solo si `user.role=='admin'`.
- [ ] **Step 2: Roles en UI (US-27).** En `admin.html`, por cada usuario un control para cambiar role (curador/validador/admin) → `POST /admin/users/{id}/role` (solo admin) que actualiza `users.role`. Test de endpoint: admin puede, curador recibe 403.
- [ ] **Step 3: Test de endpoint.** `tests/test_admin_api.py`: admin ve `/admin` (200) y el curador es redirigido/403; cambiar role funciona para admin.
- [ ] **Step 4: Verificación.** Login admin demo → ve "Administración" con usuarios + log filtrable; login curador → no ve el menú ni accede a `/admin`. `pytest -q` GLOBAL verde.
- [ ] **Step 5: Commit.** `git add ... && git commit -m "feat(admin): vista de administracion (usuarios + roles + log) con gating"`

---

## Cierre

### Task Z: Verificación end-to-end + README

- [ ] **Step 1:** `PYTHONPATH=src .venv/bin/python -m pytest -q` → TODO verde.
- [ ] **Step 2:** Levantar uvicorn y recorrer: estrategia de sampling, entropy, contador de umbral, sparkline F1, matriz de confusión, conflictos, A/B, salud, visor OHIF, gallery+bulk, búsqueda, login admin → vista admin. Arreglar lo que aparezca.
- [ ] **Step 3:** Actualizar `README.md`: nuevas features + credenciales admin (`admin@pacusam.org`/`admin1234`) + mover de Roadmap a Hecho lo que corresponda (US-13/16/17/18/19/21/22/26/27/28).
- [ ] **Step 4: Commit.** `git add README.md && git commit -m "docs: README con bundles A/B/C/D"`

## Notas de integración (LEY, repetir para el ejecutor)
- No romper los 174 tests existentes. Params nuevos siempre opcionales al final con default que preserva comportamiento.
- Render vía `templating.render`; reusar macros de `partials/ui.html` y tokens de `tokens.css`; sin em-dashes, acentos correctos.
- Las teclas del visor (Bundle C) NO deben colisionar con A/C/R del curado.
- Schema: columnas nuevas con `DEFAULT`; es MVP, sin migraciones (re-seed). Mantener `seed.py` determinista.
- Autorización: rutas project-scoped via `_owned_project`; rutas admin via `require_admin`.
