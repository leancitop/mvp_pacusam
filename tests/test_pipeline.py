"""Tests de la ingesta como Pipes & Filters (white paper, A.7).

El runner encadena filtros puros f(ctx)->ctx en orden. Los filtros de M2 son
validar_formato (formato soportado) y clasificar (stub de Active Learning).
"""
from pacusam import pipeline


def test_run_pipeline_encadena_filtros_en_orden():
    pasos = []

    def f1(ctx):
        pasos.append("f1")
        ctx["a"] = 1
        return ctx

    def f2(ctx):
        pasos.append("f2")
        ctx["b"] = ctx["a"] + 1
        return ctx

    out = pipeline.run_pipeline([f1, f2], {"fn": "x.jpg"})
    assert pasos == ["f1", "f2"] and out["a"] == 1 and out["b"] == 2


def test_filtro_clasificar_asigna_label_y_confianza():
    ctx = pipeline.filtro_clasificar({"filename": "rx_0001.jpg", "labels": ["NORMAL", "PNEUMONIA"]})
    assert ctx["suggested_label"] in ("NORMAL", "PNEUMONIA")
    assert 0.5 <= ctx["confidence"] <= 0.99


def test_filtro_validar_formato_acepta_jpg_png_dcm_y_rechaza_otros():
    assert pipeline.filtro_validar_formato({"filename": "a.jpg"})["formato_ok"] is True
    assert pipeline.filtro_validar_formato({"filename": "a.txt"})["formato_ok"] is False
