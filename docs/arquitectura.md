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

- **Pipes & Filters:** todavía no materializado; el flujo seed→sugerencia→validación es directo. Se materializa con la ingesta real (US-07).
- **Pub-Sub:** **diferido**. El progreso se recalcula on-demand en `services.progress`, no por eventos. El bus cobra sentido recién en M3. Deuda técnica planificada.
- **active_learning:** stub determinista (`classifier.py`). US-15 lo reemplaza sin tocar `services`/`api`.
- **Aún no implementado:** auth (US-01/02/03), proyectos (US-04/06/08), rechazo (US-12). Próximas iteraciones.

## Atributos de calidad priorizados

Pendiente — derivar de ISO/IEC 25010 y del Plan de Gestión de Calidad ya entregado.

## Decisiones (cerradas en iteración 1)

- **Stack:** Python 3.10+ / FastAPI / SQLite (stdlib) / pytest-bdd. Justificación: cero infra, dominio Python natural para Ciencia de Datos, Gherkin engancha con los criterios de aceptación ya escritos.
- **Formato de imágenes en el MVP:** irrelevante en esta iteración (no hay decode real; los nombres de archivo son mocks). La validación de formato JPG/PNG/DICOM entra con US-07 (ingesta real).
