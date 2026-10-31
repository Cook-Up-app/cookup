# CLAUDE.md — conventions pour Claude Code

`SPEC.md` fait foi. En cas de contradiction ou d'ambiguïté : poser la question avant de coder. Un jalon à la fois (section 12), petits commits, arrêt et compte rendu à la fin de chaque jalon, validation avant le suivant.

## Commandes

```bash
make db-up      # PostgreSQL local (docker compose, port 5433)
make dev        # serveur de développement
make test       # pytest (nécessite la base locale)
make lint       # ruff check + ruff format --check
make format     # corrige lint et format
make migrate    # migrations via DATABASE_DIRECT_URL (jamais le pooler transactionnel)
make audit      # pip-audit
make check      # lint + tests + makemigrations --check
node --test tests/js/*.test.js   # logique JavaScript (aussi lancée par pytest si node est présent)
```

Dépendances : `uv add <paquet>` (jamais pip). Réglages : `config.settings.local` (défaut de `manage.py`), `config.settings.production` (défaut de `wsgi.py`).

## Décisions tranchées (SPEC section 13)

- Q4 : Marmiton = import par URL + recherche automatique, sous réserve de la vérification section 14 (`docs/sources.md`) ; désactivation immédiate si interdit ou blocage systématique.
- Q5 : Cookeo = pages publiques moulinex.fr uniquement, aucune connexion à My Moulinex.
- Q14 : domaine `.vercel.app` de production du projet, jamais l'URL d'un déploiement, jamais renommé (les passkeys y sont liées).
- **Assouplissements décidés après M1** (priment sur SPEC.md sections 2, 5 et 13-Q19) : usage seul possible, foyer créé automatiquement (4 portions), invitations facultatives ; MFA obligatoire seulement pour les administrateurs (staff ou propriétaire de foyer), facultative pour les simples membres ; aucune révocation d'accès liée au temps (session d'un an prolongée à chaque requête, invitations sans expiration, `INVITATION_TTL_DAYS=0`). Restent en vigueur : usage unique des invitations, révocation manuelle, réauthentification pour les actions sensibles.
- **Inscription libre (après la refonte front-end)** : `/inscription` ouverte (`SIGNUP_OPEN`), chaque inscrit a son foyer ; MFA obligatoire seulement pour `is_staff`/`is_superuser` (le rôle propriétaire de foyer n'est plus administrateur). Primé sur SPEC.md section 2 et sur l'assouplissement précédent. Reste à faire : e-mail (réinitialisation, vérification).
- Les autres questions appliquent leur défaut (foyer 2–6 personnes ; déjeuner + dîner ; pas de suivi nutritionnel ; HTMX + Alpine ; Resend ou Brevo ; sauvegarde hebdomadaire ; MFA obligatoire ; le propriétaire gère convives, allergies, invitations).

## Front-end (après refonte)

CSS maison dans `static/css/`, aucun style ou script en ligne. Navigation définie une seule fois dans `apps/core/navigation.py`. Nouveau formulaire : champs rendus par `as_field_group`. Étape d'assistant : décorateur `@step` dans `apps/onboarding/steps.py`. `seed_demo` et `/dev/connexion/<profil>` sont réservés au local.

## Règles de la section 14

- Code en anglais, textes d'interface en français via `gettext`, documentation en français. Python typé.
- Chaque dépendance : une ligne dans `docs/dependencies.md`, épinglée dans `uv.lock`, publiée depuis au moins 2 semaines (`exclude-newer` dans `pyproject.toml`).
- Avant d'utiliser une API Vercel, Supabase, Django ou bibliothèque : vérifier la documentation à jour.
- **DRY** : allergènes, unités, rayons, équipements, types de repas définis une seule fois (module `core`). Filtrage par foyer uniquement via `objects.for_household(...)`. Règle des trois avant d'abstraire.
- **SOLID** : vues minces ; logique dans `services.py` et dans le moteur pur ; sources et critères de score via registre ; contrats `Searchable`/`Fetchable`/`Parsable` ; dépendances injectées (dépôt, horloge, aléa).
- **Clean code** : fonctions ~20 lignes, complexité ≤ 10 (C901), modules < 300 lignes, pas de nombres magiques, commentaires = pourquoi, exceptions métier explicites, jamais de `except Exception` nu.
- **Sécurité** : validation à la frontière, ORM paramétré, refus par défaut (chaque vue déclare son accès), aucune donnée sensible dans les logs, règles ruff `S` bloquantes, `pip-audit`.
- **Performance** : pas de N+1 (`assertNumQueries`), ≤ 15 requêtes SQL/page, semaine de menus < 2 s, imports paresseux.
- Tests d'abord pour `planner` et `shopping` (couverture ≥ 85 %), tests de sécurité pour comptes, foyers, import.
- Fin de jalon : tests verts, ruff propre, aucune migration manquante, auto-critique (duplications, entorses SOLID, dettes), README à jour, liste des écarts.

## Interdits

Rétro-ingénierie My Moulinex ou identifiants tiers ; scraping pendant la génération d'un menu ; désactiver CSRF, CSP ou MFA ; secret dans le dépôt ; `eval` ; exposer des tables via la Data API Supabase ; fonctionnalité hors périmètre sans accord. Ne jamais contourner une protection anti-robots ; `User-Agent` honnête, 1 requête/s.

## Pièges serverless / base de données

- Pas d'état en mémoire ni de disque persistant ; compteurs de limitation de débit dans `DatabaseCache`, pas en cache local.
- Pooler transactionnel (6543) pour l'application : `DISABLE_SERVER_SIDE_CURSORS`, `CONN_MAX_AGE=0`, `prepare_threshold=None` (voir `database_config`). Migrations par connexion directe ou pooler session.
- Django 6.1 exige PostgreSQL 15 ou plus.
- `django.contrib.auth`/`admin` ne sont volontairement pas installés avant M1 (le modèle utilisateur personnalisé doit précéder la première migration d'`auth`).
