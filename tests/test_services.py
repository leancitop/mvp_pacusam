"""Unit tests de la capa de dominio (CAPA 1 — backend logico).

Cubre: list/create/get project, get_image, seed_images, queue_next/queue_list
(uncertainty sampling), validate (invalid_label), reject/unreject, progress,
concordance, class_distribution, simulate_retrain (+ cap D13) y tiempo ahorrado (D12).
"""
from __future__ import annotations

import json

import pytest

from pacusam import db, services
from pacusam.services import DomainError


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    c.execute(
        "INSERT INTO users (email, password_hash, created_at) "
        "VALUES ('demo@pacusam.org','h','2026-01-01T00:00:00+00:00')"
    )
    c.commit()
    return c


def _mk_user(conn, email="u@x.com"):
    cur = conn.execute(
        "INSERT INTO users (email, password_hash, created_at) VALUES (?,?,?)",
        (email, "h", "2026-01-01T00:00:00+00:00"),
    )
    conn.commit()
    return cur.lastrowid


def _mk_project(conn, owner_id=1, name="P", labels=("normal", "anomalia")):
    cur = conn.execute(
        "INSERT INTO projects (name, description, owner_id, domain, labels, created_at) "
        "VALUES (?, '', ?, 'rx', ?, '2026-01-01T00:00:00+00:00')",
        (name, owner_id, json.dumps(list(labels))),
    )
    conn.commit()
    return cur.lastrowid


def _img(conn, project_id, filename="x.dcm", label="normal", conf=0.6, status="pending"):
    cur = conn.execute(
        "INSERT INTO images (project_id, filename, path, suggested_label, confidence, status) "
        "VALUES (?,?,?,?,?,?)",
        (project_id, filename, f"/static/datasets/{project_id}/{filename}", label, conf, status),
    )
    conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------- projects

def test_list_projects_filtra_por_owner_y_deserializa_labels(conn):
    p1 = _mk_project(conn, owner_id=1, name="Mio")
    other = _mk_user(conn, "b@x.com")
    _mk_project(conn, owner_id=other, name="Ajeno")
    projs = services.list_projects(conn, 1)
    assert [p["name"] for p in projs] == ["Mio"]
    assert projs[0]["labels"] == ["normal", "anomalia"]


def test_create_project_ok(conn):
    p = services.create_project(conn, 1, "Torax 2026", "RX", "radiologia", ["normal", "anomalia"])
    assert p["id"] >= 1
    assert p["name"] == "Torax 2026"
    assert p["owner_id"] == 1
    assert p["labels"] == ["normal", "anomalia"]
    assert p["created_at"]
    assert services.list_projects(conn, 1)[0]["id"] == p["id"]


def test_create_project_name_required(conn):
    with pytest.raises(DomainError) as e:
        services.create_project(conn, 1, "   ", "d", "radiologia", ["normal"])
    assert e.value.code == "name_required"


def test_create_project_name_too_long(conn):
    with pytest.raises(DomainError) as e:
        services.create_project(conn, 1, "x" * 101, "d", "radiologia", ["normal"])
    assert e.value.code == "name_too_long"


def test_get_project_ok(conn):
    pid = _mk_project(conn)
    p = services.get_project(conn, pid)
    assert p["id"] == pid
    assert p["labels"] == ["normal", "anomalia"]


def test_get_project_not_found(conn):
    with pytest.raises(DomainError) as e:
        services.get_project(conn, 9999)
    assert e.value.code == "project_not_found"


# ---------------------------------------------------------------- images / seed

def test_get_image_ok(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid)
    img = services.get_image(conn, iid)
    assert img["id"] == iid
    assert img["project_id"] == pid


def test_get_image_not_found(conn):
    with pytest.raises(DomainError) as e:
        services.get_image(conn, 999)
    assert e.value.code == "image_not_found"


def test_seed_images_inserta_corre_classifier_y_setea_path(conn):
    pid = _mk_project(conn, labels=("NORMAL", "PNEUMONIA"))
    n = services.seed_images(conn, pid, ["rx_0001.jpeg", "rx_0002.jpeg"])
    assert n == 2
    row = conn.execute("SELECT * FROM images WHERE filename='rx_0001.jpeg'").fetchone()
    assert row["suggested_label"] in ("NORMAL", "PNEUMONIA")
    assert 0.50 <= row["confidence"] <= 0.99
    assert row["status"] == "pending"
    assert row["path"] == f"/static/datasets/{pid}/rx_0001.jpeg"


