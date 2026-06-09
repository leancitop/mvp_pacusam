# language: es
# Acceptance BDD del curado asistido (MVP PACUSAM), project-scoped.
# Migrado del legacy (D10): los escenarios operan sobre un proyecto con imagenes
# sembradas por SQL (project_id explicito) contra la capa de dominio.

Característica: Curado asistido por incertidumbre
  Como curador quiero validar primero las imágenes donde el modelo duda
  y que cada acción actualice el avance del proyecto.

  Escenario: La cola entrega primero la imagen más incierta
    Dado un proyecto con imágenes de confianza 0.90, 0.55 y 0.72
    Cuando pido la próxima imagen de la cola
    Entonces recibo la imagen de confianza 0.55

  Escenario: Validar una imagen actualiza el progreso
    Dado un proyecto con imágenes de confianza 0.90, 0.55 y 0.72
    Cuando valido la próxima imagen de la cola con la etiqueta "normal"
    Entonces el progreso muestra 1 validada y 2 pendientes

  Escenario: Rechazar con motivo excluye la imagen de la cola
    Dado un proyecto con imágenes de confianza 0.90, 0.55 y 0.72
    Cuando rechazo la próxima imagen de la cola con motivo "Imagen borrosa"
    Entonces el progreso muestra 1 rechazada y 2 pendientes
    Y la próxima imagen de la cola es la de confianza 0.72
