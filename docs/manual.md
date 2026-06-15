# Manual de uso y mapa de funcionalidades - PACUSAM

MVP academico de curado de imagenes medicas con Active Learning. LCD-UNSAM, Ing. de Software,
Grupo 9 (Mateo Romano + Leandro Escudero), 1C 2026. Cliente: CIMeT-UNSAM.

Este documento sirve para dos cosas:

1. Practicar la demo punta a punta (levantar, resetear, recorrer cada pantalla).
2. Responder en la defensa "donde implementaste X" con una referencia real `archivo:funcion`.

Todas las referencias salen del codigo real en `src/pacusam/`. Si algo no esta aca, no esta en
el MVP (ver la seccion Roadmap al final).

---

## 1. Levantar, resetear y re-sembrar

### Requisitos

- Python 3.10+ (el repo corre sobre 3.14, ver `.python-version`).
- El virtualenv ya vive en `.venv/`. No hay `npm` ni build de frontend: el vendor de
  HTMX/Alpine/Tailwind/Lucide se sirve local desde `static/vendor`.

### Levantar el servidor

```bash
PYTHONPATH=src PACUSAM_DB=pacusam.db \
  /Users/mateoromano/Documents/mvp_pacusam/.venv/bin/python \
  -m uvicorn pacusam.api:app --reload
```

Abrir: http://127.0.0.1:8000

- `PYTHONPATH=src`: el paquete `pacusam` vive bajo `src/` (layout src).
- `PACUSAM_DB=pacusam.db`: archivo SQLite que usa la app. `db.connect` resuelve este env var
  (`src/pacusam/db.py:connect`); sin el, cae al default `pacusam.db`.
- `--reload`: recarga en caliente al editar codigo (solo para desarrollo).

La app se arma en `src/pacusam/api.py:create_app` (orden canonico: app -> conexion -> StaticFiles
-> SessionMiddleware -> exception handler -> rutas -> `seed.seed_if_empty`).

### Credenciales sembradas

| Rol | Email | Password | Fuente unica |
|---|---|---|---|
| Curador | `demo@pacusam.org` | `demo1234` | `src/pacusam/seed.py` (`DEMO_EMAIL` / `DEMO_PASSWORD`) |
| Admin | `admin@pacusam.org` | `admin1234` | `src/pacusam/seed.py` (`ADMIN_EMAIL` / `ADMIN_PASSWORD`) |

El curador ve sus 2 proyectos. El admin ademas ve el enlace a `/admin`.

### Resetear / re-sembrar de cero

La DB se crea sola y se **re-siembra solo si esta vacia** (no pisa datos existentes). Para
empezar de cero:

```bash
rm /Users/mateoromano/Documents/mvp_pacusam/pacusam.db
# (si existen) rm pacusam.db-wal pacusam.db-shm   # archivos WAL de SQLite
```

Al volver a levantar, `src/pacusam/seed.py:seed_if_empty` detecta que no hay proyectos y vuelve a
sembrar el demo completo (usuarios + 2 proyectos + imagenes + progreso vivo + 2 ciclos AL). El
re-seed es **determinista** (ancla de tiempo fija `_SEED_ANCHOR`, sin `random`), asi los numeros
de analytics salen iguales siempre.

### Que siembra el demo

`seed.py:seed_demo` + `seed.py:_seed_live_progress`:

- 2 proyectos del curador:
  1. "Radiografias de torax", labels `NORMAL` / `PNEUMONIA`.
  2. "Celulas sanguineas", labels `NEUTROPHIL` / `EOSINOPHIL` / `LYMPHOCYTE` / `MONOCYTE`.
- ~40 imagenes reales por proyecto (desde `static/datasets/<project_id>/`; si el dir no existe,
  no rompe, queda sin imagenes).
- Progreso parcial vivo: ~35% validadas, unos pocos rechazos, el resto pendiente, dejando siempre
  al menos 1 pendiente para la demo. Concordancia creible ~85.7% (se corrige ~1 de cada 7).
- 2 ciclos AL de ejemplo con F1/AUC crecientes (`record_cycle`, F1 0.86 -> 0.90).
- Umbral de re-entrenamiento del demo = 20 validadas (`retrain_threshold` en `_ensure_project`).

### Correr los tests

