"""Verifica que base.html trae el design system completo (Track B / Capa 2).

D15: los assets (htmx/alpine/tailwind/lucide) se sirven LOCAL desde
/static/vendor (versiones pineadas), no por CDN.
"""
from __future__ import annotations

from starlette.requests import Request

from pacusam import templating


def _req() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _render_base() -> str:
    child = templating.TEMPLATES_DIR / "_probe_base.html"
    child.write_text(
        '{% extends "base.html" %}'
        "{% block content %}<main>PROBE_BODY</main>{% endblock %}",
        encoding="utf-8",
    )
    try:
        return templating.render(
            _req(), "_probe_base.html", title="PROBE_TITLE"
        ).body.decode()
    finally:
        child.unlink()


def test_base_sirve_vendor_local_no_cdn():
    html = _render_base()
    # D15: assets pineados servidos local, no CDN.
    assert "/static/vendor/tailwind.min.js" in html
    assert "/static/vendor/htmx.min.js" in html
    assert "/static/vendor/alpine.min.js" in html
    assert "/static/vendor/lucide.min.js" in html
    assert "cdn.tailwindcss.com" not in html
    assert "unpkg.com" not in html


def test_base_carga_fonts():
    html = _render_base()
    assert "Inter" in html and "Lora" in html and "JetBrains+Mono" in html


def test_base_define_tokens_de_paleta_en_tailwind_config():
    html = _render_base()
    assert "#FCFBF9" in html  # app
    assert "#2563EB" in html  # accent
    assert "#16A34A" in html  # approved
    assert "#DC2626" in html  # rejected
    assert "#D97706" in html  # flag
    assert "tailwind.config" in html


def test_base_tiene_listener_de_error_htmx():
    html = _render_base()
    assert "htmx:responseError" in html  # D20
    assert "toast-host" in html


def test_base_inserta_titulo_y_contenido_del_hijo():
    html = _render_base()
    assert "PROBE_TITLE" in html
    assert "PROBE_BODY" in html
