# PACUSAM — Estilos arquitectónicos + Calidad (alineación white paper) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Materializar en código los estilos arquitectónicos del white paper (Pub-Sub, Event Processing, Pipes & Filters), cerrar criterios ISO/IEC 25010 baratos, y documentar la trazabilidad de las decisiones del MVP — todo manteniendo los 235 tests verdes.

**Architecture:** Se agrega un **event bus in-process** (`events.py`, dict de suscriptores, cero dependencias) que `services.py` usa para publicar 4 eventos de dominio. Los **suscriptores** (feedback loop de re-entrenamiento, logging) se registran SOLO en `create_app` — así las pruebas unitarias de dominio no se ven afectadas. La ingesta se refactoriza en un **pipeline de filtros encadenados** (Pipes & Filters). El resto son cierres puntuales (docstrings, validación de password, `/health`, perf test) + documentación de defensa.

**Tech Stack:** Python 3.10+, FastAPI, Jinja2/HTMX, SQLite (stdlib), pytest/pytest-bdd. **Sin dependencias nuevas.**

**Contexto de código (firmas reales):**
- `services.py`: `seed_images(conn, project_id, filenames)`, `validate_image(conn, image_id, label)`, `reject_image(conn, image_id, reason)`, `simulate_retrain(conn, project_id)`, `threshold_status(conn, project_id)` → `{threshold, validated, remaining, reached}`, `record_cycle(...)`, `progress(conn, project_id)`. Reusar `DomainError(code)`.
- `auth.py`: `create_user(conn, email, password, role="curador")` (lanza `DomainError('email_exists')`).
- `api.py`: `create_app(db_path=None)`, `require_user`, `_owned_project`, `_guard`, `_log(conn, user, action, image_id, project_id)` (best-effort), `_render_next_card(...)`, rutas. `app = create_app()` al final.
- venv: `.venv/bin/python`. Tests: `PYTHONPATH=src .venv/bin/python -m pytest -q`. **Baseline: 235 passed.**

**Reglas (LEY):** No romper los 235 tests. El bus es aditivo; los suscriptores que mutan estado (auto-retrain) se registran SOLO en `create_app`, no a nivel de import, para no afectar tests unitarios de dominio. Sin em-dashes en UI. Commits frecuentes (uno por tarea). Correr `pytest -q` GLOBAL al cierre de cada tarea.

---

## Nivel 1 — Estilos arquitectónicos

### Task 1: Event bus in-process (`events.py`) — estilo Publish-Subscribe

**Files:**
- Create: `src/pacusam/events.py`
- Test: `tests/test_events.py` (create)