```bash
PYTHONPATH=src PACUSAM_DB=:memory: ./.venv/bin/python -m pytest -q
```

Estado actual: **248 tests verdes** (unitarios de dominio/auth + endpoints + integracion + BDD en
Gherkin espanol + estilos arquitectonicos + calidad ISO 25010). Healthcheck publico: `GET /health`
devuelve `{"status": "ok", "version": ...}` (`api.py:health`).

---

## 2. Pantalla por pantalla

Toda la UI se renderiza server-side via `templating.render` (`src/pacusam/templating.py`). Las
acciones de curado usan HTMX: el server devuelve un fragmento HTML que reemplaza un nodo
(`hx-target` / `hx-swap`), sin recargar la pagina.

### 2.1 Login (`GET/POST /login`)

- **Que hace:** autentica al usuario y abre sesion (cookie firmada por `SessionMiddleware`).
- **Como se usa:** email + contrasena -> "Ingresar". Credenciales invalidas -> re-renderiza el
  form con error y status 401. Las credenciales demo aparecen al pie del form.
- **Codigo:** `api.py:login_page` (GET) y `api.py:login_action` (POST), que llaman a
  `auth.authenticate` (`src/pacusam/auth.py`). Template: `templates/login.html`.
- **Atajos:** ninguno (el campo email tiene `autofocus`).

### 2.2 Registro (`GET/POST /register`)

- **Que hace:** crea un curador nuevo y lo loguea automaticamente.
- **Como se usa:** email + contrasena (minimo 6 chars). Errores posibles: email ya registrado
  (`email_exists`, 409 a nivel dominio) o contrasena corta (`password_too_short`, 422). Se
  re-renderiza el form con el mensaje. El rol por defecto es `curador`.
- **Validacion:** server-side en `auth.create_user` (no solo el `minlength` del HTML).
- **Codigo:** `api.py:register_page` / `api.py:register_action` -> `auth.create_user`. Hash
  PBKDF2-HMAC-SHA256 con `auth.hash_password` (stdlib, sin deps C). Template:
  `templates/register.html`.

### 2.3 Home / Proyectos (`GET /`)

- **Que hace:** lista los proyectos del usuario logueado, cada uno con su barra de progreso.
- **Como se usa:** click en una tarjeta -> detalle del proyecto. Boton "Nuevo proyecto" despliega
  el formulario de creacion (Alpine `x-show`). Si sos admin, aparece el enlace "Administracion".
- **Crear proyecto:** nombre (obligatorio, <=100 chars), descripcion, dominio, etiquetas separadas
  por coma. Al crear, si hay un dataset en disco para ese `project_id`, se siembran las imagenes.
  Errores de nombre vuelven a la home con un flash.
- **Codigo:** `api.py:home` (lista + progreso), `api.py:create_project_action` (POST `/projects`)
  -> `services.create_project` + `services.seed_images`. Templates: `templates/home.html`,
  `templates/partials/project_card.html`.

### 2.4 Detalle de proyecto (`GET /projects/{id}`)

- **Que hace:** muestra nombre, descripcion, chips de etiquetas y el resumen de progreso
  (validadas / rechazadas / pendientes).
- **Como se usa:** botones "Empezar a curar" (-> curado) y "Analitica" (-> analytics).
- **Autorizacion:** solo el dueño. Un proyecto ajeno devuelve **404** (no 403) para no filtrar
  existencia (`api.py:_owned_project`, decision D05 / anti-IDOR).
- **Codigo:** `api.py:project_detail` -> `services.get_project` + `services.progress`. Template:
  `templates/project.html`.

### 2.5 Curado (`GET /projects/{id}/curate`) - la pantalla estrella

Layout de altura fija: topbar + card de 2 columnas (info a la izquierda, visor a la derecha) +
filmstrip abajo. La cola se carga al abrir via HTMX (`hx-trigger="load"` -> `GET .../queue`).

#### Atajos de teclado

Definidos en `templates/partials/image_card.html` (Alpine `@keydown.window`) y en
`templates/curate.html`:

| Tecla | Accion |
|---|---|
| `A` | Confirmar la sugerencia del modelo (valida con `suggested_label`) y auto-avanzar |
| `C` | Corregir: despliega las otras etiquetas para elegir la correcta |
| `R` | Rechazar: abre el panel de motivo |
| `Esc` | Cerrar / cancelar el panel abierto (corregir o rechazar) |
| `?` (Shift+/) | Abrir/cerrar el overlay de atajos |

