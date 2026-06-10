from pacusam import events


def test_subscribe_y_publish_llama_handlers():
    bus = events.EventBus()
    recibidos = []
    bus.subscribe("ImagenValidada", lambda p: recibidos.append(p))
    bus.publish("ImagenValidada", {"image_id": 7})
    assert recibidos == [{"image_id": 7}]


def test_publish_sin_suscriptores_no_rompe():
    bus = events.EventBus()
    bus.publish("CicloFinalizo", {"project_id": 1})  # no debe lanzar


def test_un_handler_que_falla_no_corta_a_los_demas():
    bus = events.EventBus()
    ok = []
    bus.subscribe("X", lambda p: (_ for _ in ()).throw(RuntimeError("boom")))
    bus.subscribe("X", lambda p: ok.append(1))
    bus.publish("X", {})  # best-effort: no propaga
    assert ok == [1]


def test_eventos_canonicos_declarados():
    # Los 4 eventos del white paper estan declarados como constantes.
    assert events.IMAGENES_SUBIDAS == "ImagenesSubidas"
    assert events.IMAGEN_VALIDADA == "ImagenValidada"
    assert events.UMBRAL_ALCANZADO == "UmbralAlcanzado"
    assert events.CICLO_FINALIZO == "CicloFinalizo"