- [ ] **Step 1: Test que falla.** Crear `tests/test_events.py`:
```python
from pacusam import events

def test_subscribe_y_publish_llama_handlers():
    bus = events.EventBus()
    recibidos = []
    bus.subscribe("ImagenValidada", lambda p: recibidos.append(p))
    bus.publish("ImagenValidada", {"image_id": 7})
    assert recibidos == [{"image_id": 7}]

def test_publish_sin_suscriptores_no_rompe():
    bus = events.EventBus()
    bus.publish("CicloFinalizo", {"project_id": 1})  # no debe lanzar

def test_un_handler_que_falla_no_corta_a_los_demas():
    bus = events.EventBus()
    ok = []
    bus.subscribe("X", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("X", lambda p: ok.append(1))
    bus.publish("X", {})  # best-effort: no propaga
    assert ok == [1]

def test_eventos_canonicos_declarados():
    # Los 4 eventos del white paper estan declarados como constantes.
    assert events.IMAGENES_SUBIDAS == "ImagenesSubidas"
    assert events.IMAGEN_VALIDADA == "ImagenValidada"
    assert events.UMBRAL_ALCANZADO == "UmbralAlcanzado"
    assert events.CICLO_FINALIZO == "CicloFinalizo"
```
- [ ] **Step 2: Correr y ver fallar.** `PYTHONPATH=src .venv/bin/python -m pytest tests/test_events.py -q` → FAIL.
- [ ] **Step 3: Implementar `src/pacusam/events.py`:**
```python
"""Event bus in-process (estilo Publish-Subscribe del white paper, A.7).

Materializa el estilo Pub-Sub SIN infraestructura (sin Celery/Redis): un bus
sincrono en memoria. El backend publica los 4 eventos canonicos del dominio y
los suscriptores (registrados en create_app) reaccionan. La entrega es
best-effort: un handler que falla no corta a los demas ni propaga al publisher.
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
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = {}

    def subscribe(self, event: str, handler: Handler) -> None:
        self._subs.setdefault(event, []).append(handler)

    def publish(self, event: str, payload: dict[str, Any]) -> None:
        for handler in list(self._subs.get(event, [])):
            try:
                handler(payload)
            except Exception:
                # Best-effort: un suscriptor que falla no afecta al publisher
                # ni a los demas suscriptores.
                pass

    def clear(self) -> None:
        self._subs.clear()


# Bus global del proceso. services.py publica aca; create_app suscribe.
bus = EventBus()
```
- [ ] **Step 4: Correr y ver pasar.** `... pytest tests/test_events.py -q` → 4 passed.
- [ ] **Step 5: Commit.** `git add src/pacusam/events.py tests/test_events.py && git commit -m "feat(arch): event bus in-process (estilo Publish-Subscribe, A.7)"`

### Task 2: Publicar los 4 eventos de dominio desde `services.py`

**Files:**
- Modify: `src/pacusam/services.py`
- Test: `tests/test_events_domain.py` (create)

- [ ] **Step 1: Test que falla.** Crear `tests/test_events_domain.py`:
```python
from pacusam import db, services, events

def _proj(conn, threshold=2):
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at,retrain_threshold) VALUES ('P',1,'[\"X\",\"Y\"]','t',?)", (threshold,))
    return 1

def _img(conn, pid, fn, conf=0.6, sug="X"):
    cur = conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence) VALUES (?,?,?,?,?)",
                       (pid, fn, "/s/"+fn, sug, conf))
    return cur.lastrowid

def test_seed_images_publica_imagenes_subidas():
    conn = db.connect(":memory:"); pid = _proj(conn)
    got = []
    events.bus.clear(); events.bus.subscribe(events.IMAGENES_SUBIDAS, lambda p: got.append(p))
    services.seed_images(conn, pid, ["a.jpg", "b.jpg"])
    assert got and got[-1]["project_id"] == pid and got[-1]["count"] == 2
    events.bus.clear()

def test_validate_publica_imagen_validada():
    conn = db.connect(":memory:"); pid = _proj(conn, threshold=99)
    i = _img(conn, pid, "a.jpg")
    got = []
    events.bus.clear(); events.bus.subscribe(events.IMAGEN_VALIDADA, lambda p: got.append(p))
    services.validate_image(conn, i, "X")
    assert got and got[-1]["image_id"] == i and got[-1]["project_id"] == pid
    events.bus.clear()

def test_umbral_alcanzado_se_publica_al_cruzar_el_umbral():
    conn = db.connect(":memory:"); pid = _proj(conn, threshold=2)
    i1 = _img(conn, pid, "a.jpg"); i2 = _img(conn, pid, "b.jpg")
    got = []
    events.bus.clear(); events.bus.subscribe(events.UMBRAL_ALCANZADO, lambda p: got.append(p))
    services.validate_image(conn, i1, "X")   # validated=1 < 2 -> no dispara
    assert got == []
    services.validate_image(conn, i2, "X")   # validated=2 == 2 -> dispara UNA vez
    assert len(got) == 1 and got[0]["project_id"] == pid
    events.bus.clear()

def test_simulate_retrain_publica_ciclo_finalizo():
    conn = db.connect(":memory:"); pid = _proj(conn, threshold=99)
    _img(conn, pid, "a.jpg"); _img(conn, pid, "b.jpg")
    got = []
    events.bus.clear(); events.bus.subscribe(events.CICLO_FINALIZO, lambda p: got.append(p))
    services.simulate_retrain(conn, pid)
    assert got and got[-1]["project_id"] == pid
    events.bus.clear()
```
- [ ] **Step 2: Correr y ver fallar.** `... pytest tests/test_events_domain.py -q` → FAIL.
- [ ] **Step 3: Implementar.** En `services.py`, `import` el bus (`from pacusam import events` o `from pacusam.events import bus, ...`). Publicar (payload incluye `conn` para que el suscriptor del feedback loop pueda actuar):
  - En `seed_images`, al final (tras insertar), si `count > 0`: `events.bus.publish(events.IMAGENES_SUBIDAS, {"conn": conn, "project_id": project_id, "count": count})`.
  - En `validate_image`, tras marcar validada y ANTES de retornar: `events.bus.publish(events.IMAGEN_VALIDADA, {"conn": conn, "image_id": image_id, "project_id": project_id})`. Luego calcular `ts = threshold_status(conn, project_id)`; si `ts["validated"] == ts["threshold"]` (cruce exacto): `events.bus.publish(events.UMBRAL_ALCANZADO, {"conn": conn, "project_id": project_id, "validated": ts["validated"], "threshold": ts["threshold"]})`.
  - En `simulate_retrain`, en el path 'ok' al final (tras `record_cycle`): `events.bus.publish(events.CICLO_FINALIZO, {"conn": conn, "project_id": project_id, "improvement_pct": <el valor calculado>})`.
  - `project_id` en `validate_image`: obtenerlo de la fila de la imagen (ya se consulta la imagen). Importante: publicar NO debe cambiar el valor de retorno de estas funciones.
