"""Unit tests de seed.py (CAPA 1 — backend logico).

Idempotencia probada con un directorio de datasets temporal (monkeypatch del
path de datasets) para no depender de imagenes reales en disco.
"""
from __future__ import annotations

import json

import pytest

from pacusam import auth, db, seed, services


@pytest.fixture
def tmp_datasets(tmp_path, monkeypatch):
    """Crea static/datasets/1 y /2 temporales con algunos .jpeg y apunta seed alli."""
    d1 = tmp_path / "1"
    d2 = tmp_path / "2"
    d1.mkdir(parents=True)
    d2.mkdir(parents=True)
    for i in range(3):
        (d1 / f"rx_{i:04d}.jpeg").write_bytes(b"\xff\xd8\xff\xe0jpeg")
    for i in range(4):
        (d2 / f"bccd_{i:04d}.jpeg").write_bytes(b"\xff\xd8\xff\xe0jpeg")
    monkeypatch.setattr(seed, "_STATIC_DATASETS", tmp_path)
    return tmp_path


def test_credenciales_demo_fuente_unica():
    assert seed.DEMO_EMAIL == "demo@pacusam.org"
    assert seed.DEMO_PASSWORD == "demo1234"


def test_seed_demo_crea_usuario_demo(tmp_datasets):
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    u = conn.execute("SELECT * FROM users WHERE email = ?", (seed.DEMO_EMAIL,)).fetchone()
    assert u is not None
    assert u["password_hash"]  # hasheada, no vacia
    # credencial demo realmente autentica
    assert auth.authenticate(conn, seed.DEMO_EMAIL, seed.DEMO_PASSWORD) is not None


def test_seed_demo_crea_dos_proyectos_con_labels_y_domain(tmp_datasets):
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    projs = conn.execute("SELECT * FROM projects ORDER BY id").fetchall()
    assert len(projs) == 2
    assert projs[0]["name"] == "Radiografías de tórax"
    assert json.loads(projs[0]["labels"]) == ["NORMAL", "PNEUMONIA"]
    assert projs[0]["domain"] == "chest_xray"
    assert projs[1]["name"] == "Células sanguíneas"
    assert len(json.loads(projs[1]["labels"])) >= 3  # multiclase
    assert projs[1]["domain"] == "blood_cells"


def test_seed_demo_registra_imagenes_del_dir(tmp_datasets):
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    rows = conn.execute("SELECT * FROM images").fetchall()
    assert len(rows) == 7  # 3 del proyecto 1 + 4 del proyecto 2
    for r in rows:
        assert r["suggested_label"]
        assert 0.50 <= r["confidence"] <= 0.99
        assert r["status"] == "pending"
        assert "/static/datasets/" in r["path"]


def test_seed_demo_es_idempotente(tmp_datasets):
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    u1 = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    p1 = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    i1 = conn.execute("SELECT COUNT(*) c FROM images").fetchone()["c"]
    seed.seed_demo(conn)  # segunda corrida no duplica nada
    assert conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] == u1
    assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == p1
    assert conn.execute("SELECT COUNT(*) c FROM images").fetchone()["c"] == i1


def test_seed_demo_dir_inexistente_no_rompe(tmp_path, monkeypatch):
    # apuntar a un path sin subdirs 1/ 2/ -> no debe romper, 0 imagenes
    monkeypatch.setattr(seed, "_STATIC_DATASETS", tmp_path / "no-existe")
    conn = db.connect(":memory:")
    summary = seed.seed_demo(conn)
    assert summary["images_inserted"] == 0
    assert len(summary["projects"]) == 2


def test_seed_if_empty_siembra_cuando_no_hay_proyectos(tmp_datasets):
    conn = db.connect(":memory:")
    assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 0
    assert seed.seed_if_empty(conn) is True
    assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == 2


def test_seed_if_empty_no_siembra_si_ya_hay_proyectos(tmp_datasets):
    conn = db.connect(":memory:")
    seed.seed_demo(conn)
    before = conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"]
    assert seed.seed_if_empty(conn) is False
    assert conn.execute("SELECT COUNT(*) c FROM projects").fetchone()["c"] == before


# ---------------------------------------------------------------- datos vivos

