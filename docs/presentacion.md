# Guion de presentacion + demo en vivo - PACUSAM

Duracion objetivo: 8 a 10 minutos. Grupo 9 (Mateo Romano + Leandro Escudero), LCD-UNSAM, 1C 2026. Cliente: CIMeT-UNSAM.

> Antes de empezar: app corriendo en `http://127.0.0.1:8000`, sesion cerrada, dos pestañas listas (una para el curador, otra para el admin). Credenciales a mano: curador `demo@pacusam.org` / `demo1234`, admin `admin@pacusam.org` / `admin1234`. Tener el visor a buen tamaño y el volumen del cursor visible (vas a curar con teclado).

## Como leer este guion

- **CLICKEAR**: la accion concreta sobre la pantalla.
- **DECIR**: el texto sugerido para acompañar (no leerlo palabra por palabra, es la idea).
- **WOW**: el momento de impacto y la frase que lo remata.
- Tono: claro y con seguridad. Lo que esta implementado se muestra; lo que esta mockeado se explica con honestidad (es una decision de alcance, no una carencia).

## Timing por bloque

| Bloque | Contenido | Tiempo |
|---|---|---|
| 1 | Apertura: el problema y la solucion | ~1:00 |
| 2 | Login + home (2 proyectos) | ~0:45 |
| 3 | Curado con teclado A/C/R + visor | ~2:00 |
| 4 | Estrategia de sampling + filmstrip por incertidumbre | ~1:15 |
| 5 | Feedback loop: cruzar el umbral y re-entrenar solo | ~1:15 |
| 6 | Analytics (concordancia, matriz, A/B, F1, tiempo ahorrado) | ~1:45 |
| 7 | Re-entrenar manual (toast) | ~0:30 |
| 8 | Admin: roles + log de actividad | ~0:45 |
| 9 | Export CSV + cierre (valor + roadmap) | ~1:00 |

---

## Bloque 1 - Apertura (~1:00)

**DECIR** (gancho, 2 a 3 frases):

- "En curado de imagenes medicas el cuello de botella no es la computadora: es el experto. Hasta el 80% del tiempo de un proyecto de Ciencia de Datos clinica se va en etiquetar a mano, imagen por imagen."
- "PACUSAM le da vuelta el problema: en vez de pedirle al medico que etiquete todo, usamos Active Learning para mostrarle primero lo que mas le enseña al modelo, y que confirme o corrija con una tecla."
- "El resultado: curado asistido tipo revision rapida, con metricas de calidad y un modelo que se re-entrena solo a medida que el experto trabaja. Se lo muestro en vivo."

**DECIR** (encuadre, una frase): "Esto es el MVP del milestone M2: un walking skeleton punta a punta. El motor de Active Learning esta mockeado de forma honesta, y al final explico exactamente que es real y que esta simulado, porque fue una decision de alcance documentada."

---

## Bloque 2 - Login + home (~0:45)

**CLICKEAR**: abrir `http://127.0.0.1:8000`, entrar como `demo@pacusam.org` / `demo1234`.

**DECIR**: "Login con sesion firmada. Las contraseñas se guardan con hash pbkdf2 de la libreria estandar, sin dependencias nativas. Hay roles: este es un curador."

**CLICKEAR**: quedar en el home. Mostrar las dos tarjetas de proyecto.

**DECIR**: "El curador ve solo sus proyectos. Tenemos dos datasets reales: radiografias de torax con etiquetas NORMAL y PNEUMONIA, y celulas sanguineas con cuatro tipos de leucocitos. Cada tarjeta muestra el progreso de curado. Entramos al de radiografias."

---

## Bloque 3 - Curado con teclado A/C/R + visor (~2:00)

**CLICKEAR**: entrar a "Radiografias de torax" y luego a curar (la pantalla `Curado por incertidumbre`).

**DECIR**: "Esta es la pantalla de trabajo. A la derecha, el visor estilo OHIF con la radiografia. A la izquierda, la sugerencia del modelo y su confianza. Y fijate arriba del todo: 'Ordenado por incertidumbre, te mostramos primero lo que el modelo menos sabe'. No es una cola cualquiera."

**CLICKEAR**: senalar la barra de confianza y la linea "Incertidumbre (proxy 1 - confianza)".

**DECIR**: "El modelo sugiere una etiqueta con un nivel de confianza. La incertidumbre es el complemento. Cuanto mas duda el modelo, mas arriba esta esa imagen en la cola, porque es la que mas valor aporta etiquetar."

> **WOW 1 - Curado por teclado (tipo "revision clinica rapida").** Esto es lo que hace que el curado sea fluido.

**CLICKEAR**: curar 3 o 4 imagenes seguidas, narrando cada tecla:
- Tecla **A** en una con confianza alta -> "Apruebo la sugerencia. Mira que avanza sola a la siguiente, sin tocar el mouse."
- Tecla **A** de nuevo -> "Otra confirmada."
- Tecla **C** en una -> "Si el modelo se equivoco, corrijo: aparecen las otras etiquetas y elijo la correcta." (clickear la etiqueta correcta).
- Tecla **R** en una -> "Y si la imagen no sirve, la rechazo con un motivo del menu." (elegir un motivo y confirmar).

