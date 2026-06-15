# PACUSAM

## Plataforma de Curado Asistido de Imagenes Medicas con Active Learning

**Informe del Trabajo Practico Final Integrador (TPFI)**

| | |
|---|---|
| **Proyecto** | PACUSAM - MVP academico de curado de imagenes medicas con Active Learning |
| **Grupo** | Grupo 9 |
| **Integrantes** | Mateo Romano, Leandro Escudero |
| **Materia** | Ingenieria de Software |
| **Carrera** | Licenciatura en Ciencia de Datos (LCD) |
| **Institucion** | Universidad Nacional de San Martin (UNSAM) |
| **Cliente / Sponsor** | CIMeT - UNSAM (Centro de Investigacion en Metodos Computacionales y de Translacion) |
| **Periodo** | 1er Cuatrimestre 2026 |
| **Version del MVP** | 0.1.0 (Milestone M2 - walking skeleton) |

---

## Indice

1. Resumen ejecutivo
2. Contexto
3. Propuesta de solucion
4. Impacto y beneficios
5. Arquitectura
6. Estado del MVP y cobertura de User Stories
7. Conclusiones y proximos pasos
8. Anexos

---

## 1. Resumen ejecutivo

### Problema

El curado y etiquetado de imagenes medicas es un cuello de botella para los grupos de
investigacion. Los expertos clinicos dedican una porcion enorme de su tiempo a una tarea
repetitiva (revisar imagen por imagen, asignar o confirmar una etiqueta) en lugar de invertirlo
en el analisis cientifico. El proceso manual es lento, dificil de auditar y no prioriza las
imagenes mas informativas: se etiqueta todo por igual, gastando esfuerzo experto en casos que
el modelo ya resuelve con alta confianza.

### Solucion

**PACUSAM** es una plataforma web de **curado asistido** que pone al experto en el centro del
ciclo (human-in-the-loop) y usa **Active Learning** para ordenar el trabajo: primero se le
muestran al curador las imagenes donde el modelo esta mas inseguro (uncertainty sampling), que
son las que mas aportan al aprendizaje. El curador valida, corrige o rechaza con el teclado
(flujo tipo "Tinder clinico": A = aprobar, C = corregir, R = rechazar) y avanza automaticamente.
Cuando se acumulan suficientes validaciones, un evento dispara el re-entrenamiento del modelo,
cerrando el ciclo de feedback.

### Beneficios

| Beneficio | Como lo logra PACUSAM |
|---|---|
| Menos tiempo experto por imagen | Curado por teclado con auto-avance y visor estilo OHIF (zoom, pan, invertir) |
| Esfuerzo dirigido a lo que importa | Cola ordenada por incertidumbre (uncertainty sampling real) |
| Mejora continua del modelo | Feedback loop: al cruzar el umbral, se dispara el re-entrenamiento |
| Trazabilidad y auditoria | Roles curador/admin, log de actividad, motivo de rechazo reversible |
| Visibilidad del valor generado | Analytics: concordancia, tiempo ahorrado, F1/AUC, comparativa A/B vs manual |

El MVP entregado es un **walking skeleton** (Milestone M2): cubre la rebanada punta a punta de
curado manual asistido sobre un dataset semilla, con el motor de Active Learning **mockeado de
forma honesta** (la interfaz y el uncertainty sampling son reales; el entrenamiento es simulado).
Esta decision esta documentada y justificada por el riesgo R03 del registro (ver seccion 5 y
Anexos).

---

## 2. Contexto

El **CIMeT (UNSAM)** investiga con grandes volumenes de imagenes medicas (radiografias, frotis de
sangre, etc.). Para entrenar y validar modelos de clasificacion necesita datasets curados: cada
imagen debe tener una etiqueta confiable, revisada por un experto.

El problema central que motiva el proyecto: **alrededor del 80% del tiempo del proceso es trabajo
manual** de revision y etiquetado imagen por imagen. Ese tiempo lo aporta personal experto y
escaso. Ademas, el flujo manual:

- No prioriza: se revisa todo en el mismo orden, sin distinguir lo facil de lo dificil.
- Es opaco: cuesta auditar quien valido que, cuando y por que se rechazo una imagen.
- No realimenta al modelo de forma sistematica.

