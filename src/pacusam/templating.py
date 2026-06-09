"""Config compartida de Jinja2 para toda la UI (Track B / Capa 2).

Un solo punto de verdad para `Jinja2Templates` (Decisión #3): api.py y los
fragmentos HTMX importan `templates`/`render` de acá en vez de re-instanciar.
Los partials (progress_bar, confidence_bar, flash) viven en templates/partials/
y se usan vía `{% from "partials/ui.html" import ... %}` desde cada track.
"""
from __future__ import annotations

from pathlib import Path

from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def render(
    request: Request, name: str, status_code: int = 200, **context
) -> HTMLResponse:
    """Renderiza `name` inyectando `request` (Jinja2Templates lo exige) + contexto.

    Único helper de render del proyecto (Decisión #3). Devuelve HTMLResponse para
    que las rutas de página y los fragmentos HTMX compartan el mismo camino.
    """
    return templates.TemplateResponse(request, name, context, status_code=status_code)
