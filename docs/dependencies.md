# Dépendances

Toutes épinglées dans `uv.lock`, publiées avant le 2026-10-17 (`exclude-newer`).

| Paquet | Rôle | Jalon |
| --- | --- | --- |
| `django` 6.1 | Framework web ; CSP native, requiert PostgreSQL 15+ | M0 |
| `psycopg[binary]` | Pilote PostgreSQL 3 | M0 |
| `whitenoise` | Fichiers statiques (local) et compression | M0 |
| `dj-database-url` | Lecture de `DATABASE_URL` | M0 |
| `django-allauth[mfa]` 65.20 | Connexion, TOTP, codes de récupération, passkeys, réauthentification, limitation de débit | M1 |
| `argon2-cffi` | Hachage Argon2id des mots de passe | M1 |
| `fido2`, `qrcode`, `cryptography` (transitives de l'extra `mfa`) | WebAuthn, QR code TOTP, chiffrement des secrets | M1 |
| `recipe-scrapers` 15.12 | Extraction JSON-LD des recettes (marmiton.org pris en charge) ; la 15.13 (18 octobre) est trop récente | M2 |
| `protego` | Lecture de robots.txt avec jokers (`*`, `$`), que `urllib.robotparser` ne gère pas | M2 |
| `nh3` | Nettoyage HTML du contenu importé avant stockage | M2 |
| `pytest`, `pytest-django` (dev) | Tests | M0 |
| `pytest-cov` (dev) | Mesure de couverture (≥ 85 % exigé sur `planner` et `shopping`) | M3 |
| `ruff` (dev) | Lint, format, règles de sécurité `S` | M0 |
| `pip-audit` (dev) | Audit des vulnérabilités | M0 |

## Exceptions à la règle des deux semaines

| Paquet | Version | Raison |
| --- | --- | --- |
| `certifi` (transitive de `pip-audit`, dev) | 2026.10.18 | Corrige PYSEC-2026-4320 ; publiée le 2026-10-18, soit moins de 2 semaines. Hors production. |
| `filelock` (transitive de `pip-audit`, dev) | 4.2.1 | Corrige 17 CVE (4.2.0 vulnérable) ; publiée le 2026-10-17. Hors production. |

Dès que ces versions auront deux semaines, l'exception peut être retirée en avançant `exclude-newer`.