- [ ] **Step 4: Correr y ver pasar.** `... pytest tests/test_events_domain.py -q` → 4 passed. Luego `pytest -q` GLOBAL → **235 passed** (los suscriptores NO están registrados a nivel módulo, así que el dominio no auto-reentrenará en otros tests).
- [ ] **Step 5: Commit.** `git add src/pacusam/services.py tests/test_events_domain.py && git commit -m "feat(arch): publicar los 4 eventos de dominio (ImagenesSubidas/ImagenValidada/UmbralAlcanzado/CicloFinalizo)"`

### Task 3: Suscriptores en `create_app` (feedback loop) + Event Processing (SEP/OEP/CEP)

**Files:**
- Modify: `src/pacusam/api.py`
- Test: `tests/test_feedback_loop.py` (create)

- [ ] **Step 1: Test que falla.** Crear `tests/test_feedback_loop.py`:
```python
from fastapi.testclient import TestClient
from pacusam import db, services, events
from pacusam.api import create_app

def test_umbral_dispara_reentrenamiento_automatico(tmp_path):
    # Estilo CEP: al cruzar el umbral de validadas, se dispara un ciclo de AL
    # automaticamente (feedback loop de Pipes & Filters via Pub-Sub).
    app = create_app(db_path=str(tmp_path / "t.db"))  # registra los suscriptores
    conn = db.connect(str(tmp_path / "t.db"))
    # proyecto chico con umbral 2
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('u@x.com','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at,retrain_threshold) VALUES ('P',1,'[\"X\"]','t',2)")
    pid = conn.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1").fetchone()["id"]
    ids = [conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence) VALUES (?,?,?,?,?)",
                        (pid, f"i{i}.jpg", f"/s/i{i}.jpg", "X", 0.6)).lastrowid for i in range(2)]
    conn.commit()
    before = len(services.list_cycles(conn, pid))
    services.validate_image(conn, ids[0], "X")
    services.validate_image(conn, ids[1], "X")   # cruza umbral -> UmbralAlcanzado -> retrain
    after = len(services.list_cycles(conn, pid))
    assert after == before + 1   # se registro un ciclo automaticamente
```
- [ ] **Step 2: Correr y ver fallar.** `... pytest tests/test_feedback_loop.py -q` → FAIL (no hay suscriptor que reentrene).
- [ ] **Step 3: Implementar.** En `api.py`, dentro de `create_app` (tras crear `app.state.conn`), registrar suscriptores en el bus:
```python
from pacusam import events

# Estilo Pub-Sub + feedback loop de Pipes & Filters: al alcanzar el umbral
# de imagenes validadas (Complex Event Processing: evento derivado de N
# ImagenValidada), se dispara automaticamente un ciclo de re-entrenamiento.
def _on_umbral(payload):
    services.simulate_retrain(payload["conn"], payload["project_id"])

events.bus.subscribe(events.UMBRAL_ALCANZADO, _on_umbral)
```
  Guarda de idempotencia de suscripción: para no duplicar suscriptores si `create_app` se llama varias veces (tests), antes de suscribir hacé `events.bus.clear()` al inicio del wiring de eventos (o usá un flag). Recomendado: al comienzo del bloque de eventos, `events.bus.clear()` y volver a suscribir, así cada app tiene su set limpio.