#### Visor estilo OHIF (panel derecho, imagen sobre fondo negro)

Hotkeys **scoped al visor** (el contenedor tiene `tabindex` y `@keydown` sin `.window`, para no
pisar A/C/R). Hacer foco/click en la imagen y:

| Tecla | Accion | Boton equivalente |
|---|---|---|
| `=` o `+` | Zoom in (acercar) | lupa + |
| `-` | Zoom out (alejar) | lupa - |
| `0` | Reset (restablecer zoom/pan/invert) | rotar |
| `i` | Invertir escala de grises | contraste |

Con zoom > 1 se puede arrastrar (pan) con el mouse; aparece un indicador `x.xx`.

#### Flujo de curado

- **Confirmar (A):** POST `/images/{id}/validate` con `label = suggested_label`.
- **Corregir (C):** despliega `other_labels`; cada chip hace POST `/images/{id}/validate` con esa
  etiqueta. Binario = 1 chip, multiclase = N.
- **Rechazar (R):** abre un `<select>` de motivos; "Confirmar rechazo" hace POST
  `/images/{id}/reject` con `reason`. El boton queda deshabilitado hasta elegir motivo.
- **Auto-avance:** cada accion devuelve la **proxima** imagen + progreso, reemplazando
  `#image-card` (`hx-swap="outerHTML"`). El filmstrip se actualiza fuera de banda (OOB).
- **Fin de cola:** micro-celebracion ("Dataset curado!") con confetti y enlace a analytics.
- **Codigo:** `api.py:curate_page`, `api.py:queue_fragment` (`GET .../queue`),
  `api.py:validate` / `api.py:reject` / `api.py:unreject`. El render del card lo arma
  `api.py:_render_next_card`. Dominio: `services.validate_image`, `services.reject_image`,
  `services.unreject_image`, `services.queue_next`, `services.queue_list`. Templates:
  `templates/curate.html`, `templates/partials/image_card.html`,
  `templates/partials/filmstrip.html`.

#### Como ver cada feature destacada en esta pantalla

- **Uncertainty sampling (cola ordenada):** la proxima imagen es siempre la mas dudosa
  (`1 - confianza` mas alto). Lo calcula `services.queue_next` (default `strategy="uncertainty"`,
  orden en `services._order_rows`). El panel muestra "Incertidumbre (proxy 1 - confianza)".
- **Selector de estrategia:** topbar con 3 botones (Incertidumbre / Aleatoria / Secuencial). Cada
  uno re-pide `GET .../queue?strategy=...` y reordena **solo la proxima imagen**. El filmstrip
  siempre queda en uncertainty por diseno. Normalizacion en `api.py:_norm_strategy`; estrategias
  validas en `_STRATEGIES`; orden por estrategia en `services._order_rows`.
- **Filmstrip de miniaturas:** tira horizontal abajo, miniaturas REALES ordenadas por
  incertidumbre, con borde por status (verde validada / rojo rechazada / gris pendiente) y un ring
  azul en la proxima a etiquetar. Cada miniatura muestra `u <uncertainty>`. Fuente:
  `services.queue_list` + `templates/partials/filmstrip.html`.
- **Filtro por etiqueta (US-17):** chips arriba a la derecha del filmstrip ("Todas" + una por
  clase con su conteo). Filtran **solo el filmstrip** por `suggested_label` via
  `GET .../queue?label=...`. Macro `filter_chips` en `templates/partials/ui.html`; conteos en
  `services.label_counts`.
- **Aprobar en lote >90% (bulk):** boton "Aprobar pendientes con confianza >90%" en el panel
  izquierdo. POST `/projects/{id}/bulk-validate` SIN ids: el server arma la lista de pendientes
  propias con `confidence >= 0.9` y las valida con su propia sugerencia. Devuelve un toast
  "N aprobadas". Codigo: `api.py:bulk_validate_action` -> `services.bulk_validate`. El endpoint
  filtra los ids al proyecto antes de validar (fix IDOR).
