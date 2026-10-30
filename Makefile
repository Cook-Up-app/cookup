# Les variables de .env (format KEY=valeur, sans guillemets) sont exportées.
-include .env
export

.PHONY: dev test lint format migrate db-up db-down audit check

db-up:
	docker compose up -d db

db-down:
	docker compose down

dev: db-up
	uv run python manage.py runserver

test: db-up
	uv run pytest

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

# Migrations via la connexion directe (ou pooler en mode session), jamais le pooler transactionnel.
migrate:
	DATABASE_URL=$${DATABASE_DIRECT_URL:-$$DATABASE_URL} uv run python manage.py migrate

audit:
	uv run pip-audit

check: lint test
	uv run python manage.py makemigrations --check --dry-run
