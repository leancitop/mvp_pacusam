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

## Atributos de calidad priorizados

Pendiente — derivar de ISO/IEC 25010 y del Plan de Gestión de Calidad ya entregado.

## Decisiones abiertas

- Stack tecnológico (lenguaje, framework API, almacenamiento, mensajería).
- Formato de imágenes soportado en el MVP (DICOM / PNG / NIfTI).