- **Contador hacia el umbral + feedback loop (CEP):** caja "Hacia el proximo re-entrenamiento"
  con `validadas / umbral` y mini-barra. Al cruzar el umbral exacto, `services.validate_image`
  publica el evento `UmbralAlcanzado`, y el suscriptor registrado en `api.py:create_app`
  (`_on_umbral`) dispara `services.simulate_retrain` **automaticamente** (re-entrenamiento solo,
  sin tocar un boton). En la card aparece "UmbralAlcanzado: el modelo se re-entrena" con enlace a
  analytics. Umbral del demo = 20 (sembrado por `seed.py`). Para verlo en vivo: curar validando
  hasta cruzar las 20 validadas (o resetear y usar un proyecto con umbral mas bajo).
- **Rechazo reversible (US-12):** una imagen rechazada aparece en el filmstrip con boton
  "Deshacer" (POST `/images/{id}/unreject`), que la vuelve a `pending` y la reinyecta en la cola.

### 2.6 Analytics (`GET /projects/{id}/analytics`)

- **Que hace:** tablero de metricas del proyecto. Todos los servicios son seguros con 0 validadas
  (devuelven el estado vacio/neutro, no lanzan).
- **Secciones y su fuente:**
  - Concordancia con el modelo (US-19): `services.concordance`.
  - Progreso de curado (US-09): `services.progress`.
  - Total de imagenes y resumen (US-21): `services.progress` + texto en el template.
  - Tiempo ahorrado (US-20, ROI): `services.time_saved` (mock ~3s AL vs ~30s manual si no hay
    timestamps reales).
  - Distribucion de clases (US-22): `services.class_distribution`.
  - Ciclos de Active Learning + curva F1 (US-16): `services.list_cycles`; el sparkline SVG dibuja
    F1 por ciclo.
  - Salud del dataset (semaforo verde/amarillo/rojo): `services.dataset_health`.
  - Matriz de confusion (sugerido vs final): `services.confusion_matrix`.
  - Precision / recall por clase + accuracy: `services.quality_metrics`.
  - Comparativa A/B (manual vs PACUSAM-AL): `services.ab_summary`.
  - Conflictos (donde el curador corrigio al modelo): `services.conflicts`.
- **Acciones de la pagina:**
  - "Exportar CSV": enlace a `GET .../export.csv`.
  - "Re-entrenar (simulado)": POST `/projects/{id}/retrain` -> `services.simulate_retrain`,
    devuelve un toast ("confianza media de pendientes +X%"). Si ya esta calibrado, toast informativo.
- **Codigo:** `api.py:analytics_page`. Template: `templates/analytics.html`.

#### Export del dataset curado (US-23)

- **CSV:** `GET /projects/{id}/export.csv` -> descarga `pacusam-proyecto-{id}-dataset.csv` con
  columnas `filename, final_label, suggested_label, confidence, validated_at`. Codigo:
  `api.py:export_csv` -> `services.export_rows`.
- **JSON:** `GET /projects/{id}/export.json` -> `{rows, summary}`. Codigo: `api.py:export_json`
  -> `services.export_rows` + `services.export_summary`.
- Ambos exportan **solo imagenes validadas** (no rechazadas, no pendientes), ordenadas por
  `validated_at` para reproducibilidad.

### 2.7 Administracion (`GET /admin`) - solo rol admin

- **Que hace:** panel read-only con la lista de usuarios (email + rol) y el log de actividad de
  curado.
- **Como se usa:** filtros opcionales por id de usuario (`?user=`) y por accion (`?action=`,
  p. ej. `validate` / `reject` / `unreject`). Boton "Filtrar" + "Limpiar".
- **Autorizacion:** `api.py:require_admin` reusa `require_user`; sin sesion -> 303 a `/login`,
  curador -> 403, admin -> 200.
- **Log:** cada accion exitosa de curado se registra best-effort via `api.py:_log` ->
  `services.log_activity` (nunca tumba una accion ya exitosa).
- **Codigo:** `api.py:admin_page` -> `services.list_activity`. Template: `templates/admin.html`.

### 2.8 Salir / Sesion

- "Salir" en cualquier topbar hace POST `/logout` (`api.py:logout_action`), limpia la sesion y
  vuelve a `/login`. Sin sesion, cualquier ruta protegida redirige a `/login` (303) via
  `api.py:require_user` + el handler de `_RedirectException`.

