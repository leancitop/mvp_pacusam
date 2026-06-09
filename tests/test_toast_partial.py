"""El fragmento partials/toast.html reusa el macro flash (D08)."""
from __future__ import annotations

from starlette.requests import Request

from pacusam import templating


def _req() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def test_toast_renderiza_flash_con_kind_y_message():
    html = templating.render(
        _req(),
        "partials/toast.html",
        kind="success",
        message="Confianza media de pendientes +12%",
    ).body.decode()
    assert "Confianza media de pendientes +12%" in html
    assert "bg-approved-tint" in html


def test_toast_error_usa_estilo_rejected():
    html = templating.render(
        _req(), "partials/toast.html", kind="error", message="Algo falló"
    ).body.decode()
    assert "bg-rejected-tint" in html
