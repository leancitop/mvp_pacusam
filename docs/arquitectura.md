# Arquitectura objetivo — PACUSAM

Documento vivo. Describe la arquitectura **objetivo** del sistema completo, no la estructura actual del repo. Refleja las decisiones del grupo (entregable de estilos arquitectónicos v3 en la wiki). PACUSAM es la plataforma; CIMeT es el sponsor/cliente.

> El MVP (M2) es un *walking skeleton* sobre datos mockeados. La estructura de carpetas/módulos **no está pre-armada**: emerge a medida que se implementa el código. Lo de acá es el norte, no el estado actual.

## Estilos combinados

| Estilo | Dónde aplica | Por qué |
|---|---|---|
| Pipes & Filters | pipeline de ingesta | Pasos independientes y reordenables sobre cada imagen (decode → normalizar → validar → almacenar). |
| Layered | sistema completo | Separa presentación, dominio y datos. Aísla cambios. |
| Pub-Sub | comunicación entre componentes | Desacopla el motor de Active Learning: publica "imagen nueva" / "lote etiquetado", los consumidores reaccionan sin acoplarse. |

## Componentes objetivo

Conceptuales, no carpetas existentes:

- **ingesta** — recibe imágenes, las preprocesa por etapas (filtros encadenados).
- **curado** — ciclo de etiquetado/validación con humano en el loop.
- **active_learning** — selecciona qué imágenes mandar a validar (mayor incertidumbre). Riesgo crítico R03 del registro de riesgos. Llega en M3, no en el MVP.
- **eventos** — bus de mensajes entre componentes.
- **api** — punto de entrada (servicio / UI), capa de presentación.

## Alcance del MVP (M2)

Solo el camino de **US-10** (validar/corregir imágenes pre-clasificadas) sobre **dataset semilla + stub de sugerencias**. Ingesta real (US-07) y pre-clasificador real (US-15) quedan fuera del MVP. Ver decisiones del grupo en la wiki.

## Estado actual del MVP (iteración 1)

Una sola rebanada end-to-end: **US-10** (validar imágenes pre-clasificadas) + US-09 (progreso). Implementado como **Layered**: `api` (FastAPI) → `services` (dominio) → `db` (SQLite, tabla `images`). El dominio no conoce HTTP.

- **Pipes & Filters:** **materializado** en `pipeline.py`: la ingesta corre filtros encadenados puros `[filtro_validar_formato, filtro_clasificar]` sobre cada imagen. Los filtros de decode/anonimizar/almacenar se agregan con la ingesta real (US-07) sin reescribir el flujo.
- **Pub-Sub:** **materializado** en `events.py`: bus sincrono en memoria. `services` publica los 4 eventos canónicos (`ImagenesSubidas`, `ImagenValidada`, `UmbralAlcanzado`, `CicloFinalizo`); los suscriptores (feedback loop de re-entrenamiento) se registran solo en `create_app`. Event Processing clasificado como SEP (acción uno-a-uno), OEP (score + reordenamiento al instante) y CEP (`UmbralAlcanzado` derivado de N validadas dispara el ciclo).
- **active_learning:** stub determinista (`classifier.py`). US-15 lo reemplaza sin tocar `services`/`api`.
- **Auth, proyectos, rechazo, roles/admin/log:** implementados (US-01/02/03, US-04/06/08, US-12, US-26/27/28).

## Atributos de calidad priorizados

Derivados de ISO/IEC 25010 y del Plan de Gestión de Calidad. La columna **Estado** distingue lo
que ya está verificado en el código de lo que se defiende por alcance (M2 / R03).

| Característica (ISO/IEC 25010) | Criterio en el MVP | Evidencia | Estado |
|---|---|---|---|
| **Funcionalidad** (adecuación funcional) | El camino US-10 y las funciones de defensa funcionan según los criterios de aceptación | 252 tests verdes (unitarios de dominio/auth + endpoints + integración + BDD en Gherkin) | **real** |
| **Fiabilidad** | La app no corrompe datos bajo concurrencia y expone su salud | `journal_mode=WAL` + `busy_timeout=3000` en `db.py`; endpoint `GET /health` que devuelve `{status, version}` | **real** |
| **Usabilidad** | El curador opera por teclado con feedback inmediato | 3 wow-moments (curado tipo "Tinder clínico", uncertainty sampling visible, analytics); se prueba en vivo en la defensa | **real** + prueba manual en defensa |
| **Eficiencia** (desempeño) | Las páginas responden holgadamente | Test de performance: `/login` y `/health` responden bajo 3s | **real** |
| **Seguridad** | Credenciales protegidas, sesiones firmadas, sin acceso a recursos ajenos, sin PII | Hash `pbkdf2_sha256` (stdlib); cookies de sesión firmadas (`https_only` configurable); `_owned_project` evita IDOR (404 a recurso ajeno); password server-side (mínimo 6); datasets públicos sin PII (mitiga **R04**) | **real** |
| **Compatibilidad** (interoperabilidad) | Los datos curados se exportan a formatos estándar | `export.csv` / `export.json` (US-23); la importación real de imágenes JPG/PNG/DICOM (US-07) queda en roadmap | **real** (export) / **roadmap** (import) |
| **Mantenibilidad** | El código está documentado y los estilos están aislados | Cobertura de docstrings >= 80% verificada por test; capas `api`/`services`/`db` separadas; estilos en `events.py` y `pipeline.py` | **real** |
| **Portabilidad** | Despliegue reproducible sin tocar el código | `render.yaml` (Blueprint) versionado + re-seed determinista al arrancar | **config lista** / deploy manual del dashboard |

Lo que se **defiende por alcance** y no por implementación: el motor de Active Learning real
(US-13/15) está mockeado de forma honesta para mitigar **R03** (uncertainty sampling y métricas
son reales; el entrenamiento es simulado), y la ingesta real (US-07) está fuera de M2. Ver
`docs/trazabilidad.md` para el mapeo completo decisión -> white paper / actividad / riesgo.

## Decisiones (cerradas en iteración 1)

- **Stack:** Python 3.10+ / FastAPI / SQLite (stdlib) / pytest-bdd. Justificación: cero infra, dominio Python natural para Ciencia de Datos, Gherkin engancha con los criterios de aceptación ya escritos.
- **Formato de imágenes en el MVP:** irrelevante en esta iteración (no hay decode real; los nombres de archivo son mocks). La validación de formato JPG/PNG/DICOM entra con US-07 (ingesta real).