---

## 3. Tabla feature -> user story -> archivo:funcion

Referencias reales del codigo (`archivo:funcion` relativo a `src/pacusam/`). Las templates van con
su ruta completa.

| Feature | User story | Donde vive (archivo:funcion / template) |
|---|---|---|
| Login | US-01 | `api.py:login_page` / `api.py:login_action`; `auth.py:authenticate`; `templates/login.html` |
| Registro de curador | US-02 | `api.py:register_page` / `api.py:register_action`; `auth.py:create_user`; `templates/register.html` |
| Logout / sesion / guard de auth | US-03 | `api.py:logout_action`; `api.py:require_user` (+ `_RedirectException`); `auth.py:get_user` |
| Hash de contrasena (PBKDF2, stdlib) | US-01/02 | `auth.py:hash_password` / `auth.py:verify_password` |
| Home: lista de proyectos | US-04 | `api.py:home`; `services.list_projects`; `templates/home.html`, `templates/partials/project_card.html` |
| Detalle de proyecto | US-05 | `api.py:project_detail`; `services.get_project`; `templates/project.html` |
| Crear proyecto | US-06 | `api.py:create_project_action`; `services.create_project`; `templates/home.html` |
| Autorizacion por dueño (anti-IDOR) | US-08 | `api.py:_owned_project` |
| Progreso de curado | US-09 | `services.progress`; macro `progress_bar` en `templates/partials/ui.html` |
| Validar / confirmar sugerencia (A) | US-10 | `api.py:validate`; `services.validate_image`; `templates/partials/image_card.html` |
| Corregir etiqueta (C) | US-11 | `api.py:validate` (con label distinta); `templates/partials/image_card.html` (chips `other_labels`) |
| Rechazar con motivo, reversible | US-12 | `api.py:reject` / `api.py:unreject`; `services.reject_image` / `services.unreject_image` |
| Cola por incertidumbre (uncertainty sampling) | US-14 | `services.queue_next` + `services._order_rows`; `api.py:_render_next_card` |
| Selector de estrategia de sampling | US-14 | `api.py:queue_fragment` + `api.py:_norm_strategy`; `services._order_rows`; `templates/curate.html` (topbar) |
| Filmstrip de miniaturas | US-14 | `services.queue_list`; `templates/partials/filmstrip.html` |
| Visor estilo OHIF (zoom/pan/invert/reset) | US-10 (UX) | `templates/partials/image_card.html` (Alpine `viewer()`, panel derecho) |
| Aprobar en lote >90% (bulk) | US-10 (bulk) | `api.py:bulk_validate_action`; `services.bulk_validate` |
| Historial de ciclos AL + curva F1/AUC | US-16 | `services.list_cycles` / `services.record_cycle`; `templates/analytics.html` (sparkline SVG) |
| Filtro por etiqueta | US-17 | `services.label_counts`; macro `filter_chips` en `templates/partials/ui.html`; `api.py:queue_fragment` (param `label`) |
| Concordancia curador-modelo | US-19 | `services.concordance` |
| Tiempo ahorrado (ROI) | US-20 | `services.time_saved` |
| Resumen ejecutivo | US-21 | `services.progress` + texto en `templates/analytics.html` |
| Distribucion de clases | US-22 | `services.class_distribution` |
| Matriz de confusion | US-22 (calidad) | `services.confusion_matrix` |
| Precision / recall por clase + accuracy | US-22 (calidad) | `services.quality_metrics` |
| Comparativa A/B (manual vs AL) | US-20 (calidad) | `services.ab_summary` |
| Salud del dataset (semaforo) | US-22 (calidad) | `services.dataset_health` |
| Conflictos (correcciones al modelo) | US-19 (calidad) | `services.conflicts` |
| Export CSV / JSON | US-23 | `api.py:export_csv` / `api.py:export_json`; `services.export_rows` / `services.export_summary` |
| Re-entrenamiento simulado (boton) | US-16 | `api.py:retrain`; `services.simulate_retrain` |
| Feedback loop automatico (umbral -> retrain) | US-16 | `services.validate_image` (publica `UmbralAlcanzado`); `api.py:create_app:_on_umbral` (suscriptor CEP); `services.threshold_status` |
| Roles curador/admin | US-26 | `auth.py:create_user` (param `role`); `db.py` (columna `role`) |
| Vista /admin (read-only) | US-27 | `api.py:admin_page` + `api.py:require_admin`; `templates/admin.html` |
| Log de actividad | US-28 | `services.log_activity` / `services.list_activity`; `api.py:_log` |
| Healthcheck | n/a (Fiabilidad) | `api.py:health` (`GET /health`) |

