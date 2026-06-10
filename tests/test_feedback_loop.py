from fastapi.testclient import TestClient
from pacusam import db, services, events
from pacusam.api import create_app


def test_umbral_dispara_reentrenamiento_automatico(tmp_path):
    # Estilo CEP: al cruzar el umbral de validadas, se dispara un ciclo de AL
    # automaticamente (feedback loop de Pipes & Filters via Pub-Sub).
    app = create_app(db_path=str(tmp_path / "t.db"))  # registra los suscriptores
    conn = db.connect(str(tmp_path / "t.db"))
    # proyecto chico con umbral 2
    conn.execute("INSERT INTO users (email,password_hash,created_at) VALUES ('u@x.com','h','t')")
    conn.execute("INSERT INTO projects (name,owner_id,labels,created_at,retrain_threshold) VALUES ('P',1,'[\"X\"]','t',2)")
    pid = conn.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 1").fetchone()["id"]
    ids = [conn.execute("INSERT INTO images (project_id,filename,path,suggested_label,confidence) VALUES (?,?,?,?,?)",
                        (pid, f"i{i}.jpg", f"/s/i{i}.jpg", "X", 0.6)).lastrowid for i in range(2)]
    conn.commit()
    before = len(services.list_cycles(conn, pid))
    services.validate_image(conn, ids[0], "X")
    services.validate_image(conn, ids[1], "X")   # cruza umbral -> UmbralAlcanzado -> retrain
    after = len(services.list_cycles(conn, pid))
    assert after == before + 1   # se registro un ciclo automaticamente
