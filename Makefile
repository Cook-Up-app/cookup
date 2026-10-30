# `uv --env-file` charge .env (guillemets acceptés) ; sans .env, les variables du shell s'appliquent.
RUN = uv run $(if $(wildcard .env),--env-file .env,)

.PHONY: dev test lint format migrate db-up db-down audit check

db-up:
	docker compose up -d db

db-down:
	docker compose down

dev: db-up
	$(RUN) python manage.py runserver

test: db-up
	$(RUN) pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

# Migrations via DATABASE_DIRECT_URL (connexion directe ou pooler session), jamais le pooler transactionnel.
migrate:
	USE_DIRECT_DATABASE=1 $(RUN) python manage.py migrate

audit:
	uv run pip-audit

check: lint test
	$(RUN) python manage.py makemigrations --check --dry-run