def test_seed_images_idempotente_por_project_filename(conn):
    pid = _mk_project(conn)
    services.seed_images(conn, pid, ["a.jpeg", "b.jpeg"])
    n2 = services.seed_images(conn, pid, ["a.jpeg", "b.jpeg", "c.jpeg"])
    total = conn.execute(
        "SELECT COUNT(*) c FROM images WHERE project_id=?", (pid,)
    ).fetchone()["c"]
    assert total == 3
    assert n2 == 1


def test_seed_images_proyecto_inexistente(conn):
    with pytest.raises(DomainError) as e:
        services.seed_images(conn, 9999, ["a.jpeg"])
    assert e.value.code == "project_not_found"


# ---------------------------------------------------------------- queue (AL)

def test_queue_next_devuelve_la_mas_incierta_primero(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "alta.dcm", "normal", 0.95)   # incertidumbre 0.05
    _img(conn, pid, "baja.dcm", "anomalia", 0.55)  # incertidumbre 0.45
    _img(conn, pid, "media.dcm", "normal", 0.72)  # incertidumbre 0.28
    nxt = services.queue_next(conn, pid)
    assert nxt["filename"] == "baja.dcm"
    assert nxt["uncertainty"] == 0.45
    assert nxt["remaining_pending"] == 3


def test_queue_next_ignora_no_pending(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "v.dcm", "normal", 0.55, status="validated")
    _img(conn, pid, "p.dcm", "normal", 0.80, status="pending")
    nxt = services.queue_next(conn, pid)
    assert nxt["filename"] == "p.dcm"


def test_queue_next_sin_pendientes_devuelve_none(conn):
    pid = _mk_project(conn)
    assert services.queue_next(conn, pid) is None


def test_queue_next_confidence_nula_usa_05(conn):
    """D19: COALESCE(confidence, 0.5) — una imagen con confidence NULL no rompe."""
    pid = _mk_project(conn)
    conn.execute(
        "INSERT INTO images (project_id, filename, path, suggested_label, confidence, status) "
        "VALUES (?, 'nula.dcm', '/p', 'normal', NULL, 'pending')",
        (pid,),
    )
    conn.commit()
    nxt = services.queue_next(conn, pid)
    assert nxt is not None
    assert nxt["uncertainty"] == 0.5


def test_queue_list_ordenado_por_incertidumbre_con_status(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "alta.dcm", "normal", 0.95, status="validated")   # inc 0.05
    _img(conn, pid, "baja.dcm", "anomalia", 0.55, status="pending")   # inc 0.45
    _img(conn, pid, "media.dcm", "normal", 0.70, status="rejected")   # inc 0.30
    items = services.queue_list(conn, pid)
    assert [i["filename"] for i in items] == ["baja.dcm", "media.dcm", "alta.dcm"]
    assert [i["status"] for i in items] == ["pending", "rejected", "validated"]
    assert items[0]["uncertainty"] == 0.45
    assert items[0]["path"].endswith("baja.dcm")


def test_queue_list_aisla_por_proyecto(conn):
    p1 = _mk_project(conn, name="P1")
    p2 = _mk_project(conn, name="P2")
    _img(conn, p1, "a.dcm", "normal", 0.80)
    _img(conn, p2, "b.dcm", "normal", 0.80)
    items = services.queue_list(conn, p1)
    assert [i["filename"] for i in items] == ["a.dcm"]


# ---------------------------------------------------------------- validate