PACUSAM ataca ese 80% convirtiendo el curado en un flujo asistido, priorizado por incertidumbre y
auditable, sin sacar al experto del lazo de decision.

> Restricciones del contexto academico (Milestone M2): equipo de 2 personas part-time, presupuesto
> acotado y un cuatrimestre de calendario. Esto condiciona el alcance del MVP (ver seccion 6) y
> motiva las decisiones de simplificacion documentadas en `docs/trazabilidad.md`.

---

## 3. Propuesta de solucion

La solucion se organiza en **9 epicas**. La tabla resume cada epica y su **estado real en el MVP**
(hecho = materializado y testeado; mock = stub honesto con interfaz real; roadmap = decidido y
documentado, fuera de M2).

| # | Epica | Que cubre | Estado real en el MVP |
|---|---|---|---|
| E1 | Autenticacion y sesion | Registro, login, logout (US-01/02/03) | **Hecho**: pbkdf2 (stdlib), cookies de sesion firmadas, password server-side (minimo 6) |
| E2 | Proyectos | Home, listado, creacion de proyecto con labels y dominio (US-04/05/06/08) | **Hecho**: 2 proyectos sembrados, creacion con etiquetas y umbral |
| E3 | Curado human-in-the-loop | Validar / corregir / rechazar por teclado, auto-avance (US-10/11/12) | **Hecho**: A=aprobar, C=corregir, R=rechazar; rechazo con motivo **reversible** |
| E4 | Visor de imagenes | Visor estilo OHIF: zoom, pan, invertir, reset (US-14) | **Hecho**: teclas `=`, `-`, `0`, `i` |
| E5 | Active Learning | Estrategia de muestreo, cola por incertidumbre, filmstrip (US-09/13/15) | **Hecho** el uncertainty sampling (cola por `1 - confianza`) y el selector de estrategia (uncertainty/random/sequential); **mock** el pre-clasificador y el re-entrenamiento (R03) |
| E6 | Feedback loop | Contador hacia el umbral, disparo de re-entrenamiento | **Hecho** el lazo de eventos (umbral -> evento -> ciclo); **mock** el entrenamiento real (simulado, determinista) |
| E7 | Analytics y metricas | Concordancia, tiempo ahorrado, distribucion, matriz de confusion, A/B, F1/AUC (US-16/19/20/21/22) | **Hecho**: calculadas sobre la DB real (concordancia, distribucion, conflictos) o por formula determinista (F1/AUC de los ciclos) |
| E8 | Export e interoperabilidad | Export del dataset curado (US-17/23) | **Hecho** export CSV/JSON y filtro por etiqueta; **roadmap** import real e ingesta (US-07) |
| E9 | Administracion y trazabilidad | Roles curador/admin, vista /admin, log de actividad, /health (US-26/27/28) | **Hecho**: `/admin` protegida por rol, log best-effort de cada accion, `/health` publico |

Funcionalidad transversal materializada: **aprobar en lote** las imagenes con confianza > 90% y
**filtro por etiqueta** en la cola de curado.

---

## 4. Impacto y beneficios

Las metricas se calculan sobre la base de datos real del MVP (datos sembrados de forma
determinista) o, en el caso de las metricas de modelo, mediante formulas deterministas crecientes
(mock honesto). Los valores que siguen corresponden al demo sembrado.

### 4.1 Datos del demo

| Dato | Valor |
|---|---|
| Proyectos | 2 ("Radiografias de torax", "Celulas sanguineas") |
| Imagenes reales por proyecto | ~40 |
| Validadas | ~14 por proyecto |
| Rechazadas | ~3 por proyecto |
| Pendientes | ~23 por proyecto |
| Concordancia curador vs modelo | ~85.7% |
| Ciclos de Active Learning registrados | 2 (F1/AUC creciente) |

### 4.2 Concordancia y calidad del modelo (US-16/19)

La **concordancia** es la tasa de acuerdo entre la etiqueta sugerida por el modelo y la etiqueta
final del curador, calculada sobre las imagenes validadas. En el demo es **~85.7%**, lo que indica
que el pre-clasificador ya acierta la mayoria de las veces y el experto corrige el resto.

Historial de **2 ciclos de AL** con metricas crecientes (mock honesto, formula determinista):

