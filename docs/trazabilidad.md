# Trazabilidad de decisiones del MVP

Documento de defensa. Mapea cada **decision de diseno del MVP (M2)** a su justificacion en el
white paper de estilos arquitectonicos, la **actividad del curso** que la motiva, el **riesgo**
del registro que mitiga, y su **estado real en el codigo**.

Convencion de actividades: A.4 (estimacion de esfuerzo / costo y equipo), A.7 (estilos
arquitectonicos), A.8 (vistas y modelo C4), A.9 (criterios de aceptacion / BDD), A.10 (walking
skeleton), A.11 (gestion de riesgos). Riesgos: R03 (motor de Active Learning demasiado complejo
para el alcance), R04 (almacenamiento / datos sensibles).

Estado: **hecho** = materializado y testeado en el MVP; **mock** = stub honesto (interfaz real,
implementacion simulada); **diferido** = decidido y documentado, llega en M3.

| Decision del MVP | Clausula del white paper | Actividad | Riesgo | Estado en el MVP |
|---|---|---|---|---|
| Monolito **Layered** (`api` -> `services` -> `db`), el dominio no conoce HTTP | Layered es uno de los estilos combinados (A.7); se baja a un solo deployable para el walking skeleton | A.7, A.10 | n/a | **hecho** (rebanada end-to-end US-10, dominio aislado de FastAPI) |
| **Active Learning mockeado** con uncertainty sampling **real** | "el MVP arranca sobre el dataset semilla mockeado"; el motor real (US-13/15) queda fuera | A.11 | R03 (excluir el motor real si resulta complejo) | **mock** honesto: `classifier.suggest` determinista, pero la cola se ordena por `1 - confianza` de verdad y la concordancia se calcula sobre la DB |
| **Pub-Sub** in-process (bus de eventos) | A.7 declara Pub-Sub para desacoplar el motor de AL; aca se materializa sin infraestructura | A.7 | n/a | **hecho**: `events.py` (bus sincrono en memoria) publica los 4 eventos canonicos del dominio |
| **Event Processing** (SEP / OEP / CEP) clasificado y materializado | A.7: procesamiento de eventos de dominio; el feedback loop nace de eventos | A.7 | R03 | **hecho**: SEP = `ImagenValidada` por cada accion; OEP = score + reordenamiento de cola al instante; CEP = `UmbralAlcanzado` (derivado de N validadas) dispara el re-entrenamiento |
| **Pipes & Filters** en la ingesta (filtros encadenados puros) | A.7: pasos independientes y reordenables sobre cada imagen | A.7 | n/a | **hecho** (parcial): `pipeline.py` con `[filtro_validar_formato, filtro_clasificar]`; los filtros de decode/anonimizar/almacenar llegan con la ingesta real (US-07/M3) sin reescribir el flujo |
| **SQLite + filesystem** (una conexion compartida, WAL) como almacenamiento | Presupuesto acotado y equipo de 2 part-time; almacenamiento local para el MVP | A.4, A.11 | R04 (almacenamiento / datos sensibles) | **hecho**: `db.py` con `journal_mode=WAL` + `busy_timeout=3000`; imagenes en `static/datasets/` versionadas (datasets publicos, sin PII) |
| **Jinja2 + HTMX** server-side (sin SPA, sin build/npm) | Costo y tamano de equipo; menos story points que un frontend separado | A.4, A.8 | n/a | **hecho**: `templating.py` + `templates/`; vendor (HTMX/Alpine/Tailwind/Lucide) servido local |
| **Roles + vista admin + log de actividad** | E9 (administracion y trazabilidad); deriva del esfuerzo estimado de auth | A.4 | R04 (auditabilidad / accesos) | **hecho**: roles curador/admin, `/admin` protegida por rol, `_log` best-effort de cada accion |
| **Validacion de password server-side** (pbkdf2 + minimo 6) | Atributo de Seguridad de ISO/IEC 25010; el `minlength` client-side no alcanza | A.7 | R04 | **hecho**: `auth.create_user` lanza `password_too_short`; `api.py` lo mapea a 422 |
| **`/health` + test de performance** | Atributos de Fiabilidad y Eficiencia de ISO/IEC 25010 | A.7 | n/a | **hecho**: `GET /health` publico devuelve `{status, version}`; `/login` responde holgadamente bajo 3s |
| **Criterios de aceptacion BDD ejecutables** (Gherkin en espanol) | A.9: los criterios de aceptacion guian la verificacion | A.9 | n/a | **hecho**: `tests/features/curado.feature` ejecutado por pytest-bdd (cola por incertidumbre, validar actualiza progreso, rechazar excluye) |
| **Export CSV / JSON** del dataset curado | Compatibilidad de ISO/IEC 25010 (interoperabilidad de datos) | A.7 | n/a | **hecho**: `export.csv` / `export.json` (US-23); la **importacion** real de imagenes (US-07) queda en roadmap |
| **Deploy en Render** (Blueprint) | Portabilidad de ISO/IEC 25010 | A.4 | n/a | **diferido** (config lista): `render.yaml` versionado; el deploy es un paso manual del dashboard, re-seed determinista al arrancar |

## Lectura de defensa

- Lo **materializado ahora** (Pub-Sub, Event Processing, Pipes & Filters, Layered) demuestra que
  los estilos del white paper no son solo diagramas: estan en `events.py`, `pipeline.py` y la
  separacion `api`/`services`/`db`, con tests que los ejercitan.
- Lo **mockeado** (motor de AL) es una mitigacion consciente de **R03**: la interfaz (`classifier`,
  ciclos de re-entrenamiento, metricas) es real y testeada; solo el entrenamiento esta simulado, de
  modo que US-13/15 lo reemplazan sin tocar `services`/`api`.
- Lo **diferido** (ingesta real US-07, deploy) esta acotado por alcance de M2 y documentado, no
  olvidado: el pipeline y la config ya dejan el "gancho" para ese trabajo.
