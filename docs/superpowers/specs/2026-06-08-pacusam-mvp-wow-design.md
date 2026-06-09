# PACUSAM MVP "wow" — Design Spec

**Fecha:** 2026-06-08
**Autor:** Mateo Romano (con Claude Code)
**Materia:** Ingeniería de Software (LCD-UNSAM) — TPFI Grupo 9
**Branch:** `worktree-mvp-wow` (worktree aislado, desde `origin/main` de Leandro)
**Deadline:** 2 días — esto es un **MVP de cátedra**, no producción.

---

## 1. Objetivo y filosofía

PACUSAM es una plataforma web de **curado asistido de imágenes médicas con Active Learning** (cliente: CIMeT-UNSAM). El motor pre-clasifica imágenes con un score de confianza; el curador humano **valida, corrige o rechaza** cada sugerencia.

El objetivo de este MVP **no** es cubrir las 28 user stories ni ser production-grade. Es **maximizar "wow moments"** para deslumbrar al curso y al docente, manteniendo lo básico (auth, navegación) funcional, y **mockear sin culpa** todo lo que no aporte al wow. Lo que no se construye se documenta en un **roadmap** explícito (señal de visión de producto).

**Principio rector de diseño:** "Linear conoce a un cuaderno de residencia clínica" — minimalista, muy limpio, fácil de entender, con vibe académico pulido.

### Los 3 wow moments

1. **🩻 Pantalla de curado ("Tinder clínico").** Imagen médica real grande y centrada, etiqueta sugerida + barra de confianza, acciones por teclado (A/C/R) con auto-avance.
2. **🧠 Active Learning — uncertainty sampling.** La cola de curado **se reordena sola** poniendo arriba las imágenes de menor confianza. Mensaje: *"etiquetaste 8 de 200 — pero son las 8 que más le enseñan al modelo"*.
3. **📊 Analytics que parece producto real.** Tasa de concordancia modelo↔humano, gráfico de distribución de clases, progreso.

---

## 2. Alcance: matriz build / mock / roadmap

### ✅ BUILD real (funcional de verdad)
- **US-01/02/03 — Auth.** Registro (email + password con hash), login (sesión por cookie), logout. Guard de páginas internas.
- **US-04/05/06/08 — Home + proyectos.** Listar proyectos del usuario con barra de progreso; crear proyecto (nombre + descripción); abrir proyecto.
- **US-09 — Progreso.** Total / etiquetadas / pendientes / %.
- **US-10/11 — Curado + navegación.** Validar/corregir etiqueta sugerida; navegar siguiente/anterior entre pendientes.
- **US-12 — Rechazo + motivo.** Rechazar imagen eligiendo un motivo de una lista; excluida del dataset; reversible.

### 🎭 MOCK convincente (se ve real, sin motor real)
- **US-14 — Pre-clasificación.** Cada imagen sembrada trae `suggested_label` + `confidence` **pre-generados de forma realista** (algunas obvias ~0.95, otras ambiguas ~0.55).
- **"US-15" — Re-entrenar.** Botón que simula un ciclo: toast *"Ciclo completado — precisión +X%"* y reajuste de confianzas de pendientes. Puro teatro visual.
- **US-19/21/22 — Analytics.** Concordancia, resumen ejecutivo y distribución de clases **calculados de verdad sobre la DB**.

### 🗺️ ROADMAP (documentado, no construido)
US-07 (upload real + DICOM), US-13 (parámetros del clasificador), US-16 (historial de ciclos), US-17/18 (filtro/búsqueda — *stretch si sobra tiempo*), US-23/24/25 (export/PDF), US-26/27/28 (admin/roles/log de actividad).

Se documenta en `README.md` (sección Roadmap) y, opcionalmente, en la UI como features "próximamente" deshabilitadas.

### Stretch (cheap wins, solo si sobra tiempo)
- US-17 filtro por etiqueta (HTMX, barato).
- US-23 export CSV del dataset validado (download endpoint, barato).

---

## 3. Arquitectura

Se **extiende** el código de Leandro (no se reescribe). Se respeta la arquitectura en capas documentada en `docs/arquitectura.md`:

```
src/pacusam/
  api.py          # presentación: rutas FastAPI (HTML vía Jinja2 + JSON)
  services.py     # dominio: lógica de negocio, no conoce HTTP
  db.py           # datos: SQLite (esquema + conexión)
  classifier.py   # stub del motor de AL (confianzas mock)
  auth.py         # NUEVO: hashing de password, sesiones
  seed.py         # NUEVO: siembra determinista de proyectos + imágenes reales
  templates/      # NUEVO: plantillas Jinja2 (HTMX)
  static/
    css/          # Tailwind compilado (o CDN en dev)
    js/           # Alpine + helpers
    datasets/     # NUEVO: ~100 imágenes reales por proyecto, versionadas
```