@pytest.fixture
def big_datasets(tmp_path, monkeypatch):
    """Datasets mas grandes (20 imagenes por proyecto) para el progreso parcial."""
    for pid in (1, 2):
        d = tmp_path / str(pid)
        d.mkdir(parents=True)
        for i in range(20):
            (d / f"img_{pid}_{i:04d}.jpeg").write_bytes(b"\xff\xd8\xff\xe0jpeg")
    monkeypatch.setattr(seed, "_STATIC_DATASETS", tmp_path)
    return tmp_path


def test_seed_if_empty_deja_progreso_parcial_por_proyecto(big_datasets):
    """Cada proyecto arranca con validadas>0, rechazadas>0, ciclos>0 y pendientes>0."""
    conn = db.connect(":memory:")
    assert seed.seed_if_empty(conn) is True
    pids = [r["id"] for r in conn.execute("SELECT id FROM projects ORDER BY id").fetchall()]
    assert len(pids) == 2
    for pid in pids:
        prog = services.progress(conn, pid)
        assert prog["validated"] > 0
        assert prog["rejected"] > 0
        assert prog["pending"] > 0  # quedan imagenes por curar en la demo
        cycles = services.list_cycles(conn, pid)
        assert len(cycles) >= 2


def test_seed_datos_vivos_concordancia_alta_creible(big_datasets):
    """La concordancia sembrada queda alta y creible (no 100%): hay correcciones."""
    conn = db.connect(":memory:")
    seed.seed_if_empty(conn)
    pids = [r["id"] for r in conn.execute("SELECT id FROM projects ORDER BY id").fetchall()]
    for pid in pids:
        c = services.concordance(conn, pid)
        assert c["total_validated"] > 0
        assert 0.70 <= c["rate"] < 1.0  # alta pero con algunas correcciones


def test_seed_datos_vivos_tiempo_ahorrado_da_numeros(big_datasets):
    """Las decididas tienen shown_at/validated_at -> time_saved reporta numeros."""
    conn = db.connect(":memory:")
    seed.seed_if_empty(conn)
    pids = [r["id"] for r in conn.execute("SELECT id FROM projects ORDER BY id").fetchall()]
    for pid in pids:
        stats = services.time_saved(conn, pid)
        assert stats["decided"] > 0
        assert stats["saved_seconds"] > 0
        assert stats["saved_pct"] > 0


def test_seed_datos_vivos_ciclos_precision_creciente(big_datasets):
    """Los 2 ciclos AL de ejemplo van con precision creciente (~78 -> ~84%)."""
    conn = db.connect(":memory:")
    seed.seed_if_empty(conn)
    pids = [r["id"] for r in conn.execute("SELECT id FROM projects ORDER BY id").fetchall()]
    for pid in pids:
        cycles = services.list_cycles(conn, pid)
        assert len(cycles) >= 2
        assert cycles[0]["avg_conf_after"] < cycles[1]["avg_conf_after"]


def test_seed_datos_vivos_es_reproducible(big_datasets):
    """Re-seed determinista: mismo estado de imagenes (sin random)."""
    conn1 = db.connect(":memory:")
    seed.seed_if_empty(conn1)
    conn2 = db.connect(":memory:")
    seed.seed_if_empty(conn2)
    pids = [r["id"] for r in conn1.execute("SELECT id FROM projects ORDER BY id").fetchall()]
    for pid in pids:
        s1 = conn1.execute(
            "SELECT filename, status, final_label FROM images "
            "WHERE project_id=? ORDER BY id",
            (pid,),
        ).fetchall()
        s2 = conn2.execute(
            "SELECT filename, status, final_label FROM images "
            "WHERE project_id=? ORDER BY id",
            (pid,),
        ).fetchall()
        assert [tuple(r) for r in s1] == [tuple(r) for r in s2]


def test_seed_datos_vivos_pequeno_dataset_no_rompe(tmp_datasets):
    """Con el dataset pequeno (3 y 4 imagenes) sigue dejando estados validos."""
    conn = db.connect(":memory:")
    seed.seed_if_empty(conn)
    pids = [r["id"] for r in conn.execute("SELECT id FROM projects ORDER BY id").fetchall()]
    for pid in pids:
        prog = services.progress(conn, pid)
        assert prog["validated"] > 0
        assert prog["rejected"] > 0
        assert prog["pending"] > 0
