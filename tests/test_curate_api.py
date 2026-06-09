"""Tests de endpoint del curado (CAPA 5) — la pantalla estrella.

Login con seed.DEMO_EMAIL/DEMO_PASSWORD (D02). Cubre: la cola trae el fragmento
con <img /static/datasets/> y data-image-id; validar/corregir y rechazar+motivo
actualizan progreso/excluyen; deshacer; 'Dataset curado' tras la ultima imagen
(D14, fragmento SIN data-image-id); error-paths de /progress (D21.b) y validate
de imagen inexistente (D04: 404, no 500).
"""
from __future__ import annotations

from conftest import demo_project_ids, make_project, seed_image


def _demo_user_id(conn):
    from pacusam import seed

    return conn.execute(
        "SELECT id FROM users WHERE email = ?", (seed.DEMO_EMAIL,)
    ).fetchone()["id"]


def test_queue_trae_fragmento_con_imagen_real_y_data_image_id(demo_login, conn):
    """D02/#10: GET /queue del proyecto demo devuelve la card con la imagen real
    servida desde /static/datasets/ y el data-image-id en la raiz."""
    pid = demo_project_ids(conn)[0]
    resp = demo_login.get(f"/projects/{pid}/queue", follow_redirects=False)
    assert resp.status_code == 200
    assert "data-image-id" in resp.text
    assert "/static/datasets/" in resp.text
    assert "<img" in resp.text


def test_queue_devuelve_la_imagen_mas_incierta_primero(demo_login, conn):
    """Uncertainty sampling: la card es la de menor confianza pendiente del proyecto."""
    pid = demo_project_ids(conn)[0]
    expected = conn.execute(
        "SELECT id FROM images WHERE project_id = ? AND status='pending' "
        "ORDER BY (1.0 - COALESCE(confidence,0.5)) DESC, id ASC LIMIT 1",
        (pid,),
    ).fetchone()["id"]
    resp = demo_login.get(f"/projects/{pid}/queue", follow_redirects=False)
    assert f'data-image-id="{expected}"' in resp.text


def test_validar_actualiza_progreso(demo_login, conn):
    """Validar la imagen actual -> 200, sube validated y baja pending."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Curado controlado", labels=("normal", "anomalia"))
    img_id = seed_image(conn, pid, filename="a.jpeg", confidence=0.55)
    seed_image(conn, pid, filename="b.jpeg", confidence=0.80)

    before = demo_login.get("/progress", params={"project_id": pid}).json()
    assert before["validated"] == 0
    assert before["pending"] == 2

    resp = demo_login.post(
        f"/images/{img_id}/validate", data={"label": "normal"}, follow_redirects=False
    )
    assert resp.status_code == 200

    after = demo_login.get("/progress", params={"project_id": pid}).json()
    assert after["validated"] == 1
    assert after["pending"] == 1
    assert after["percent"] > before["percent"]


def test_corregir_con_otra_etiqueta_valida(demo_login, conn):
    """Corregir = validar con una etiqueta distinta a la sugerida (debe persistir)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Correccion", labels=("normal", "anomalia"))
    img_id = seed_image(conn, pid, filename="c.jpeg", label="normal", confidence=0.51)

    resp = demo_login.post(
        f"/images/{img_id}/validate", data={"label": "anomalia"}, follow_redirects=False
    )
    assert resp.status_code == 200
    row = conn.execute(
        "SELECT status, final_label FROM images WHERE id = ?", (img_id,)
    ).fetchone()
    assert row["status"] == "validated"
    assert row["final_label"] == "anomalia"


def test_rechazar_con_motivo_excluye_de_la_cola(demo_login, conn):
    """Rechazar con motivo -> 200, la imagen queda 'rejected' y deja de ser pending."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Rechazo", labels=("normal", "anomalia"))
    img_id = seed_image(conn, pid, filename="r.jpeg", confidence=0.5)

    resp = demo_login.post(
        f"/images/{img_id}/reject",
        data={"reason": "Imagen borrosa o de baja calidad"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    after = demo_login.get("/progress", params={"project_id": pid}).json()
    assert after["rejected"] == 1
    assert after["pending"] == 0


def test_rechazar_sin_motivo_es_422(demo_login, conn):
    """reason vacio -> 422 (DomainError reason_required via _guard)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Rechazo sin motivo")
    img_id = seed_image(conn, pid, filename="r2.jpeg")
    resp = demo_login.post(
        f"/images/{img_id}/reject", data={"reason": ""}, follow_redirects=False
    )
    assert resp.status_code == 422


def test_deshacer_rechazo_devuelve_a_pendiente(demo_login, conn):
    """unreject -> 200 y la imagen vuelve a 'pending' (reaparece en la cola)."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Deshacer")
    img_id = seed_image(conn, pid, filename="u.jpeg", status="rejected")

    resp = demo_login.post(f"/images/{img_id}/unreject", follow_redirects=False)
    assert resp.status_code == 200
    row = conn.execute("SELECT status FROM images WHERE id = ?", (img_id,)).fetchone()
    assert row["status"] == "pending"


def test_cola_completa_tras_ultima_imagen(demo_login, conn):
    """D14: con UNA imagen, validarla deja la cola vacia. El fragmento de respuesta
    es la micro-celebracion: NO trae data-image-id y no es 500."""
    uid = _demo_user_id(conn)
    pid = make_project(conn, owner_id=uid, name="Una sola", labels=("normal", "anomalia"))
    img_id = seed_image(conn, pid, filename="last.jpeg", confidence=0.5)

    resp = demo_login.post(
        f"/images/{img_id}/validate", data={"label": "normal"}, follow_redirects=False
    )
    assert resp.status_code == 200
    assert "data-image-id" not in resp.text
    assert "Dataset curado" in resp.text


def test_progress_proyecto_inexistente_es_404(demo_login):
    """D21.b: /progress?project_id=9999 -> 404."""
    resp = demo_login.get("/progress", params={"project_id": 9999}, follow_redirects=False)
    assert resp.status_code == 404


def test_progress_sin_param_es_422(demo_login):
    """D21.b: /progress sin project_id -> 422 (query param requerido por FastAPI)."""
    resp = demo_login.get("/progress", follow_redirects=False)
    assert resp.status_code == 422


def test_validate_imagen_inexistente_es_404(demo_login):
    """D04: validar una imagen que no existe -> 404 (get_image via _guard), no 500."""
    resp = demo_login.post(
        "/images/999999/validate", data={"label": "normal"}, follow_redirects=False
    )
    assert resp.status_code == 404


def test_curate_imagen_de_proyecto_ajeno_es_404(client, conn):
    """IDOR sobre acciones de imagen: el usuario B no puede validar una imagen de A."""
    from conftest import make_user

    user_a = make_user(conn, email="ca@hospital.org")
    pid_a = make_project(conn, owner_id=user_a, name="A-curate", labels=("normal", "anomalia"))
    img_a = seed_image(conn, pid_a, filename="aa.jpeg")

    client.post(
        "/register",
        data={"email": "cb@hospital.org", "password": "secreto123"},
        follow_redirects=False,
    )
    resp = client.post(
        f"/images/{img_a}/validate", data={"label": "normal"}, follow_redirects=False
    )
    assert resp.status_code == 404
