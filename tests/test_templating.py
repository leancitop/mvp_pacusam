"""Unit tests del módulo de templating compartido (Track B / Capa 2)."""
from __future__ import annotations

from pathlib import Path

from starlette.requests import Request

from pacusam import templating


def _fake_request() -> Request:
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    return Request(scope)


def test_templates_dir_apunta_a_carpeta_templates():
    expected = Path(templating.__file__).parent / "templates"
    assert templating.TEMPLATES_DIR == expected
    assert templating.TEMPLATES_DIR.is_dir()


def test_render_devuelve_html_con_contexto():
    probe = templating.TEMPLATES_DIR / "_probe.html"
    probe.write_text("<p>hola {{ nombre }}</p>", encoding="utf-8")
    try:
        resp = templating.render(_fake_request(), "_probe.html", nombre="curador")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert b"hola curador" in resp.body
    finally:
        probe.unlink()


def test_render_acepta_status_code():
    probe = templating.TEMPLATES_DIR / "_probe_status.html"
    probe.write_text("<p>x</p>", encoding="utf-8")
    try:
        resp = templating.render(_fake_request(), "_probe_status.html", status_code=422)
        assert resp.status_code == 422
    finally:
        probe.unlink()
