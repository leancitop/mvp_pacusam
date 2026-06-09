"""Capa de presentacion (CAPA 4). FastAPI sobre la capa de dominio.

Un solo `api.py` con auth (SessionMiddleware + require_user via Depends), rutas
project-scoped (home, detalle, curado, cola, analytics) y Active Learning mockeado.
Renderiza SIEMPRE via `templating.render` (Decision #3). Las imagenes reales se
sirven desde /static (Decision #5.1 / #10).

Decisiones canonicas aplicadas:
- Orden de ensamblaje de create_app (#5): app -> conn -> StaticFiles -> Session ->
  exception handler -> rutas -> seed_if_empty.
- D01/D04: require_user via Depends que LANZA _RedirectException; toda obtencion por
  id va envuelta en _guard.
- D05 / integracion #14: _owned_project autoriza por dueño (404 si ajeno, no 403).
- D18 (una sola conexion app.state.conn), D19, D25 (sesion same_site/https_only).
- #7: _STATUS mergeado; rutas auth NO pasan por _guard.
- D08/D13: retrain devuelve partials/toast.html con copy "Confianza media de pendientes".
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import auth, db, seed, services, templating

_STATIC_DIR = Path(__file__).parent / "static"

# #7: un solo mapeo de codigos de dominio -> HTTP status. Las rutas auth NO lo usan.
_STATUS = {
    "image_not_found": 404,
    "project_not_found": 404,
    "label_required": 422,
    "invalid_label": 422,
    "reason_required": 422,
    "name_required": 422,
    "name_too_long": 422,
    "email_exists": 409,
}

# Mensajes legibles para el flash de creacion de proyecto (D20 los lee del detalle).
_FLASH_MSG = {
    "name_required": "El nombre del proyecto es obligatorio.",
    "name_too_long": "El nombre no puede superar los 100 caracteres.",
}


class _RedirectException(Exception):
    """La levanta require_user cuando no hay sesion valida. El exception handler
    de create_app la traduce a RedirectResponse(location, 303) (Decision #4/D01)."""

    def __init__(self, location: str = "/login"):
        self.location = location
        super().__init__(location)


def create_app(db_path: str | None = None) -> FastAPI:
    """Ensambla la app en el ORDEN canonico (Decision #5).

    `db_path=None` usa la env var PACUSAM_DB (db.connect resuelve el default).
    Pasar ':memory:' explicitamente en tests.
    """
    # (1) app + conexion unica compartida (D18) + StaticFiles + SessionMiddleware (D25).
    app = FastAPI(title="PACUSAM MVP", version="1.0.0")
    app.state.conn = db.connect(db_path)
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    # D25: cookie de sesion. Por defecto http-friendly: la demo local corre sobre
    # http://localhost y la cookie de sesion debe poder round-tripear sin HTTPS.
    # En produccion (Render, HTTPS) setear PACUSAM_SECURE_COOKIES=1 para que la
    # cookie viaje con el flag Secure (render.yaml ya lo hace). Tests (TestClient
    # sobre http) tambien funcionan con el default. PACUSAM_INSECURE_COOKIES se
    # sigue respetando como override explicito por compatibilidad.
    secure_cookies = os.environ.get("PACUSAM_SECURE_COOKIES") in ("1", "true", "True")
    if os.environ.get("PACUSAM_INSECURE_COOKIES") in ("1", "true", "True"):
        secure_cookies = False
    app.add_middleware(
        SessionMiddleware,
        secret_key=os.environ.get("PACUSAM_SECRET", "dev-secret"),
        same_site="lax",
        https_only=secure_cookies,
    )

    # (2) exception handler de _RedirectException + _guard / _STATUS.
    @app.exception_handler(_RedirectException)
    async def _redirect_handler(request: Request, exc: _RedirectException):
        return RedirectResponse(exc.location, status_code=303)

    def get_conn():
        return app.state.conn

    def _guard(fn, *args):
        """Ejecuta fn(*args) traduciendo DomainError a HTTPException via _STATUS (D04)."""
        try:
            return fn(*args)
        except services.DomainError as e:
            raise HTTPException(status_code=_STATUS.get(e.code, 400), detail=e.code)

    def require_user(request: Request) -> dict:
        """Dependency: devuelve el usuario logueado o LANZA _RedirectException (D01).

        Limpia la sesion si el user_id apunta a un usuario inexistente (D21.a).
        """
        user_id = request.session.get("user_id")
        if not user_id:
            raise _RedirectException("/login")
        user = auth.get_user(app.state.conn, user_id)
        if user is None:
            request.session.clear()
            raise _RedirectException("/login")
        return user

    def _owned_project(conn, project_id: int, user: dict) -> dict:
        """Autorizacion por dueño (D05 / integracion #14). 404 (no 403) si el proyecto
        no existe o es de otro usuario, para no filtrar existencia."""
        p = _guard(services.get_project, conn, project_id)
        if p["owner_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="project_not_found")
        return p

    def _render_next_card(request: Request, conn, project_id: int):
        """Fragmento HTMX que se inyecta tras cada accion (auto-avance). Devuelve la
        proxima imagen mas incierta + progreso y filmstrip OOB. Usado por
        validate/reject/unreject y por GET /queue."""
        nxt = services.queue_next(conn, project_id)
        prog = services.progress(conn, project_id)
        labels = services.get_project(conn, project_id)["labels"]
        return templating.render(
            request,
            "partials/image_card.html",
            image=nxt,
            progress=prog,
            labels=labels,
            project_id=project_id,
            filmstrip=services.queue_list(conn, project_id),
        )

    # (3) rutas auth (NO pasan por _guard; renderizan el form con error y status 400/401).
    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        return templating.render(request, "login.html")

    @app.get("/register", include_in_schema=False)
    def register_page(request: Request):
        return templating.render(request, "register.html")

    @app.post("/register", include_in_schema=False)
    def register_action(
        request: Request,
        conn=Depends(get_conn),
        email: str = Form(""),
        password: str = Form(""),
    ):
        try:
            user = auth.create_user(conn, email, password)
        except services.DomainError as e:
            return templating.render(
                request,
                "register.html",
                status_code=400,
                email=email,
                error="El email ya esta registrado." if e.code == "email_exists" else e.code,
            )
        request.session["user_id"] = user["id"]
        return RedirectResponse("/", status_code=303)

    @app.post("/login", include_in_schema=False)
    def login_action(
        request: Request,
        conn=Depends(get_conn),
        email: str = Form(""),
        password: str = Form(""),
    ):
        user = auth.authenticate(conn, email, password)
        if user is None:
            return templating.render(
                request,
                "login.html",
                status_code=401,
                email=email,
                error="Credenciales invalidas.",
            )
        request.session["user_id"] = user["id"]
        return RedirectResponse("/", status_code=303)

    @app.post("/logout", include_in_schema=False)
    def logout_action(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    # (4) rutas proyectos (D): home, crear, detalle.
    @app.get("/", include_in_schema=False)
    def home(request: Request, user=Depends(require_user), conn=Depends(get_conn)):
        projects = services.list_projects(conn, user["id"])
        for p in projects:
            p["progress"] = services.progress(conn, p["id"])
        return templating.render(
            request,
            "home.html",
            user=user,
            projects=projects,
            # Nombre distinto del macro `flash` para no colisionar en el template.
            flash_message=request.query_params.get("flash"),
        )

    @app.post("/projects", include_in_schema=False)
    def create_project_action(
        request: Request,
        user=Depends(require_user),
        conn=Depends(get_conn),
        name: str = Form(""),
        description: str = Form(""),
        domain: str = Form(""),
        labels: str = Form(""),
    ):
        label_list = [l.strip() for l in labels.split(",") if l.strip()]
        try:
            project = services.create_project(
                conn, user["id"], name, description, domain, label_list
            )
        except services.DomainError as e:
            msg = _FLASH_MSG.get(e.code, e.code)
            return RedirectResponse(f"/?flash={msg}", status_code=303)
        # Sembrar las imagenes del dataset del proyecto si existen en disco.
        filenames = seed._filenames_for(project["id"])
        if filenames:
            services.seed_images(conn, project["id"], filenames)
        # #6: POST /projects redirige a /projects/{id}.
        return RedirectResponse(f"/projects/{project['id']}", status_code=303)

    @app.get("/projects/{project_id}", include_in_schema=False)
    def project_detail(
        project_id: int, request: Request,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        project = _owned_project(conn, project_id, user)
        prog = services.progress(conn, project_id)
        return templating.render(
            request, "project.html", user=user, project=project, prog=prog
        )

    # (5) rutas curado (E): pagina, cola (fragmento), acciones.
    @app.get("/projects/{project_id}/curate", include_in_schema=False)
    def curate_page(
        project_id: int, request: Request,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        project = _owned_project(conn, project_id, user)
        nxt = services.queue_next(conn, project_id)
        return templating.render(
            request,
            "curate.html",
            user=user,
            project=project,
            image=nxt,
            labels=project["labels"],
            filmstrip=services.queue_list(conn, project_id),
            progress=services.progress(conn, project_id),
            project_id=project_id,
        )

    @app.get("/projects/{project_id}/queue", include_in_schema=False)
    def queue_fragment(
        project_id: int, request: Request,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        _owned_project(conn, project_id, user)
        return _render_next_card(request, conn, project_id)

    @app.post("/images/{image_id}/validate", include_in_schema=False)
    def validate(
        image_id: int, request: Request, label: str = Form(""),
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        img = _guard(services.get_image, conn, image_id)
        _owned_project(conn, img["project_id"], user)
        _guard(services.validate_image, conn, image_id, label)
        return _render_next_card(request, conn, img["project_id"])

    @app.post("/images/{image_id}/reject", include_in_schema=False)
    def reject(
        image_id: int, request: Request, reason: str = Form(""),
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        img = _guard(services.get_image, conn, image_id)
        _owned_project(conn, img["project_id"], user)
        _guard(services.reject_image, conn, image_id, reason)
        return _render_next_card(request, conn, img["project_id"])

    @app.post("/images/{image_id}/unreject", include_in_schema=False)
    def unreject(
        image_id: int, request: Request,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        img = _guard(services.get_image, conn, image_id)
        _owned_project(conn, img["project_id"], user)
        _guard(services.unreject_image, conn, image_id)
        return _render_next_card(request, conn, img["project_id"])

    @app.get("/progress", include_in_schema=False)
    def get_progress(
        project_id: int, user=Depends(require_user), conn=Depends(get_conn),
    ):
        _owned_project(conn, project_id, user)
        return services.progress(conn, project_id)

    # (6) rutas AL + analytics (F).
    @app.post("/projects/{project_id}/retrain", include_in_schema=False)
    def retrain(
        project_id: int, request: Request,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        _owned_project(conn, project_id, user)
        result = _guard(services.simulate_retrain, conn, project_id)
        # D13: copy unificado a "Confianza media de pendientes +X%" + cap del re-click.
        if result["status"] == "calibrado":
            kind = "info"
            message = "El modelo ya esta bien calibrado para estas pendientes."
        else:
            kind = "success"
            message = (
                f"Reentrenamiento simulado: confianza media de pendientes "
                f"+{result['improvement_pct']:.1f}% "
                f"(ahora {result['new_avg_confidence'] * 100:.0f}%)."
            )
        return templating.render(
            request, "partials/toast.html", kind=kind, message=message
        )

    @app.get("/projects/{project_id}/analytics", include_in_schema=False)
    def analytics_page(
        project_id: int, request: Request,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        project = _owned_project(conn, project_id, user)
        return templating.render(
            request,
            "analytics.html",
            user=user,
            project=project,
            concordance=services.concordance(conn, project_id),
            distribution=services.class_distribution(conn, project_id),
            progress=services.progress(conn, project_id),
            time_saved=services.time_saved(conn, project_id),
        )

    # (7) re-seed determinista al arrancar, sobre la MISMA conexion (D03). Corre una
    # vez en build; solo siembra si projects esta vacio (no pisa datos existentes).
    seed.seed_if_empty(app.state.conn)

    return app


app = create_app()