**Stack de UI (sin build pesado):** FastAPI + **Jinja2** (render server-side) + **HTMX** (interacción sin recargar) + **Alpine.js** (estado cliente: zoom, panel, atajos) + **Tailwind** (CDN en dev; CLI standalone si hay tiempo para prod). Sin React, sin npm obligatorio.

**Iconos:** Lucide (SVG inline).

---

## 4. Modelo de datos (SQLite, a archivo)

Se arregla el bug de DB en memoria → **archivo** (`PACUSAM_DB`, default `pacusam.db`), con **re-seed determinista al arrancar si está vacía** (funciona local y en Render aunque resetee disco).

```sql
users (
  id INTEGER PK,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
)

projects (
  id INTEGER PK,
  name TEXT NOT NULL,
  description TEXT,
  owner_id INTEGER NOT NULL REFERENCES users(id),
  domain TEXT,          -- 'chest_xray' | 'blood_cells'
  labels TEXT NOT NULL, -- JSON: etiquetas válidas del proyecto (fuente única de verdad)
  created_at TEXT NOT NULL
)

images (
  id INTEGER PK,
  project_id INTEGER NOT NULL REFERENCES projects(id),
  filename TEXT NOT NULL,
  path TEXT NOT NULL,           -- ruta servible a la imagen real en static/datasets/
  suggested_label TEXT,
  confidence REAL,              -- 0.50–0.99, pre-generada realista
  status TEXT DEFAULT 'pending',-- 'pending' | 'validated' | 'rejected'
  final_label TEXT,
  reject_reason TEXT,
  shown_at TEXT,                -- para medir tiempo de validación
  validated_at TEXT
)
```

Las etiquetas válidas viven en `projects.labels` (JSON) → **se elimina la duplicación hardcodeada** en 3 lugares. `validate` valida el `final_label` contra ese set.

---

## 5. Endpoints (API)

**Páginas (HTML, Jinja2 + HTMX):**
- `GET /login`, `GET /register` — formularios
- `GET /` — home (grid de proyectos del usuario logueado)
- `GET /projects/{id}` — vista del proyecto (resumen + analytics + "Empezar a curar")
- `GET /projects/{id}/curate` — ⭐ pantalla de curado
- `GET /projects/{id}/analytics` — analytics

**Acciones (form posts / HTMX, devuelven fragmentos o redirects):**
- `POST /register`, `POST /login`, `POST /logout`
- `POST /projects` — crear proyecto
- `GET /projects/{id}/queue` — siguiente imagen a curar **ordenada por incertidumbre** (`1 − confidence`)
- `POST /images/{id}/validate` — `{label}` confirma/corrige (valida contra labels del proyecto)
- `POST /images/{id}/reject` — `{reason}` rechaza con motivo
- `POST /images/{id}/unreject` — revierte rechazo (US-12 reversible)
- `POST /projects/{id}/retrain` — simula ciclo AL (reajusta confianzas + devuelve "mejora")
- `GET /progress?project_id=` — progreso
- (stretch) `GET /projects/{id}/export.csv` — export dataset validado

Todas las páginas internas y acciones requieren sesión activa (middleware/dependency de auth). Errores de dominio mapeados a HTTP, **con manejo de error visible en el front** (no como hoy).

---

## 6. Motor de Active Learning (mock convincente)

- **Confianzas pre-generadas:** al sembrar, cada imagen recibe una confianza realista. Distribución diseñada para que haya un mix claro de "obvias" y "dudosas" → el reordenamiento tiene de qué agarrarse.
- **Uncertainty sampling (real, ~5 líneas):** `GET /queue` ordena las pendientes por `1 − confidence` desc (least-confidence). La UI lo muestra como "ordenado por incertidumbre".
- **Concordancia (real):** `% de validadas donde final_label == suggested_label`.
- **Re-entrenar (simulado):** `POST /retrain` mueve las confianzas de las pendientes hacia arriba (simula que el modelo "aprendió") y reporta una mejora de precisión calculada de forma plausible. No hay ML real.

> El white paper marca el AL como "riesgo crítico R03": debe degradar elegante a curado manual. Este mock cumple: si se quita el AL, el curado manual sigue funcionando.

---

## 7. Datos reales (imágenes)

- **2 proyectos pre-sembrados:**
  1. *"Radiografías de tórax"* — dataset Chest X-ray Pneumonia (Kermany, CC BY 4.0), 2 clases: `NORMAL` / `PNEUMONIA`. ~100 imágenes.
  2. *"Células sanguíneas"* — dataset BCCD / Blood Cells (MIT), multiclase. ~100 imágenes.