### Estilos arquitectonicos (white paper A.7) -> donde viven

| Estilo | Donde se materializa |
|---|---|
| Layered (api -> services -> db) | `api.py` (presentacion) -> `services.py` (dominio) -> `db.py` (datos); el dominio no conoce HTTP |
| Publish-Subscribe (bus in-process) | `events.py:EventBus` (`bus`); publishers en `services.py`; suscriptores en `api.py:create_app` |
| Eventos canonicos (4) | `events.py`: `ImagenesSubidas`, `ImagenValidada`, `UmbralAlcanzado`, `CicloFinalizo` |
| Event Processing SEP | `services.validate_image` publica `ImagenValidada` (uno-a-uno por accion) |
| Event Processing OEP | `services.queue_next` reordena la cola por incertidumbre al instante tras cada accion |
| Event Processing CEP | `UmbralAlcanzado` = derivado de N validadas -> dispara `simulate_retrain` (feedback loop) |
| Pipes & Filters (ingesta) | `pipeline.py:run_pipeline` con `INGESTA = [filtro_validar_formato, filtro_clasificar]`; usado por `services.seed_images` |
| Active Learning (stub honesto) | `classifier.py:suggest` (determinista por hash); uncertainty sampling REAL en `services._order_rows` |

---

## 4. Glosario

- **Uncertainty sampling:** estrategia de Active Learning que prioriza mostrar primero las
  imagenes donde el modelo esta **mas inseguro**, porque son las que mas le enseñan al etiquetarlas.
  En PACUSAM la incertidumbre es un proxy honesto: `1 - confianza`. La cola se ordena de mayor a
  menor incertidumbre en `services.queue_next` / `services._order_rows`. Es REAL aunque el modelo
  sea un stub.

- **Concordancia:** tasa de acuerdo entre el curador humano y el modelo. De las imagenes validadas,
  cuantas terminaron con `final_label == suggested_label`, dividido el total de validadas. Se
  calcula en `services.concordance`. En el demo sembrado ronda ~85.7% (se corrige ~1 de cada 7).

- **Umbral (de re-entrenamiento):** cantidad de imagenes validadas que dispara un ciclo de
  re-entrenamiento. Cada proyecto tiene `retrain_threshold` (demo = 20). Al cruzarlo exactamente,
  `services.validate_image` emite el evento `UmbralAlcanzado` (CEP), que el suscriptor de
  `create_app` usa para correr `simulate_retrain` solo (el feedback loop). Estado del contador en
  `services.threshold_status`.

- **F1 / AUC:** metricas de calidad de un clasificador. **F1** es la media armonica entre precision
  (cuantas de las predichas positivas eran correctas) y recall (cuantas de las reales positivas se
  detectaron). **AUC** (area bajo la curva ROC) mide la capacidad de separar clases a distintos
  umbrales. En el MVP son **mockeadas de forma honesta**: deterministas y crecientes por numero de
  ciclo (`services.simulate_retrain` calcula `f1`/`auc`; se guardan con `services.record_cycle` y
  se dibujan en el sparkline de analytics). El re-entrenamiento real (US-13/15) las reemplazaria
  sin tocar el resto del sistema.

---

## 5. Roadmap (fuera del MVP, justificado)

Decidido y documentado, no olvidado (ver `docs/trazabilidad.md` y `docs/arquitectura.md`):

- US-07: upload real de imagenes + soporte DICOM (la ingesta `pipeline.py` ya deja el gancho).
- US-18: busqueda en una galeria dedicada.
- US-24: filtros de export.
- US-25: reporte PDF del proyecto.
- Cambio de rol en vivo.

El motor de Active Learning real (US-13/15) esta mockeado a proposito para mitigar el riesgo R03
(motor demasiado complejo para el alcance de M2): `classifier.py` es un stub determinista, el
uncertainty sampling y las metricas son reales, y solo el entrenamiento esta simulado.