def test_validate_confirma_la_sugerencia(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid, label="normal")
    out = services.validate_image(conn, iid, "normal")
    assert out["status"] == "validated"
    assert out["final_label"] == "normal"
    assert out["validated_at"]
    row = conn.execute("SELECT status, final_label FROM images WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "validated" and row["final_label"] == "normal"


def test_validate_corrige_a_otra_label_del_proyecto(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid, label="normal")
    out = services.validate_image(conn, iid, "anomalia")
    assert out["final_label"] == "anomalia"


def test_validate_rechaza_label_fuera_del_proyecto(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid)
    with pytest.raises(DomainError) as e:
        services.validate_image(conn, iid, "fractura")
    assert e.value.code == "invalid_label"


def test_validate_label_requerida(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid)
    with pytest.raises(DomainError) as e:
        services.validate_image(conn, iid, "   ")
    assert e.value.code == "label_required"


def test_validate_imagen_inexistente(conn):
    with pytest.raises(DomainError) as e:
        services.validate_image(conn, 999, "normal")
    assert e.value.code == "image_not_found"


def test_validate_es_idempotente(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid)
    services.validate_image(conn, iid, "normal")
    out = services.validate_image(conn, iid, "anomalia")  # re-validar cambia label
    assert out["final_label"] == "anomalia"


# ---------------------------------------------------------------- reject / unreject

def test_reject_setea_status_y_motivo(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid)
    out = services.reject_image(conn, iid, "imagen borrosa")
    assert out["status"] == "rejected"
    assert out["reject_reason"] == "imagen borrosa"
    row = conn.execute("SELECT status, reject_reason FROM images WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "rejected" and row["reject_reason"] == "imagen borrosa"


def test_reject_motivo_requerido(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid)
    with pytest.raises(DomainError) as e:
        services.reject_image(conn, iid, "  ")
    assert e.value.code == "reason_required"


def test_reject_imagen_inexistente(conn):
    with pytest.raises(DomainError) as e:
        services.reject_image(conn, 999, "motivo")
    assert e.value.code == "image_not_found"


def test_reject_excluye_de_la_cola(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid, filename="rej.dcm", conf=0.55)
    _img(conn, pid, filename="keep.dcm", conf=0.60)
    services.reject_image(conn, iid, "motivo")
    nxt = services.queue_next(conn, pid)
    assert nxt["filename"] == "keep.dcm"


def test_unreject_vuelve_a_pending(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid)
    services.reject_image(conn, iid, "borrosa")
    out = services.unreject_image(conn, iid)
    assert out["status"] == "pending"
    row = conn.execute("SELECT status, reject_reason FROM images WHERE id=?", (iid,)).fetchone()
    assert row["status"] == "pending" and row["reject_reason"] is None


def test_unreject_reaparece_en_la_cola(conn):
    pid = _mk_project(conn)
    iid = _img(conn, pid, conf=0.55)
    services.reject_image(conn, iid, "borrosa")
    assert services.queue_next(conn, pid) is None
    services.unreject_image(conn, iid)
    assert services.queue_next(conn, pid)["id"] == iid


def test_unreject_imagen_inexistente(conn):
    with pytest.raises(DomainError) as e:
        services.unreject_image(conn, 999)
    assert e.value.code == "image_not_found"


# ---------------------------------------------------------------- progress

def test_progress_cuenta_por_estado_y_porcentaje(conn):
    pid = _mk_project(conn)
    a = _img(conn, pid, filename="a.dcm")
    b = _img(conn, pid, filename="b.dcm")
    _img(conn, pid, filename="c.dcm")
    _img(conn, pid, filename="d.dcm")
    services.validate_image(conn, a, "normal")
    services.reject_image(conn, b, "borrosa")
    prog = services.progress(conn, pid)
    assert prog["total"] == 4
    assert prog["validated"] == 1
    assert prog["rejected"] == 1
    assert prog["pending"] == 2
    assert prog["percent"] == 50.0  # (1 validated + 1 rejected) / 4


def test_progress_proyecto_vacio(conn):
    pid = _mk_project(conn)
    assert services.progress(conn, pid) == {
        "total": 0, "validated": 0, "rejected": 0, "pending": 0, "percent": 0.0,
    }


# ---------------------------------------------------------------- analytics

def test_concordance_rate_con_set_fijo(conn):
    pid = _mk_project(conn)
    i1 = _img(conn, pid, "a.dcm", "normal", 0.9)
    i2 = _img(conn, pid, "b.dcm", "normal", 0.8)
    i3 = _img(conn, pid, "c.dcm", "anomalia", 0.7)
    i4 = _img(conn, pid, "d.dcm", "anomalia", 0.6)
    services.validate_image(conn, i1, "normal")     # agree
    services.validate_image(conn, i2, "anomalia")   # disagree
    services.validate_image(conn, i3, "anomalia")   # agree
    services.validate_image(conn, i4, "normal")     # disagree
    c = services.concordance(conn, pid)
    assert c["total_validated"] == 4
    assert c["agreed"] == 2
    assert c["rate"] == 0.5


def test_concordance_sin_validadas_rate_cero(conn):
    pid = _mk_project(conn)
    _img(conn, pid, "x.dcm", "normal", 0.9)  # pending
    assert services.concordance(conn, pid) == {"agreed": 0, "total_validated": 0, "rate": 0.0}


def test_class_distribution_cuenta_y_porcentajes(conn):
    pid = _mk_project(conn)
    ids = [_img(conn, pid, f"n{i}.dcm", "normal", 0.9) for i in range(3)]
    a1 = _img(conn, pid, "an1.dcm", "anomalia", 0.8)
    rej = _img(conn, pid, "rej.dcm", "normal", 0.7)
    _img(conn, pid, "pend.dcm", "normal", 0.6)  # pending, no cuenta
    for i in ids:
        services.validate_image(conn, i, "normal")
    services.validate_image(conn, a1, "anomalia")
    services.reject_image(conn, rej, "mala calidad")
    dist = services.class_distribution(conn, pid)
    assert dist == [
        {"label": "normal", "count": 3, "percent": 75.0},
        {"label": "anomalia", "count": 1, "percent": 25.0},
    ]


def test_class_distribution_vacia(conn):
    pid = _mk_project(conn)
    assert services.class_distribution(conn, pid) == []


def test_simulate_retrain_sube_confidencias_y_reporta_mejora(conn):
    pid = _mk_project(conn)
    p1 = _img(conn, pid, "p1.dcm", "normal", 0.50)
    p2 = _img(conn, pid, "p2.dcm", "anomalia", 0.60)
    v1 = _img(conn, pid, "v1.dcm", "normal", 0.90)
    services.validate_image(conn, v1, "normal")
    before_avg = (0.50 + 0.60) / 2  # 0.55
    res = services.simulate_retrain(conn, pid)
    assert res["improvement_pct"] > 0
    assert res["new_avg_confidence"] > before_avg
    assert res["new_avg_confidence"] <= 1.0
    assert res["status"] != "calibrado"
    rows = conn.execute(
        "SELECT id, confidence, status FROM images WHERE id IN (?,?)", (p1, p2)
    ).fetchall()
    by_id = {r["id"]: r for r in rows}
    assert by_id[p1]["confidence"] > 0.50 and by_id[p1]["status"] == "pending"
    assert by_id[p2]["confidence"] > 0.60 and by_id[p2]["status"] == "pending"
    # piso de incertidumbre: no sube por encima de 0.95
    assert by_id[p1]["confidence"] <= 0.95
    assert by_id[p2]["confidence"] <= 0.95
    # La validada no se toco.
    val = conn.execute("SELECT confidence FROM images WHERE id=?", (v1,)).fetchone()
    assert val["confidence"] == 0.90


def test_simulate_retrain_sin_pending_no_mejora(conn):
    pid = _mk_project(conn)
    res = services.simulate_retrain(conn, pid)
    assert res["improvement_pct"] == 0.0
    assert res["new_avg_confidence"] == 0.0
    assert res["status"] == "calibrado"


def test_simulate_retrain_cap_cuando_ya_calibrado(conn):
    """D13: si avg pending > 0.9 (o mejora < 0.5%), marca 'calibrado' y no rompe el orden."""
    pid = _mk_project(conn)
    _img(conn, pid, "p1.dcm", "normal", 0.93)
    _img(conn, pid, "p2.dcm", "anomalia", 0.94)
    res = services.simulate_retrain(conn, pid)
    assert res["status"] == "calibrado"


# ---------------------------------------------------------------- tiempo ahorrado (D12)

def test_tiempo_ahorrado_con_mock_3s_vs_30s(conn):
    pid = _mk_project(conn)
    a = _img(conn, pid, "a.dcm")
    b = _img(conn, pid, "b.dcm")
    services.validate_image(conn, a, "normal")
    services.reject_image(conn, b, "x")
    stats = services.time_saved(conn, pid)
    assert stats["decided"] == 2
    # mock: 3s AL vs 30s manual -> ahorro ~90% sobre 2 imagenes
    assert stats["al_seconds"] == pytest.approx(6.0)
    assert stats["manual_seconds"] == pytest.approx(60.0)
    assert stats["saved_seconds"] == pytest.approx(54.0)
    assert stats["saved_pct"] == pytest.approx(90.0)
    assert stats["saved_minutes"] >= 0


def test_tiempo_ahorrado_sin_decididas(conn):
    pid = _mk_project(conn)
    stats = services.time_saved(conn, pid)
    assert stats["decided"] == 0
    assert stats["saved_seconds"] == 0.0
    assert stats["saved_pct"] == 0.0