**DECIR** (frase WOW): "Sin tocar el mouse. A apruebo, C corrijo, R rechazo, y avanza sola. Un experto cura cientos de imagenes asi en minutos, no en horas."

**CLICKEAR**: en el visor de la derecha, hacer foco y usar `=` para acercar, `-` para alejar, `i` para invertir y `0` para resetear. Tambien arrastrar con el mouse cuando esta con zoom.

**DECIR**: "El visor responde como un PACS: zoom con igual y menos, invertir contraste con i, resetear con cero, y arrastrar para hacer pan. El curador inspecciona la imagen de verdad antes de decidir."

---

## Bloque 4 - Estrategia de sampling + filmstrip (~1:15)

**CLICKEAR**: arriba a la derecha, el selector de estrategia. Tocar "Aleatoria", luego "Secuencial", y volver a "Incertidumbre". Senalar que la proxima imagen cambia.

**DECIR**: "El curador puede elegir como se ordena la cola: aleatoria, secuencial, o por incertidumbre. La de incertidumbre es la de Active Learning: trae primero lo que el modelo menos sabe. Volvemos a esa, que es la que aporta valor."

> **WOW 2 - Uncertainty sampling visible.** Aca se ve el Active Learning con los ojos.

**CLICKEAR**: senalar el filmstrip de miniaturas abajo. Indicar el recuadro azul ("la proxima a etiquetar") y el orden de las miniaturas.

**DECIR** (frase WOW): "Esta tira de abajo es la cola, ordenada por incertidumbre. El recuadro azul es la proxima imagen. No etiquetamos cualquier cosa: etiquetamos las que mas le enseñan al modelo. Eso es Active Learning, y aca el ordenamiento por incertidumbre es codigo real, no un adorno."

**CLICKEAR** (opcional, si hay tiempo): tocar un chip de filtro por clase para mostrar que el filmstrip filtra por etiqueta sugerida.

**DECIR** (opcional): "Y se puede filtrar por clase para enfocarse en un tipo de imagen."

---

## Bloque 5 - Feedback loop: cruzar el umbral (~1:15)

**CLICKEAR**: senalar el contador "Hacia el proximo re-entrenamiento" en el panel izquierdo (muestra validadas / 20).

**DECIR**: "Aca esta el corazon arquitectonico. Cada validacion suma a un contador hacia un umbral. En el demo, 20 validadas."

> **WOW 3 - El modelo se re-entrena solo (feedback loop).**

**CLICKEAR**: curar con A varias imagenes hasta que el contador cruce el umbral (la barra se pone verde y aparece "UmbralAlcanzado: el modelo se re-entrena").

**DECIR** (frase WOW): "Cuando cruzamos el umbral, el sistema emite un evento, 'UmbralAlcanzado', y eso dispara un re-entrenamiento solo, sin que nadie apriete un boton. El curador trabaja, el modelo aprende detras. Ese es el loop cerrado."

**DECIR** (encuadre arquitectonico, breve): "Por dentro esto es un bus de eventos publish-subscribe. Cada validacion publica un evento; cuando se acumulan suficientes, un evento complejo derivado dispara el ciclo. Es el patron de Event Processing y el feedback loop que cierra el pipeline de ingesta. Esta todo en `events.py`."

> Plan B si no se llega al umbral en vivo: explicarlo con el contador en pantalla. "Si sigo curando hasta llegar a 20, este evento dispara el re-entrenamiento automatico. Lo vemos reflejado en la analitica, que es donde vamos ahora."

---

## Bloque 6 - Analytics (~1:45)

**CLICKEAR**: boton "Analitica" (o el link "Ver re-entrenamiento" / "Ver analitica").

**DECIR**: "Toda esta actividad se traduce en metricas de calidad. Esta pantalla es la que justifica el valor del enfoque."

Recorrer de arriba hacia abajo, senalando cada tarjeta:

- **Concordancia con el modelo** (~85%): "Cuantas veces el curador confirmo la sugerencia. Aca esta alrededor del 85%, que indica un pre-clasificador confiable. Cuando el modelo y el experto coinciden, el curado vuela."
- **Progreso de curado** y **Total de imagenes**: "Cuanto del dataset esta curado y el tamaño total."
- **Tiempo ahorrado** (frase clave): "Estimamos unos 3 segundos por imagen con curado asistido contra 30 a mano. El ahorro ronda el 90%. Es consistente con herramientas como MONAI Label, que reportan entre 50 y 80% de reduccion del esfuerzo de anotacion."

**CLICKEAR**: bajar a la **Matriz de confusion** y a **Precision y recall por clase**.

**DECIR**: "Matriz de confusion entre lo que sugirio el modelo y la etiqueta final del experto: la diagonal en verde son los aciertos. Y precision y recall por clase, tratando la etiqueta del curador como verdad de referencia."