- [ ] **Step 4: Documentar Event Processing.** En `api.py` (docstring de `create_app` o un comentario en la sección de eventos) y en `events.py`, clasificar explícitamente:
  - **SEP (Single Event Processing):** cada `POST /validate|reject` es una acción uno-a-uno (`ImagenValidada`).
  - **OEP (Online Event Processing):** el score de confianza se ve al instante y la cola se reordena por incertidumbre en cada acción (`_render_next_card` → `queue_next`).
  - **CEP (Complex Event Processing):** `UmbralAlcanzado` es un evento derivado de N `ImagenValidada` acumuladas (umbral), que dispara el re-entrenamiento.
- [ ] **Step 5: Correr y ver pasar.** `... pytest tests/test_feedback_loop.py -q` → 1 passed. `pytest -q` GLOBAL → **235 passed** (la semilla usa threshold=20; ningún test existente valida 20 imágenes, así que el auto-retrain no se dispara en ellos).
- [ ] **Step 6: Commit.** `git add src/pacusam/api.py tests/test_feedback_loop.py && git commit -m "feat(arch): feedback loop UmbralAlcanzado->retrain (CEP) + clasificacion SEP/OEP/CEP"`

---

## Nivel 2 — Cierres ISO/IEC 25010

### Task 4: Validación de password server-side (Seguridad)

**Files:**
- Modify: `src/pacusam/auth.py`
- Test: `tests/test_password_policy.py` (create)

- [ ] **Step 1: Test que falla.**
```python
import pytest
from pacusam import db, auth
from pacusam.services import DomainError

def test_password_corta_es_rechazada():
    conn = db.connect(":memory:")
    with pytest.raises(DomainError) as e:
        auth.create_user(conn, "a@b.com", "123")
    assert e.value.code == "password_too_short"

def test_password_valida_ok():
    conn = db.connect(":memory:")
    u = auth.create_user(conn, "a@b.com", "secreto1")
    assert u["email"] == "a@b.com"
```
- [ ] **Step 2: Correr y ver fallar.** FAIL.
- [ ] **Step 3: Implementar.** En `auth.create_user`, al inicio: `if len(password) < 6: raise DomainError("password_too_short")`. Mapear en `api.py` `_STATUS` `password_too_short` → 422 (o renderizar el form de registro con el error). El template `register.html` ya tiene `minlength=6` client-side; ahora hay regla server-side.
- [ ] **Step 4: Correr y ver pasar.** 2 passed; `pytest -q` GLOBAL verde.
- [ ] **Step 5: Commit.** `git add src/pacusam/auth.py src/pacusam/api.py tests/test_password_policy.py && git commit -m "feat(seguridad): validacion server-side de password (ISO 25010)"`

### Task 5: Endpoint `/health` + test de performance (Fiabilidad/Eficiencia)

