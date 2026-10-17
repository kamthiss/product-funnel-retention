PY = .venv/bin/python
PSQL = docker compose exec -T db sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

.PHONY: setup up data load marts notebook all reset-db down

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt
	test -f .env || cp .env.example .env

up:
	docker compose up -d
	until docker compose exec -T db sh -c 'pg_isready -q -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'; do sleep 1; done

data:
	$(PY) src/generate.py
	$(PY) src/validate.py

load:
	$(PY) src/load.py

marts:
	$(PSQL) < sql/02_marts.sql
	$(PSQL) < sql/03_funnel.sql
	$(PSQL) < sql/04_retention.sql

notebook:
	.venv/bin/jupyter nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb

all: up data load marts

reset-db:
	echo 'drop schema if exists staging cascade; drop schema if exists mart cascade;' | $(PSQL)

down:
	docker compose down
