PY := .venv/bin/python

.PHONY: install run test reset health

install:        ## Crear venv e instalar dependencias
	python3 -m venv .venv
	$(PY) -m pip install -U pip
	$(PY) -m pip install -r requirements-dev.txt

run:            ## Levantar la app (http://127.0.0.1:8000)
	PYTHONPATH=src PACUSAM_DB=pacusam.db $(PY) -m uvicorn pacusam.api:app --reload

test:           ## Correr la suite de tests
	PYTHONPATH=src $(PY) -m pytest -q

reset:          ## Borrar la DB para forzar re-seed de los proyectos demo
	rm -f pacusam.db pacusam.db-wal pacusam.db-shm

health:         ## Chequear que el server responde
	curl -s http://127.0.0.1:8000/health