**Files:**
- Modify: `src/pacusam/api.py`
- Test: `tests/test_health_perf.py` (create)

- [ ] **Step 1: Test que falla.**
```python
import time
from fastapi.testclient import TestClient
from pacusam.api import create_app

def test_health_ok(tmp_path):
    c = TestClient(create_app(db_path=str(tmp_path / "t.db")))
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"

def test_login_carga_rapido(tmp_path):
    # Evidencia de Eficiencia (ISO 25010): la pagina responde holgadamente < 3s.
    c = TestClient(create_app(db_path=str(tmp_path / "t.db")))
    t0 = time.perf_counter()
    r = c.get("/login")
    dt = time.perf_counter() - t0
    assert r.status_code == 200 and dt < 3.0
```
- [ ] **Step 2: Correr y ver fallar.** FAIL (no hay /health).
- [ ] **Step 3: Implementar.** En `api.py`, ruta pública (sin auth) `GET /health` → `JSONResponse({"status": "ok", "version": __version__})` (importar `__version__` de `pacusam`). No requiere sesión.
- [ ] **Step 4: Correr y ver pasar.** 2 passed; GLOBAL verde.
- [ ] **Step 5: Commit.** `git add src/pacusam/api.py tests/test_health_perf.py && git commit -m "feat(calidad): endpoint /health + test de performance (ISO 25010 Fiabilidad/Eficiencia)"`

### Task 6: Docstrings en `api.py` (Mantenibilidad >= 80% doc coverage)

**Files:**
- Modify: `src/pacusam/api.py`
- Test: `tests/test_doc_coverage.py` (create)

- [ ] **Step 1: Test que falla.**
```python
import ast, pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "pacusam"

def _doc_ratio(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    if not funcs:
        return 1.0
    documented = sum(1 for f in funcs if ast.get_docstring(f))
    return documented / len(funcs)

def test_cobertura_de_docstrings_global_supera_80():
    ratios = []
    total_funcs = total_doc = 0
    for p in SRC.glob("*.py"):
        import ast as _ast
        tree = _ast.parse(p.read_text(encoding="utf-8"))
        funcs = [n for n in _ast.walk(tree) if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))]
        total_funcs += len(funcs)
        total_doc += sum(1 for f in funcs if _ast.get_docstring(f))
    assert total_funcs and (total_doc / total_funcs) >= 0.80
```
- [ ] **Step 2: Correr y ver fallar.** FAIL (api.py route handlers sin docstring bajan el global por debajo de 80%).
- [ ] **Step 3: Implementar.** Agregar un docstring de UNA línea a cada route handler / función interna de `api.py` que no tenga (login, register, home, project_detail, curate_page, queue_fragment, validate/reject/unreject, retrain, analytics_page, export, bulk_validate, admin, health, _log, _on_umbral, etc.). Describir qué hace la ruta. No cambiar lógica.
- [ ] **Step 4: Correr y ver pasar.** 1 passed (ratio >= 0.80); GLOBAL verde.
- [ ] **Step 5: Commit.** `git add src/pacusam/api.py tests/test_doc_coverage.py && git commit -m "docs(mantenibilidad): docstrings en api.py + test de cobertura de doc >=80% (ISO 25010)"`

### Task 7: Verificar/cerrar BDD ejecutable (Funcionalidad / A.9)

**Files:**
- Modify/Verify: `tests/test_curado.py`, `tests/features/curado.feature`, `tests/conftest.py`

