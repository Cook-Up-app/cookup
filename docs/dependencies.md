# Dépendances

Toutes épinglées dans `uv.lock`, publiées avant le 2026-10-17 (`exclude-newer`).

| Paquet | Rôle | Jalon |
| --- | --- | --- |
| `django` 6.1 | Framework web ; CSP native, requiert PostgreSQL 15+ | M0 |
| `psycopg[binary]` | Pilote PostgreSQL 3 | M0 |
| `whitenoise` | Fichiers statiques (local) et compression | M0 |
| `dj-database-url` | Lecture de `DATABASE_URL` | M0 |
| `pytest`, `pytest-django` (dev) | Tests | M0 |
| `ruff` (dev) | Lint, format, règles de sécurité `S` | M0 |
| `pip-audit` (dev) | Audit des vulnérabilités | M0 |
