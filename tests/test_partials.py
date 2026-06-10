"""Unit tests de los macros Jinja compartidos (Track B / Capa 2).

Firmas (fuente única, Decisión #8/D08):
  progress_bar(progress) · confidence_bar(confidence) · flash(kind, message)
"""
from __future__ import annotations

from starlette.requests import Request

from pacusam import templating


def _req() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _render(snippet: str, **ctx) -> str:
    probe = templating.TEMPLATES_DIR / "_probe_partials.html"
    probe.write_text(
        '{% from "partials/ui.html" import progress_bar, confidence_bar, flash %}\n'
        + snippet,
        encoding="utf-8",
    )
    try:
        return templating.render(_req(), "_probe_partials.html", **ctx).body.decode()
    finally:
        probe.unlink()


def test_progress_bar_pinta_porcentaje():
    html = _render("{{ progress_bar(42.5) }}")
    assert "42.5%" in html
    assert "width: 42.5%" in html
    assert 'role="progressbar"' in html


def test_confidence_bar_umbrales():
    alta = _render("{{ confidence_bar(0.95) }}")
    media = _render("{{ confidence_bar(0.72) }}")
    baja = _render("{{ confidence_bar(0.55) }}")
    assert "95%" in alta and "bg-approved" in alta
    assert "72%" in media and "bg-accent" in media
    assert "55%" in baja and "bg-flag" in baja


def test_confidence_bar_borde_inferior_de_accent():
    # 0.60 exacto cae en accent (>= 0.60), 0.59 cae en flag.
    borde = _render("{{ confidence_bar(0.60) }}")
    debajo = _render("{{ confidence_bar(0.59) }}")
    assert "bg-accent" in borde
    assert "bg-flag" in debajo


def test_flash_error_muestra_mensaje_y_estilo_rejected():
    html = _render('{{ flash("error", "La etiqueta es obligatoria") }}')
    assert "La etiqueta es obligatoria" in html
    assert "bg-rejected-tint" in html
    assert "text-rejected" in html


def test_flash_success_y_flag():
    ok = _render('{{ flash("success", "Validación guardada") }}')
    fl = _render('{{ flash("flag", "Confianza baja") }}')
    assert "bg-approved-tint" in ok
    assert "bg-flag-tint" in fl


def test_flash_vacio_no_renderiza_nada():
    html = _render('{{ flash("error", "") }}')
    assert "bg-rejected-tint" not in html
