from pacusam import db, services, events


def _proj(conn, threshold=2):
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('a@b.c','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at,retrain_threshold) VALUES ('P',1,'[\"X\",\"Y\"]','t',?)", (threshold,))
    return 1


def _img(conn, pid, fn, conf=0.6, sug="X"):
    cur = conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence) VALUES (?,?,?,?,?)",
                       (pid, fn, "/s/"+fn, sug, conf))
    return cur.lastrowid


def test_seed_images_publica_imagenes_subidas():
    conn = db.connect(":memory:"); pid = _proj(conn)
    got = []
    events.bus.clear(); events.bus.subscribe(events.IMAGENES_SUBIDAS, lambda p: got.append(p))
    services.seed_images(conn, pid, ["a.jpg", "b.jpg"])
    assert got and got[-1]["project_id"] == pid and got[-1]["count"] == 2
    events.bus.clear()


def test_validate_publica_imagen_validada():
    conn = db.connect(":memory:"); pid = _proj(conn, threshold=99)
    i = _img(conn, pid, "a.jpg")
    got = []
    events.bus.clear(); events.bus.subscribe(events.IMAGEN_VALIDADA, lambda p: got.append(p))
    services.validate_image(conn, i, "X")
    assert got and got[-1]["image_id"] == i and got[-1]["project_id"] == pid
    events.bus.clear()


def test_umbral_alcanzado_se_publica_al_cruzar_el_umbral():
    conn = db.connect(":memory:"); pid = _proj(conn, threshold=2)
    i1 = _img(conn, pid, "a.jpg"); i2 = _img(conn, pid, "b.jpg")
    got = []
    events.bus.clear(); events.bus.subscribe(events.UMBRAL_ALCANZADO, lambda p: got.append(p))
    services.validate_image(conn, i1, "X")   # validated=1 < 2 -> no dispara
    assert got == []
    services.validate_image(conn, i2, "X")   # validated=2 == 2 -> dispara UNA vez
    assert len(got) == 1 and got[0]["project_id"] == pid
    events.bus.clear()


def test_simulate_retrain_publica_ciclo_finalizo():
    conn = db.connect(":memory:"); pid = _proj(conn, threshold=99)
    _img(conn, pid, "a.jpg"); _img(conn, pid, "b.jpg")
    got = []
    events.bus.clear(); events.bus.subscribe(events.CICLO_FINALIZO, lambda p: got.append(p))
    services.simulate_retrain(conn, pid)
    assert got and got[-1]["project_id"] == pid
    events.bus.clear()
