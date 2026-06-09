"""Unit tests del stub de Active Learning (CAPA 1 — backend logico)."""
from __future__ import annotations

from pacusam import classifier

LABELS = ["NORMAL", "PNEUMONIA"]


def test_suggest_elige_una_label_del_proyecto():
    label, conf = classifier.suggest("rx_0001.jpeg", LABELS)
    assert label in LABELS


def test_suggest_confianza_en_rango():
    _, conf = classifier.suggest("rx_0001.jpeg", LABELS)
    assert 0.50 <= conf <= 0.99


def test_suggest_es_determinista():
    a = classifier.suggest("rx_0042.jpeg", LABELS)
    b = classifier.suggest("rx_0042.jpeg", LABELS)
    assert a == b


def test_suggest_respeta_labels_multiclase():
    multi = ["NEUTROPHIL", "EOSINOPHIL", "LYMPHOCYTE", "MONOCYTE"]
    label, _ = classifier.suggest("bccd_0007.jpeg", multi)
    assert label in multi


def test_suggest_genera_mezcla_de_confianzas():
    # Sobre un lote grande debe haber confianzas altas (>0.9) Y bajas (<0.6):
    # eso es lo que alimenta el uncertainty sampling.
    confs = [classifier.suggest(f"img_{i:04d}.jpeg", LABELS)[1] for i in range(100)]
    assert any(c > 0.90 for c in confs), "faltan confianzas altas"
    assert any(c < 0.60 for c in confs), "faltan confianzas bajas"


def test_suggest_labels_vacio_lanza():
    import pytest

    with pytest.raises(ValueError):
        classifier.suggest("x.jpeg", [])
