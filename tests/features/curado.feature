# Criterios de aceptación de US-10 (Validar imágenes pre-clasificadas) + US-09 (Progreso).
# El pre-clasificador es un STUB (US-15 real es M3): cada imagen llega con
# etiqueta sugerida + score de confianza.
# language: es

Característica: Curado de imágenes pre-clasificadas
  Como curador quiero validar las sugerencias del modelo y ver el progreso.

  Antecedentes:
    Dado un conjunto de 3 imágenes sembradas

  Escenario: Cada imagen pendiente muestra sugerencia y confianza
    Cuando pido la próxima imagen pendiente
    Entonces la imagen trae una etiqueta sugerida y un nivel de confianza
    Y se informa cuántas imágenes pendientes quedan

  Escenario: Validar una imagen actualiza el progreso
    Cuando valido la próxima imagen con la etiqueta "normal"
    Entonces el progreso muestra 1 etiquetada de 3 y 2 pendientes
