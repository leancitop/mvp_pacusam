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

import csv
import io
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import __version__, auth, db, events, seed, services, templating

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
    "password_too_short": 422,
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
        """Guarda el destino del redirect (default /login) que aplicara el handler."""
        self.location = location
        super().__init__(location)


def create_app(db_path: str | None = None) -> FastAPI:
    """Ensambla la app en el ORDEN canonico (Decision #5).

    `db_path=None` usa la env var PACUSAM_DB (db.connect resuelve el default).
    Pasar ':memory:' explicitamente en tests.

    Event Processing (white paper A.7) materializado por el bus de events.py:
    - SEP (Single Event Processing): cada POST /validate|reject es una accion
      uno-a-uno que emite `ImagenValidada`.
    - OEP (Online Event Processing): el score de confianza se ve al instante y la
      cola se reordena por incertidumbre en cada accion (_render_next_card ->
      queue_next).
    - CEP (Complex Event Processing): `UmbralAlcanzado` es un evento DERIVADO de N
      `ImagenValidada` acumuladas (umbral), que aca suscribimos para disparar
      automaticamente el re-entrenamiento (feedback loop de Pipes & Filters via
      Pub-Sub).
    """
    # (1) app + conexion unica compartida (D18) + StaticFiles + SessionMiddleware (D25).
    app = FastAPI(title="PACUSAM MVP", version="1.0.0")
    app.state.conn = db.connect(db_path)

    # (1.b) Wiring de eventos (Pub-Sub, A.7). clear() al inicio para no acumular
    # suscriptores duplicados cuando se crean varias apps (tests). El suscriptor
    # del feedback loop (CEP) muta estado: por eso se registra SOLO aca, nunca a
    # nivel de import de services (asi los tests unitarios de dominio no auto-
    # reentrenan). La semilla usa retrain_threshold=20, fuera del alcance de los
    # tests existentes, asi que el auto-retrain no se dispara en ellos.
    events.bus.clear()

    def _on_umbral(payload):
        """Suscriptor CEP: al alcanzar el umbral de validadas, dispara un ciclo de
        re-entrenamiento automatico (feedback loop).

        Corre simulate_retrain sobre las pendientes. Si al cruzar el umbral ya no
        quedan pendientes que reentrenar (status 'calibrado'), igual registra un
        ciclo minimo para dejar trazabilidad de que el umbral disparo el ciclo
        (sin alterar el comportamiento de simulate_retrain, que sigue intacto)."""
        conn = payload["conn"]
        project_id = payload["project_id"]
        result = services.simulate_retrain(conn, project_id)
        if result["status"] != "ok":
            # El re-entrenamiento no produjo cambios (sin pendientes / ya
            # calibrado), pero el umbral SI se cruzo: dejamos constancia del
            # ciclo disparado por el feedback loop.
            services.record_cycle(conn, project_id, 0, 0.0, 0.0, 0.0)

    events.bus.subscribe(events.UMBRAL_ALCANZADO, _on_umbral)

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
        """Traduce _RedirectException a un RedirectResponse 303 al destino indicado."""
        return RedirectResponse(exc.location, status_code=303)

    def get_conn():
        """Dependency: devuelve la unica conexion compartida de la app (D18)."""
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

    def require_admin(user=Depends(require_user)) -> dict:
        """D3. Dependency admin: reusa require_user (no-auth -> 303 /login) y exige
        role=='admin' (sino 403). El dict de require_user ya trae 'role' (D1)."""
        if user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="forbidden")
        return user

    def _owned_project(conn, project_id: int, user: dict) -> dict:
        """Autorizacion por dueño (D05 / integracion #14). 404 (no 403) si el proyecto
        no existe o es de otro usuario, para no filtrar existencia."""
        p = _guard(services.get_project, conn, project_id)
        if p["owner_id"] != user["id"]:
            raise HTTPException(status_code=404, detail="project_not_found")
        return p

    # A1: estrategias de sampling validas. Una desconocida cae a uncertainty.
    _STRATEGIES = ("uncertainty", "sequential", "random")

    def _norm_strategy(strategy: str | None) -> str:
        """Normaliza la estrategia de sampling: invalida/None -> uncertainty (A1)."""
        return strategy if strategy in _STRATEGIES else "uncertainty"

    def _render_next_card(
        request: Request,
        conn,
        project_id: int,
        label: str | None = None,
        strategy: str = "uncertainty",
    ):
        """Fragmento HTMX que se inyecta tras cada accion (auto-avance). Devuelve la
        proxima imagen + progreso y filmstrip OOB. Usado por validate/reject/unreject
        y por GET /queue.

        US-17: `label` (None = todas) filtra SOLO el filmstrip.
        A1: `strategy` SOLO afecta a queue_next (la proxima imagen). El filmstrip
        (queue_list) SIEMPRE usa uncertainty para no romper test_api_filter/services;
        validate/reject/unreject no propagan strategy (el auto-avance vuelve a
        uncertainty, aceptable para el MVP)."""
        active_strategy = _norm_strategy(strategy)
        nxt = services.queue_next(conn, project_id, strategy=active_strategy)
        prog = services.progress(conn, project_id)
        labels = services.get_project(conn, project_id)["labels"]
        return templating.render(
            request,
            "partials/image_card.html",
            image=nxt,
            progress=prog,
            labels=labels,
            project_id=project_id,
            filmstrip=services.queue_list(conn, project_id, label),
            label_counts=services.label_counts(conn, project_id),
            active_label=label,
            threshold=services.threshold_status(conn, project_id),
            active_strategy=active_strategy,
        )

    def _log(conn, user: dict, action: str, image_id=None, project_id=None) -> None:
        """D2/US-28. Helper best-effort: registra actividad sin propagar NUNCA una
        excepcion (el log no debe tumbar una accion ya exitosa). Se llama solo tras
        un _guard exitoso, con el user de sesion."""
        try:
            services.log_activity(
                conn, user["id"], action, image_id=image_id, project_id=project_id
            )
        except Exception:
            pass

    # (3) rutas auth (NO pasan por _guard; renderizan el form con error y status 400/401).
    @app.get("/health")
    def health():
        """Healthcheck publico (sin sesion): JSON {status, version} para liveness/probes."""
        return JSONResponse({"status": "ok", "version": __version__})

    @app.get("/login", include_in_schema=False)
    def login_page(request: Request):
        """Renderiza el formulario de login."""
        return templating.render(request, "login.html")

    @app.get("/register", include_in_schema=False)
    def register_page(request: Request):
        """Renderiza el formulario de registro de un nuevo curador."""
        return templating.render(request, "register.html")

    @app.post("/register", include_in_schema=False)
    def register_action(
        request: Request,
        conn=Depends(get_conn),
        email: str = Form(""),
        password: str = Form(""),
    ):
        """Crea el usuario; en exito inicia sesion y redirige, sino re-renderiza con error."""
        try:
            user = auth.create_user(conn, email, password)
        except services.DomainError as e:
            messages = {
                "email_exists": "El email ya esta registrado.",
                "password_too_short": "La contrasena debe tener al menos 6 caracteres.",
            }
            return templating.render(
                request,
                "register.html",
                status_code=400,
                email=email,
                error=messages.get(e.code, e.code),
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
        """Autentica credenciales; en exito inicia sesion y redirige, sino re-renderiza con error 401."""
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
        """Limpia la sesion y redirige a /login."""
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    # (4) rutas proyectos (D): home, crear, detalle.
    @app.get("/", include_in_schema=False)
    def home(request: Request, user=Depends(require_user), conn=Depends(get_conn)):
        """Home: lista los proyectos del usuario con su progreso y un flash opcional."""
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
        """Crea un proyecto del usuario, siembra su dataset si existe y redirige al detalle."""
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
        """Detalle de un proyecto propio (404 si ajeno) con su progreso."""
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
        """Pagina de curado: proxima imagen, filmstrip, conteos por etiqueta y progreso."""
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
            label_counts=services.label_counts(conn, project_id),
            active_label=None,
            progress=services.progress(conn, project_id),
            project_id=project_id,
        )

    @app.get("/projects/{project_id}/queue", include_in_schema=False)
    def queue_fragment(
        project_id: int, request: Request,
        label: str | None = None, strategy: str | None = None,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        """Fragmento HTMX de la cola: proxima imagen + filmstrip (filtro/estrategia opcionales)."""
        # US-17: query param `label` opcional filtra el filmstrip por suggested_label.
        # A1: query param `strategy` opcional reordena SOLO la proxima imagen
        # (queue_next); se valida en {uncertainty, random, sequential} (sino uncertainty).
        _owned_project(conn, project_id, user)
        return _render_next_card(
            request, conn, project_id, label, strategy=_norm_strategy(strategy)
        )

    @app.post("/images/{image_id}/validate", include_in_schema=False)
    def validate(
        image_id: int, request: Request, label: str = Form(""),
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        """Valida una imagen propia con la etiqueta dada, la registra y auto-avanza la cola."""
        img = _guard(services.get_image, conn, image_id)
        _owned_project(conn, img["project_id"], user)
        _guard(services.validate_image, conn, image_id, label)
        _log(conn, user, "validate", image_id=image_id, project_id=img["project_id"])
        return _render_next_card(request, conn, img["project_id"])

    @app.post("/images/{image_id}/reject", include_in_schema=False)
    def reject(
        image_id: int, request: Request, reason: str = Form(""),
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        """Rechaza una imagen propia con motivo, la registra y auto-avanza la cola."""
        img = _guard(services.get_image, conn, image_id)
        _owned_project(conn, img["project_id"], user)
        _guard(services.reject_image, conn, image_id, reason)
        _log(conn, user, "reject", image_id=image_id, project_id=img["project_id"])
        return _render_next_card(request, conn, img["project_id"])

    @app.post("/images/{image_id}/unreject", include_in_schema=False)
    def unreject(
        image_id: int, request: Request,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        """Revierte el rechazo de una imagen propia (vuelve a pendiente) y auto-avanza la cola."""
        img = _guard(services.get_image, conn, image_id)
        _owned_project(conn, img["project_id"], user)
        _guard(services.unreject_image, conn, image_id)
        _log(conn, user, "unreject", image_id=image_id, project_id=img["project_id"])
        return _render_next_card(request, conn, img["project_id"])

    @app.get("/progress", include_in_schema=False)
    def get_progress(
        project_id: int, user=Depends(require_user), conn=Depends(get_conn),
    ):
        """Devuelve el progreso (JSON) de un proyecto propio."""
        _owned_project(conn, project_id, user)
        return services.progress(conn, project_id)

    # (6) rutas AL + analytics (F).
    @app.post("/projects/{project_id}/retrain", include_in_schema=False)
    def retrain(
        project_id: int, request: Request,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        """Simula un re-entrenamiento del proyecto y devuelve un toast con el resultado (D13)."""
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

    @app.post("/projects/{project_id}/bulk-validate", include_in_schema=False)
    def bulk_validate_action(
        project_id: int, request: Request,
        ids: list[str] = Form(default=[]),
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        """C2/P2. Aprueba pendientes en lote confirmando la sugerencia del modelo.

        Sin `ids` en el form: el server arma la lista de pendientes PROPIAS con
        confidence>=0.9 (el boton "aprobar pendientes >90%"). Con `ids`: FIX IDOR,
        se filtran al proyecto (WHERE project_id=? AND id IN(...)) ANTES de validar,
        asi un id ajeno nunca pasa a bulk_validate. Devuelve un toast "N aprobadas"."""
        _owned_project(conn, project_id, user)
        if ids:
            # Solo los ids que pertenecen a este proyecto sobreviven (IDOR).
            wanted = []
            for raw in ids:
                try:
                    wanted.append(int(raw))
                except (TypeError, ValueError):
                    continue
            owned_ids = []
            if wanted:
                placeholders = ",".join("?" for _ in wanted)
                rows = conn.execute(
                    f"SELECT id FROM images WHERE project_id = ? AND id IN ({placeholders})",
                    (project_id, *wanted),
                ).fetchall()
                owned_ids = [r["id"] for r in rows]
        else:
            # Boton ">90%": pendientes propias de alta confianza.
            rows = conn.execute(
                "SELECT id FROM images WHERE project_id = ? AND status = 'pending' "
                "AND confidence >= 0.9 ORDER BY id ASC",
                (project_id,),
            ).fetchall()
            owned_ids = [r["id"] for r in rows]

        n = services.bulk_validate(conn, owned_ids)
        for iid in owned_ids:
            _log(conn, user, "validate", image_id=iid, project_id=project_id)
        return templating.render(
            request, "partials/toast.html", kind="success", message=f"{n} aprobadas"
        )

    @app.get("/projects/{project_id}/analytics", include_in_schema=False)
    def analytics_page(
        project_id: int, request: Request,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        """Analytics del proyecto: concordancia, distribucion, ciclos AL, calidad y salud."""
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
            # US-16: historial de ciclos AL (cronologico ascendente).
            cycles=services.list_cycles(conn, project_id),
            # B3: contexto de calidad/A-B/salud. Los 5 servicios son seguros con 0
            # validadas (P1): nunca lanzan, devuelven el branch vacio/neutro.
            conflicts=services.conflicts(conn, project_id),
            confusion=services.confusion_matrix(conn, project_id),
            quality=services.quality_metrics(conn, project_id),
            ab=services.ab_summary(conn, project_id),
            health=services.dataset_health(conn, project_id),
        )

    # (7) export del dataset curado (US-23). Ambos protegidos por _owned_project.
    _EXPORT_COLUMNS = [
        "filename",
        "final_label",
        "suggested_label",
        "confidence",
        "validated_at",
    ]

    @app.get("/projects/{project_id}/export.csv", include_in_schema=False)
    def export_csv(
        project_id: int,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        """Exporta el dataset curado del proyecto como CSV adjunto (US-23)."""
        project = _owned_project(conn, project_id, user)
        rows = services.export_rows(conn, project_id)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_EXPORT_COLUMNS)
        writer.writeheader()
        for r in rows:
            writer.writerow({c: r[c] for c in _EXPORT_COLUMNS})
        filename = f"pacusam-proyecto-{project['id']}-dataset.csv"
        return Response(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/projects/{project_id}/export.json", include_in_schema=False)
    def export_json(
        project_id: int,
        user=Depends(require_user), conn=Depends(get_conn),
    ):
        """Exporta el dataset curado del proyecto como JSON (rows + summary) (US-23)."""
        _owned_project(conn, project_id, user)
        return JSONResponse(
            {
                "rows": services.export_rows(conn, project_id),
                "summary": services.export_summary(conn, project_id),
            }
        )

    # (8) administracion (D3, read-only). Gateada por require_admin: no-auth -> 303
    # /login, curador -> 403, admin -> 200. Lista usuarios + log de actividad filtrable.
    @app.get("/admin", include_in_schema=False)
    def admin_page(
        request: Request,
        user_filter: str | None = Query(default=None, alias="user"),
        action: str | None = None,
        user=Depends(require_admin), conn=Depends(get_conn),
    ):
        """Panel admin (read-only): lista usuarios y el log de actividad filtrable (D3)."""
        users = [
            {"id": r["id"], "email": r["email"], "role": r["role"]}
            for r in conn.execute(
                "SELECT id, email, role FROM users ORDER BY id ASC"
            ).fetchall()
        ]
        # Filtro opcional del log por usuario (query param `user`) y accion (`action`).
        uid = None
        try:
            uid = int(user_filter) if user_filter not in (None, "") else None
        except (TypeError, ValueError):
            uid = None
        activity = services.list_activity(conn, user_id=uid, action=action or None)
        return templating.render(
            request,
            "admin.html",
            user=user,
            users=users,
            activity=activity,
            filter_user=user_filter or "",
            filter_action=action or "",
        )

    # (9) re-seed determinista al arrancar, sobre la MISMA conexion (D03). Corre una
    # vez en build; solo siembra si projects esta vacio (no pisa datos existentes).
    seed.seed_if_empty(app.state.conn)

    return app


app = create_app()