| Ciclo | Precision (antes) | Precision (despues) | F1 | AUC |
|---|---|---|---|---|
| 1 | 0.72 | 0.78 | 0.86 | 0.88 |
| 2 | 0.78 | 0.84 | 0.90 | 0.92 |

### 4.3 Tiempo ahorrado y comparativa A/B (US-20)

El modelo de costos compara curado asistido (PACUSAM-AL) contra etiquetado manual sin asistencia:

| Metrica | Manual | PACUSAM (AL) |
|---|---|---|
| Tiempo por imagen | 30 s | 3 s |
| Throughput | 120 img/hora | 1200 img/hora |
| Tiempo ahorrado | - | **~90%** |

Para las imagenes que tienen marcas de tiempo reales (`shown_at` / `validated_at`), el calculo usa
el tiempo medido; en su defecto cae al modelo de ~3 s (AL) vs ~30 s (manual). El ahorro estimado es
del orden del **90%** del tiempo experto por imagen.

### 4.4 Distribucion de clases y salud del dataset (US-22)

PACUSAM expone la **distribucion de clases** sobre las imagenes validadas y un indicador de
**salud del dataset** con umbral relativo al numero de clases (ideal = 100 / n_clases): verde si la
clase minoritaria supera el 80% del ideal, amarillo si supera el 50%, rojo si es menor. Esto alerta
sobre desbalance antes de entrenar.

---

## 5. Arquitectura

### 5.1 Arquitectura objetivo (5 capas / componentes)

La arquitectura objetivo del sistema completo (documento de estilos arquitectonicos del grupo)
combina tres estilos y define cinco componentes conceptuales:

| Componente objetivo | Rol |
|---|---|
| ingesta | Recibe imagenes y las preprocesa por etapas (filtros encadenados) |
| curado | Ciclo de etiquetado / validacion con humano en el loop |
| active_learning | Selecciona que imagenes mandar a validar (mayor incertidumbre); llega en M3 |
| eventos | Bus de mensajes entre componentes |
| api | Punto de entrada (servicio / UI), capa de presentacion |

### 5.2 Estilos materializados en el MVP

Los estilos del white paper (clausula A.7) no son solo diagramas: estan implementados y testeados
en el codigo del MVP.

| Estilo | Donde vive en el codigo | Que hace en el MVP |
|---|---|---|
| **Layered** | separacion `api` -> `services` -> `db` | Monolito en capas; el dominio (`services.py`) no conoce HTTP; un solo deployable para el walking skeleton |
| **Publish-Subscribe** | `src/pacusam/events.py` | Bus sincrono en memoria, sin infraestructura. Publica los 4 eventos canonicos del dominio; los suscriptores se registran solo en `create_app` |
| **Event Processing** | `events.py` + `services.py` | SEP, OEP y CEP clasificados y materializados (ver abajo) |
| **Pipes & Filters** | `src/pacusam/pipeline.py` | Ingesta como filtros puros encadenados `[validar_formato, clasificar]`; reordenables y extensibles sin reescribir el flujo |

**Los 4 eventos canonicos del dominio**: `ImagenesSubidas`, `ImagenValidada`, `UmbralAlcanzado`,
`CicloFinalizo`.

**Clasificacion de Event Processing**:

| Tipo | Que es en PACUSAM |
|---|---|
| SEP (Single Event Processing) | Cada accion de curado emite un evento uno-a-uno: `ImagenValidada` por cada validacion o rechazo |
| OEP (Online Event Processing) | El score de confianza se actualiza al instante y la cola se reordena por incertidumbre tras cada accion (`queue_next`) |
| CEP (Complex Event Processing) | `UmbralAlcanzado` es un evento **derivado** de N validaciones acumuladas; al cruzar el umbral dispara el re-entrenamiento |

**El feedback loop cierra el ciclo**: el CEP (`UmbralAlcanzado`) realimenta a Pipes & Filters
disparando un nuevo ciclo de procesamiento. Es el punto donde los cuatro estilos se conectan.

### 5.3 Atributos de calidad (ISO/IEC 25010): estado vs criterio

La columna **Estado** distingue lo verificado en el codigo de lo que se defiende por alcance (M2 /
R03).