- Las imágenes (~15-20 MB total) se versionan en `static/datasets/<proyecto>/` → demo reproducible y self-contained.
- Un script de descarga (`scripts/fetch_datasets.py` o similar) documenta de dónde salieron, pero las imágenes quedan commiteadas para que el demo no dependa de la red.

---

## 8. UI / Design system

**Paleta:**
- Fondo papel `#FCFBF9` · superficie `#FFFFFF` · superficie2 `#F4F2EE` · borde `#E7E4DE`
- Texto `#1A1A18` / `#6B6B66` / `#9C9A94`
- Acento `#2563EB` (hover `#1D4ED8`, tint `#EFF4FF`)
- Estados: aprobado `#16A34A`/`#ECFDF3` · rechazado `#DC2626`/`#FEF2F2` · flag `#D97706`/`#FFFBEB`

**Tipografía:** Inter (UI) + Lora (títulos de auth/proyecto) + JetBrains Mono (datos/IDs). Google Fonts.

**Pantallas clave:**
- **Auth:** card centrada ~400px sobre fondo papel, H1 en Lora, inputs grandes (44-48px), botón azul full-width.
- **Home:** sidebar (~240px) + topbar + grid de cards de proyecto (cover mosaico, nombre, descripción, barra de progreso "47/100 curadas").
- **⭐ Curado:** imagen grande centrada (fondo oscuro opcional), filmstrip lateral con estados por color, barra de confianza, action bar inferior con 3 botones grandes + hotkeys visibles (A/C/R), auto-avance con micro-animación, panel derecho colapsable (metadata + motivo de rechazo), overlay de atajos (`?`).
- **Analytics:** concordancia (%), distribución de clases (gráfico de barras), progreso.

**Motion:** 120-160ms ease-out, todo sutil. Sin gradientes chillones ni glassmorphism.

---

## 9. Testing

Materia de Ing. de Software → **mantener BDD en español** (pytest-bdd, es el formato de los criterios de aceptación). Agregar escenarios para los flujos nuevos y **caminos de error** (hoy inexistentes):
- Auth: registro OK, email duplicado, login inválido, guard sin sesión.
- Curado: validar confirma, corregir cambia label, label inválida rechazada.
- Rechazo: rechazar con motivo, excluir de dataset, revertir.
- AL: la cola sale ordenada por incertidumbre.
- Analytics: concordancia calculada correctamente.
- Caminos de error de la API existente (404 image_not_found, 422 label_required, 404 no_pending).

Objetivo: suite verde + cobertura razonable de happy path **y** error paths.

---

## 10. Persistencia y deploy

- **SQLite a archivo** + re-seed determinista al arrancar si vacía.
- **Local** = demo principal (cero cold start). Comando documentado en README.
- **Render** = URL pública de bonus. `render.yaml` ajustado (`PACUSAM_DB` a archivo). Mitigación de cold start documentada (warm-up antes de presentar).
- Arreglar README (rutas Windows → multiplataforma; quitar referencia rota).

---

## 11. Bugs de la base que se arreglan de paso

- DB en memoria → archivo (persistencia real).
- `/seed` idempotente (UNIQUE / dedupe).
- XSS por `innerHTML` → escaping (Jinja2 autoescapa).
- Manejo de errores en el front (hoy cero).
- Etiquetas hardcodeadas en 3 lugares → fuente única (`projects.labels`).
- `validate` valida contra el set de labels del proyecto.

---

## 12. Cómo trabajamos

- Worktree aislado `mvp-wow`, branch `worktree-mvp-wow` desde `origin/main`. **No se toca la main de Leandro.**
- Implementación con `/subagent-driven-development` + workflows en paralelo (tracks: datos+modelo, auth, home/proyectos, curado, AL, analytics, UI/design-system).
- Verificación propia: suite de tests verde + levantar la app y comprobar el flujo end-to-end antes de reportar.

---

## 13. Definición de "listo" (Definition of Done)

1. Auth real funcionando (registro/login/logout + guard).
2. Home con 2 proyectos sembrados + crear proyecto.
3. Pantalla de curado con imágenes reales + acciones por teclado + auto-avance.
4. Rechazo con motivo (reversible).
5. Cola ordenada por incertidumbre (uncertainty sampling visible).
6. Analytics: concordancia + distribución de clases + progreso.
7. Botón "re-entrenar" que simula un ciclo.
8. UI con el design system aplicado (paleta, fuentes, layouts).
9. Suite de tests verde (happy + error paths).
10. App levanta local con un comando documentado; README actualizado con paso a paso y roadmap.