- [ ] **Step 1: Verificar que `curado.feature` se ejecuta.** Run: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_curado.py -v`. Si los escenarios aparecen como tests ejecutados (pytest-bdd), está OK (no hacer nada salvo confirmar en el Step 4). Si NO se ejecuta ningún escenario (el `.feature` es documental), seguir al Step 2.
- [ ] **Step 2 (solo si falta):** En `tests/test_curado.py` asegurar `from pytest_bdd import scenarios` + `scenarios("curado.feature")` y que `conftest.py` tenga los step-defs (given/when/then) que mapean el Gherkin a llamadas de dominio/API. Si faltan step-defs, escribirlos para los 3 escenarios (cola por incertidumbre, validar actualiza progreso, rechazar+motivo excluye).
- [ ] **Step 3: Correr.** `... pytest tests/test_curado.py -v` → los escenarios del `.feature` aparecen como PASSED.
- [ ] **Step 4: Confirmar GLOBAL.** `pytest -q` → verde (sin bajar el conteo).
- [ ] **Step 5: Commit (si hubo cambios).** `git add tests/ && git commit -m "test(funcionalidad): criterios de aceptacion BDD ejecutables (Gherkin, A.9)"`

---

## Nivel 3 — Pipes & Filters explícito (ingesta)

### Task 8: Refactor de la ingesta en filtros encadenados

**Files:**
- Create: `src/pacusam/pipeline.py`
- Modify: `src/pacusam/services.py` (`seed_images` usa el pipeline)
- Test: `tests/test_pipeline.py` (create)

- [ ] **Step 1: Test que falla.** Crear `tests/test_pipeline.py`:
```python
from pacusam import pipeline

def test_run_pipeline_encadena_filtros_en_orden():
    pasos = []
    def f1(ctx): pasos.append("f1"); ctx["a"] = 1; return ctx
    def f2(ctx): pasos.append("f2"); ctx["b"] = ctx["a"] + 1; return ctx
    out = pipeline.run_pipeline([f1, f2], {"fn": "x.jpg"})
    assert pasos == ["f1", "f2"] and out["a"] == 1 and out["b"] == 2

def test_filtro_clasificar_asigna_label_y_confianza():
    ctx = pipeline.filtro_clasificar({"filename": "rx_0001.jpg", "labels": ["NORMAL", "PNEUMONIA"]})
    assert ctx["suggested_label"] in ("NORMAL", "PNEUMONIA")
    assert 0.5 <= ctx["confidence"] <= 0.99

def test_filtro_validar_formato_acepta_jpg_png_dcm_y_rechaza_otros():
    assert pipeline.filtro_validar_formato({"filename": "a.jpg"})["formato_ok"] is True
    assert pipeline.filtro_validar_formato({"filename": "a.txt"})["formato_ok"] is False