| Caracteristica ISO/IEC 25010 | Criterio en el MVP | Evidencia | Estado |
|---|---|---|---|
| **Funcionalidad** (adecuacion funcional) | El camino US-10 y las funciones de defensa cumplen los criterios de aceptacion | 248 tests verdes (dominio/auth + endpoints + integracion + BDD Gherkin) | **Real** |
| **Fiabilidad** | No corrompe datos bajo concurrencia y expone su salud | `journal_mode=WAL` + `busy_timeout=3000` en `db.py`; `GET /health` devuelve `{status, version}` | **Real** |
| **Usabilidad** | El curador opera por teclado con feedback inmediato | Curado tipo "Tinder clinico", uncertainty sampling visible, analytics; prueba en vivo en la defensa | **Real** + prueba manual |
| **Eficiencia** (desempeno) | Las paginas responden holgadamente | Test de performance: `/login` y `/health` bajo 3s | **Real** |
| **Seguridad** | Credenciales protegidas, sesiones firmadas, sin acceso a recursos ajenos, sin PII | Hash `pbkdf2_sha256` (stdlib); cookies firmadas; `_owned_project` evita IDOR (404 a recurso ajeno); password server-side; datasets publicos sin PII (mitiga R04) | **Real** |
| **Compatibilidad** (interoperabilidad) | Los datos curados se exportan a formatos estandar | `export.csv` / `export.json` (US-23) | **Real** (export) / **Roadmap** (import US-07) |
| **Mantenibilidad** | Codigo documentado y estilos aislados | Cobertura de docstrings >= 80% verificada por test; capas separadas; estilos en `events.py` y `pipeline.py` | **Real** |
| **Portabilidad** | Despliegue reproducible sin tocar el codigo | `render.yaml` (Blueprint) versionado + re-seed determinista al arrancar | **Config lista** / deploy manual |

---

## 6. Estado del MVP y cobertura de User Stories

Estado honesto, rebanada por rebanada. **Hecho** = materializado y testeado. **Mock** = interfaz
real, implementacion simulada (mitigacion documentada de R03). **Roadmap** = decidido y
documentado, fuera de M2.

| US | Descripcion | Estado |
|---|---|---|
| US-01 | Registro de usuario | Hecho |
| US-02 | Login | Hecho |
| US-03 | Logout / sesion | Hecho |
| US-04 | Home | Hecho |
| US-05 | Listado de proyectos | Hecho |
| US-06 | Detalle de proyecto | Hecho |
| US-07 | Upload real de imagenes + DICOM | Roadmap |
| US-08 | Crear proyecto | Hecho |
| US-09 | Progreso / contador | Hecho |
| US-10 | Validar / corregir imagenes pre-clasificadas | Hecho |
| US-11 | Curado por teclado + auto-avance | Hecho |
| US-12 | Rechazo con motivo reversible | Hecho |
| US-13 | Motor de AL (seleccion) | Mock (uncertainty sampling real, entrenamiento simulado) |
| US-14 | Visor estilo OHIF (zoom/pan/invertir/reset) | Hecho |
| US-15 | Pre-clasificador real | Mock (stub determinista por hash) |
| US-16 | Historial de ciclos + curva F1/AUC | Hecho (F1/AUC por formula determinista) |
| US-17 | Filtro por etiqueta en la cola | Hecho |
| US-18 | Busqueda en galeria dedicada | Roadmap |
| US-19 | Analytics: concordancia | Hecho |
| US-20 | Analytics: tiempo ahorrado | Hecho |
| US-21 | Analytics: resumen del proyecto | Hecho |
| US-22 | Analytics: distribucion de clases | Hecho |
| US-23 | Export CSV / JSON | Hecho |
| US-24 | Filtros de export | Roadmap |
| US-25 | Reporte PDF del proyecto | Roadmap |
| US-26 | Roles curador / admin | Hecho |
| US-27 | Vista /admin | Hecho |
| US-28 | Log de actividad | Hecho |

Funciones adicionales materializadas no mapeadas a una unica US: aprobar en lote (confianza > 90%),
selector de estrategia (uncertainty / random / sequential), filmstrip ordenado por incertidumbre,
matriz de confusion, precision/recall por clase, comparativa A/B, salud del dataset.

**Resumen de cobertura**:

| Estado | US |
|---|---|
| Hecho | US-01/02/03, US-04/05/06/08, US-09/10/11/12/14, US-16/17/19/20/21/22/23, US-26/27/28 |
| Mock (honesto, R03) | US-13, US-15 (componente Active Learning: el uncertainty sampling y las metricas sobre la DB son reales; el pre-clasificador y el re-entrenamiento son simulados) |
| Roadmap (M3, justificado) | US-07 (upload real + DICOM), US-18 (galeria), US-24 (filtros de export), US-25 (reporte PDF), cambio de rol en vivo |

### 6.1 Justificacion del mock (R03) y de las decisiones de alcance

- El **Active Learning mockeado** es una mitigacion consciente del riesgo **R03** (motor real
  demasiado complejo para el alcance de M2): la interfaz (`classifier`, ciclos, metricas) es real y
  testeada, el uncertainty sampling ordena la cola por `1 - confianza` de verdad, y la concordancia
  se calcula sobre la base de datos. Solo el entrenamiento esta simulado, de modo que US-13/15 lo
  reemplazan sin tocar `services` ni `api`.
- El **almacenamiento en SQLite a archivo** (con WAL) + filesystem materializa el almacenamiento
  local para datos del MVP y mitiga **R04** (datos sensibles): los datasets sembrados son publicos y
  sin PII.
- El MVP (Milestone M2) es deliberadamente un **walking skeleton**: una rebanada de ingesta y curado
  manual punta a punta, condicionada por presupuesto y un equipo de 2 part-time.

Estas decisiones estan ancladas a las actividades del curso (A.4 Backlog, A.7 Estilos, A.8
Estimacion, A.9 Plan de Calidad, A.10 WBS, A.11 Riesgos) y mapeadas decision por decision en
`docs/trazabilidad.md`.

---

## 7. Conclusiones y proximos pasos

### Conclusiones

- PACUSAM entrega un **walking skeleton funcional** de curado asistido con humano en el loop, con
  248 tests verdes y una rebanada punta a punta operable y demostrable en vivo.
- Los **estilos arquitectonicos** del white paper estan materializados (Layered, Pub-Sub, Event
  Processing, Pipes & Filters) y verificados por tests, no solo diagramados.
- El **Active Learning** se entrega como mock honesto: el uncertainty sampling y las metricas son
  reales; el entrenamiento es simulado. La interfaz esta lista para que el motor real entre sin
  reescribir el dominio.
- El valor de negocio es medible: concordancia ~85.7% y ~90% de ahorro de tiempo experto estimado
  frente al etiquetado manual.

### Proximos pasos (Milestone M3)

| Prioridad | Item | US |
|---|---|---|
| Alta | Ingesta real de imagenes (upload + DICOM) con filtros decode/anonimizar/almacenar | US-07 |
| Alta | Pre-clasificador y re-entrenamiento reales (reemplazo del mock) | US-13 / US-15 |
| Media | Galeria con busqueda dedicada | US-18 |
| Media | Filtros de export y reporte PDF del proyecto | US-24 / US-25 |
| Baja | Cambio de rol en vivo | - |
| Baja | Deploy automatizado (config `render.yaml` ya lista) | - |

El pipeline de ingesta y la configuracion de deploy ya dejan el "gancho" para este trabajo: el
camino esta acotado y documentado, no improvisado.

---

## 8. Anexos

Documentacion de soporte del proyecto:

| Documento | Contenido |
|---|---|
| `docs/trazabilidad.md` | Mapeo decision de diseno -> clausula del white paper -> actividad del curso -> riesgo -> estado real en el codigo |
| `docs/arquitectura.md` | Arquitectura objetivo (estilos combinados, componentes) y atributos de calidad ISO/IEC 25010 con estado real |
| `docs/presentacion.md` | Guion de la presentacion / defensa del MVP |

**Repositorio**: `/Users/mateoromano/Documents/mvp_pacusam` (branch `main`).

**Stack**: FastAPI + Jinja2 + HTMX + Alpine + Tailwind (vendorizado local) + SQLite. Auth con
`hashlib.pbkdf2` (sin dependencias C). 248 tests verdes.

**Como correr**:

```
PYTHONPATH=src PACUSAM_DB=pacusam.db .venv/bin/python -m uvicorn pacusam.api:app --reload
```

Abrir en `http://127.0.0.1:8000`.

**Credenciales del demo**:

| Rol | Email | Password |
|---|---|---|
| Curador | demo@pacusam.org | demo1234 |
| Admin | admin@pacusam.org | admin1234 |