**CLICKEAR**: bajar a **Comparativa A/B** (Manual vs PACUSAM-AL).

**DECIR**: "La comparativa A/B lo deja claro: etiquetado manual contra el flujo PACUSAM. Tiempo total, throughput en imagenes por hora (pasa de unas 120 a la hora a más de 1000), y el ahorro de tiempo."

**CLICKEAR**: senalar el **sparkline de F1-score por ciclo** y el timeline de **Ciclos de aprendizaje activo**.

**DECIR**: "Y aca esta el efecto del feedback loop: la curva de F1 por ciclo. Cada re-entrenamiento sube la confianza del modelo sobre las pendientes. El historial muestra ciclo a ciclo como mejora, de 0.86 a 0.90 de F1 en los ciclos sembrados."

> Honestidad (decirlo aca o en el cierre): "Las metricas de incertidumbre y concordancia se calculan sobre datos reales en la base. El entrenamiento en si esta simulado con formulas deterministas crecientes: fue una decision de alcance para mitigar el riesgo de que el motor de AL fuera demasiado complejo para el MVP. La interfaz es real, asi que el motor real entra sin tocar la capa de servicios ni la API."

---

## Bloque 7 - Re-entrenar manual (toast) (~0:30)

**CLICKEAR**: arriba a la derecha de la analitica, "Re-entrenar (simulado)".

**DECIR**: "Tambien se puede disparar a mano. Aparece la confirmacion."

**CLICKEAR**: senalar el toast que aparece ("Reentrenamiento simulado: confianza media de pendientes +X%...").

**DECIR**: "El toast informa cuanto subio la confianza media de las pendientes. Lo automatico que vimos antes y este boton manual usan exactamente el mismo servicio."

---

## Bloque 8 - Admin: roles + log (~0:45)

**CLICKEAR**: en la otra pestaña, entrar como `admin@pacusam.org` / `admin1234` e ir a "Administracion" (`/admin`).

**DECIR**: "Cambiamos de rol. Este usuario es admin, y tiene una vista que el curador no ve: si un curador intenta entrar a /admin, recibe un 403."

**CLICKEAR**: senalar la tabla de **Usuarios** (email + rol) y la tabla de **Actividad**.

**DECIR**: "Lista de usuarios con su rol, y un log de actividad: cada validacion, correccion y rechazo queda registrado con usuario, accion, imagen y proyecto. Trazabilidad completa, que en un contexto clinico es clave."

**CLICKEAR** (opcional): usar el filtro por usuario o accion.

**DECIR** (opcional): "Y el log se filtra por usuario o por tipo de accion."

---

## Bloque 9 - Export CSV + cierre (~1:00)

**CLICKEAR**: volver al proyecto, en analitica tocar "Exportar CSV" (o navegar a `/projects/{id}/export.csv`).

**DECIR**: "Cuando el dataset esta curado, se exporta. CSV o JSON, con la etiqueta final, la sugerencia, la confianza y la fecha de validacion. Listo para entrenar un modelo de verdad."

**DECIR** (cierre - valor):

- "En resumen: PACUSAM convierte el curado de imagenes medicas de un trabajo manual y lento en un flujo asistido. El experto confirma con una tecla, el sistema le muestra primero lo que mas importa, y el modelo se re-entrena solo. Mostramos un ahorro de tiempo cercano al 90% y metricas de calidad que lo respaldan."
- "Arquitectonicamente materializamos cuatro estilos: capas, publish-subscribe, procesamiento de eventos y pipes & filters, con 248 tests en verde. No son diagramas: son codigo testeado."

**DECIR** (cierre - roadmap, honesto):

- "Lo que queda para el siguiente milestone, decidido y documentado, no olvidado: la ingesta real de imagenes con soporte DICOM (US-07), el reemplazo del motor de Active Learning mockeado por uno real (US-13/15) que entra sin tocar servicios ni API, una galeria de busqueda dedicada, filtros de export y un reporte PDF del proyecto."
- "Gracias. Quedamos para preguntas."

---

## Recordatorio rapido de atajos (chuleta del presentador)

| Tecla | Accion |
|---|---|
| `A` | Confirmar la sugerencia del modelo |
| `C` | Corregir (elegir otra etiqueta) |
| `R` | Rechazar (con motivo) |
| `Esc` | Cancelar / cerrar |
| `?` | Overlay de atajos |
| `=` / `+` | Zoom in en el visor |
| `-` | Zoom out en el visor |
| `0` | Reset del visor |
| `i` | Invertir contraste |

## Los tres WOW moments (no perderselos)

1. **Curado por teclado con auto-avance** (Bloque 3): "Sin tocar el mouse. A apruebo, C corrijo, R rechazo, y avanza sola."
2. **Filmstrip ordenado por incertidumbre** (Bloque 4): "Etiquetamos las que mas le enseñan al modelo."
3. **Feedback loop automatico** (Bloque 5): "Cruzamos el umbral y el modelo se re-entrena solo."
