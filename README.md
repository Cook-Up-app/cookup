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

## Inscription libre

`/inscription` : toute personne peut créer un compte (prénom, e-mail, mot de passe) et obtient **son propre foyer**, sans double authentification. Les invitations restent disponibles pour ajouter quelqu'un à un foyer existant. La double authentification n'est obligatoire que pour les administrateurs de l'application (`is_staff`). Fermer les inscriptions : `SIGNUP_OPEN=false`. Limite : 5 inscriptions par heure et par IP (compteur en base ; en production, IP lue dans `x-vercel-forwarded-for`). Pas encore d'e-mail : un mot de passe oublié se traite depuis l'administration.

## Refonte du front-end

Thème « crème et vert herbe » en CSS maison (`static/css/`, jetons dans `tokens.css`), clair et sombre automatiques. Navigation : barre du bas sur téléphone, menu latéral dès 1024 px (définie une seule fois dans `apps/core/navigation.py`). À la création d'un foyer, un assistant (`/bienvenue/`) pose les questions une par une ; il se relance depuis Préférences (« Refaire l'assistant »).

```bash
make db-up && make migrate   # migration 0006 : date de fin de l'assistant
make dev
```

Pour voir l'interface avec des données : `uv run python manage.py seed_demo` (DEBUG uniquement), puis `/dev/connexion/proprietaire` (route de développement, absente en production). Les photos des sources s'affichent grâce à `SOURCES_IMAGE_DOMAINS` (CSP `img-src`).

## Mise à jour après M6

```bash
make migrate   # ajoute l'horodatage des cases cochées (synchronisation hors ligne)
```

Installer l'application : sur téléphone, « Ajouter à l'écran d'accueil ». La liste de courses et les recettes ouvertes fonctionnent ensuite sans réseau. Secrets GitHub facultatifs pour la sauvegarde : `BACKUP_DATABASE_URL`, `BACKUP_PASSPHRASE` (voir `docs/operations.md`).

## Mise à jour après M4

```bash
make migrate   # listes de courses, placard, conditionnements, ordre des rayons
make seed      # conditionnements, densités et produits de base du catalogue (idempotent)
```

Les courses s'ouvrent depuis un menu (`/courses/<menu>/`) ; le placard est sur `/foyer/placard/`.

## Mise à jour après M3

```bash
make migrate   # nouvelles tables (réglages, goûts, menus) et traits d'ingrédients
make seed      # recalcule régimes et protéines, renormalise les recettes existantes (idempotent)
```

Ensuite : `/foyer/preferences/` (réglages et poids du moteur), `/foyer/convives/<id>/gouts`, puis `/menus/nouveau`.

Le domaine `.vercel.app` de production ne doit jamais être renommé (passkeys, M1).

## Écarts connus par rapport à la spec

Voir le compte rendu de jalon.