```
- [ ] **Step 2: Correr y ver fallar.** FAIL.
- [ ] **Step 3: Implementar `src/pacusam/pipeline.py`** (estilo Pipes & Filters):
```python
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
```
- [ ] **Step 4: Correr y ver pasar.** 3 passed.
- [ ] **Step 5: Integrar en `seed_images`.** Refactorizar `services.seed_images` para que, por cada filename, arme `ctx = {"filename": fn, "labels": <labels del proyecto>}`, corra `pipeline.run_pipeline(pipeline.INGESTA, ctx)`, y use `ctx["suggested_label"]`/`ctx["confidence"]` para el INSERT (en vez de llamar `classifier.suggest` inline). **Preservar la idempotencia por `(project_id, filename)`** y el valor de retorno (count). Mantener el `events.bus.publish(IMAGENES_SUBIDAS, ...)` de la Task 2.
- [ ] **Step 6: Correr GLOBAL.** `pytest -q` → **235 passed** (seed_images mantiene el mismo comportamiento observable). Si algún test de seed compara confidencias exactas, deben seguir iguales (el pipeline usa el mismo `classifier.suggest`).
- [ ] **Step 7: Commit.** `git add src/pacusam/pipeline.py src/pacusam/services.py tests/test_pipeline.py && git commit -m "feat(arch): ingesta como Pipes & Filters (filtros encadenados, A.7)"`

---

## Transversal — Documentación de defensa

### Task 9: Tabla de trazabilidad + completar `arquitectura.md`

**Files:**
- Create: `docs/trazabilidad.md`
- Modify: `docs/arquitectura.md`

- [ ] **Step 1: Crear `docs/trazabilidad.md`** con una tabla que mapee cada decisión del MVP a: cláusula del white paper + actividad del curso (A.4/A.7/A.8/A.9/A.10/A.11) + riesgo (R03/R04). Filas mínimas:
  - Monolito Layered ← M2 walking skeleton (A.10), Layered es uno de los estilos (A.7).
  - AL mockeado ← "el MVP arranca sobre el dataset semilla mockeado" (white paper) + R03 (excluir AL si complejo) (A.11). Matiz: uncertainty sampling real.
  - Pub-Sub / Event Processing in-process ← A.7 (materializados ahora en `events.py`).
  - Pipes & Filters ← A.7 (materializado en `pipeline.py`).
  - SQLite + filesystem ← presupuesto + 2 part-time + R04 almacenamiento local (A.11).
  - Jinja/HTMX ← costo/equipo, menos SP (A.4/A.8).
  - Roles/admin/log ← E9, A.4.
  Una columna "Estado en el MVP" (hecho/mock/diferido) por fila.
- [ ] **Step 2: Completar la sección de calidad de `arquitectura.md`.** Reemplazar la sección "Atributos de calidad priorizados" (hoy "Pendiente") por la tabla ISO/IEC 25010 estado-vs-criterio: Funcionalidad (235 tests), Fiabilidad (WAL + /health), Usabilidad (3 wow-moments, prueba en defensa), Eficiencia (/health perf < 3s), Seguridad (pbkdf2 + cookies + IDOR + datasets públicos sin PII = mitiga R04), Compatibilidad (export CSV/JSON; JPG/PNG/DICOM: import en roadmap), Mantenibilidad (doc coverage >= 80%), Portabilidad (render.yaml). Indicar cuáles son reales y cuáles se defienden por scope (R03/M2).
- [ ] **Step 3: Verificación.** Leer ambos docs y confirmar que no quedan placeholders y que reflejan el estado real.
- [ ] **Step 4: Commit.** `git add docs/trazabilidad.md docs/arquitectura.md && git commit -m "docs(defensa): tabla de trazabilidad decision->white paper/actividad/riesgo + ISO 25010 en arquitectura.md"`

---

## Cierre

### Task Z: Verificación end-to-end + README

- [ ] **Step 1:** `PYTHONPATH=src .venv/bin/python -m pytest -q` → TODO verde (>= 235 + los nuevos).
- [ ] **Step 2:** Levantar uvicorn (`rm -f pacusam.db*` antes) y recorrer: curar imágenes hasta cruzar el umbral de un proyecto chico (o setear threshold bajo) y confirmar que el **re-entrenamiento se dispara solo** (feedback loop) con su toast/ciclo nuevo en analytics; `/health` responde 200. Arreglar lo que aparezca.
- [ ] **Step 3:** Actualizar `README.md`: sección "Arquitectura" mencionando los estilos materializados (Pub-Sub `events.py`, Pipes & Filters `pipeline.py`, Event Processing SEP/OEP/CEP) y link a `docs/trazabilidad.md`. Mover de roadmap lo que aplique.
- [ ] **Step 4: Commit.** `git add README.md && git commit -m "docs: README con estilos arquitectonicos materializados + trazabilidad"`

## Notas de integración (LEY, repetir para el ejecutor)
- No romper los 235 tests. El bus es aditivo; los suscriptores que mutan (auto-retrain) se registran SOLO en `create_app`, nunca a nivel de import de `services`.
- `events.bus.clear()` al inicio del wiring de eventos en `create_app` para evitar suscriptores duplicados entre tests que crean varias apps.
- Publicar eventos NO debe cambiar el valor de retorno de `seed_images`/`validate_image`/`simulate_retrain`.
- El pipeline usa el mismo `classifier.suggest` → confidencias idénticas (no rompe tests de seed).
- Sin em-dashes en UI/docs visibles; acentos correctos.
- Deploy real a Render es un paso manual del dashboard (la config `render.yaml` ya está lista); no es parte de este plan de código.
