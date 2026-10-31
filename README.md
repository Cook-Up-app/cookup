# Menu du jour (cookup)

Planificateur de menus et liste de courses — Django, Vercel, Supabase. Spécification : [SPEC.md](SPEC.md). Conventions : [CLAUDE.md](CLAUDE.md).

## Développement local

```bash
cp .env.example .env
make db-up      # PostgreSQL 17 (docker compose, port 5433)
make migrate
make dev        # http://localhost:8000
make test
```

Prérequis : `uv`, Docker. Python 3.13 est installé par `uv`.

## Mise en route production (M0)

1. **Supabase** : créer le projet (région européenne), désactiver l'exposition du schéma `public` dans la Data API, activer `unaccent` et `pg_trgm`. Noter la chaîne du pooler transactionnel (6543) et celle du pooler session ou directe (5432).
2. **Vercel** : importer le dépôt GitHub. Variables (Production, Preview, Development) : `DJANGO_SETTINGS_MODULE=config.settings.production`, `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` (6543, `sslmode=require`), `CRON_SECRET` (≥ 32 caractères). Protéger les déploiements de prévisualisation et les brancher sur une base distincte.
3. **Migrations** : `DATABASE_DIRECT_URL=... make migrate` (jamais pendant le build).
4. Pousser sur `main` : Vercel déploie. Vérifier `https://<domaine>/sante`.

## Premier compte propriétaire (M1)

```bash
make migrate                         # contre Supabase (DATABASE_DIRECT_URL)
USE_DIRECT_DATABASE=1 uv run --env-file .env python manage.py createsuperuser
```

Connectez-vous sur `/connexion` et activez une passkey ou un TOTP sur `/compte/securite` (obligatoire pour les administrateurs). Le foyer « Mon foyer » (4 portions) est créé automatiquement. Inviter d'autres personnes est facultatif : le lien d'invitation est affiché une seule fois et n'expire pas. Les liens de réinitialisation de mot de passe se génèrent de la même façon.

## Mise à jour après M3

```bash
make migrate   # nouvelles tables (réglages, goûts, menus) et traits d'ingrédients
make seed      # recalcule régimes et protéines, renormalise les recettes existantes (idempotent)
```

Ensuite : `/foyer/preferences/` (réglages et poids du moteur), `/foyer/convives/<id>/gouts`, puis `/menus/nouveau`.

Le domaine `.vercel.app` de production ne doit jamais être renommé (passkeys, M1).

## Écarts connus par rapport à la spec

Voir le compte rendu de jalon.
