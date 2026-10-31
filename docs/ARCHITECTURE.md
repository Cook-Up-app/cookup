# Architecture

Un projet Django unique, déployé comme une fonction Vercel (`config/wsgi.py`), PostgreSQL Supabase via le pooler transactionnel. Voir `SPEC.md` sections 3 à 5.

## État après M0

- `config/settings/{base,local,production}.py` : réglages communs, développement, production (HSTS, cookies `__Host-`, SSL redirect, WhiteNoise manifest).
- `apps/core` : `/sante` (état + base), `/internal/cron/daily` (Bearer `CRON_SECRET`, comparaison en temps constant, maintien de la base active), page d'accueil provisoire, middleware `Permissions-Policy`, lecture typée de l'environnement.
- Sécurité : CSP native Django 6.1 (`SECURE_CSP`, sans `unsafe-inline`/`unsafe-eval`), `X-Frame-Options`, `Referrer-Policy`, `nosniff`.
- `vercel.json` : région `cdg1`, `maxDuration` 60 s (Hobby : 300 s max, vérifié), cron quotidien 05:00.

## État après M3

- **Moteur** (`apps/planner/engine/`, Python pur, sans Django) : `rules` (contraintes dures, une fonction par règle, registre `RULES`), `criteria` (7 critères de score enregistrés : goûts 30, notes 15, fraîcheur 20, diversité 15, anti-gaspillage 10, budget 5, saison 5), `selection` (créneaux les plus contraints d'abord, tirage softmax reproductible par graine, 200 essais d'amélioration), `planning` (mode Cookeo/mixte par créneau, jours « restes »), `failure` (rapport chiffré des contraintes qui bloquent).
- **Sécurité alimentaire** : allergie stricte = exclusion totale ; **toute recette dont un ingrédient est inconnu, à vérifier ou aux allergènes non confirmés est écartée dès qu'une allergie ou un régime existe** (échec côté sûr). Les intolérances et aliments à éviter baissent le score sans exclure.
- **Frontière** (`loading`, `services`) : une requête par table pour charger le catalogue, conversion en objets du moteur ; le remplacement d'un repas est **revalidé** par les règles dures avant d'être appliqué.
- **Données** : `MenuPlan` (paramètres figés, graine), `MenuSlot` (verrouillé, hors maison, restes, explication), `HouseholdSettings`, `TastePreference` ; `Ingredient.diet_flags` et `protein` dérivés par `catalog.traits`.
- **Écarts** : formulaires classiques avec redirection, sans HTMX (aucune bibliothèque téléchargée) ; pas encore de déplacement/duplication d'un repas ; invités ponctuels au niveau du menu, pas du repas.

## État après M2

- **Catalogue** (`apps/catalog`, partagé entre foyers) : `Ingredient` (nom canonique, rayon, allergènes, `allergens_reviewed`), `Recipe` (empreinte unique, `search_text` replié sans accents + `search_vector` français, index GIN et trigrammes), `RecipeIngredient` (texte brut toujours conservé), `RecipeEquipment`, `RecipeFeedback` (par foyer). Les ingrédients et recettes de départ se chargent par `make seed` (`seed_catalog`, idempotent).
- **Normalisation** (`text`, `normalization`, `matching`, fonctions pures) : quantité, unité (table unique `core.units`), nom ; rattachement exact, puis par inclusion (marqué « à vérifier » si un mot inconnu reste), puis similarité `pg_trgm`. Rien n'est deviné : l'inconnu garde son texte brut et un drapeau.
- **Sources** (`apps/sources`) : contrats `Searchable`/`Fetchable`/`Parsable`, registre, `PoliteFetcher` (liste blanche, SSRF avec contrôle de l'adresse réellement jointe, robots.txt avec jokers, débit en base, taille et durée plafonnées, redirections revalidées), `UrlImportSource`, `MarmitonSource`, file `ImportJob`, tâche hebdomadaire.
- **Écarts** : pas d'extension `unaccent` (repliement fait en Python, de façon identique à l'index et à la requête) ; pas de `loaddata` mais une commande de chargement.

## État après M1

- **Authentification** : `accounts.User` (UUID, e-mail unique insensible à la casse), Argon2id, allauth (sessions, TOTP, passkeys, codes de récupération, réauthentification). Inscription fermée (`ClosedAccountAdapter`).
- **Refus par défaut** : `AccessPolicyMiddleware` (dernier de la pile, ses redirections traversent CSP et en-têtes) exige une session sur toute route absente de `PUBLIC_URL_NAMES`. La MFA enrôlée (TOTP ou passkey ; les codes de récupération seuls ne comptent pas) n'est exigée que des administrateurs (`mfa_required` : staff ou propriétaire de foyer) ; un simple membre qui l'active se la voit demander à la connexion.
- **Foyer automatique** : `ensure_household` crée « Mon foyer » (4 portions) au premier passage ; les invitations sont facultatives et n'expirent pas par défaut. Sessions d'un an, prolongées à chaque requête.
- **Foyers** (`apps/households`) : `Household`, `Membership` (propriétaire/membre), `Invitation` (jeton haché, 7 jours, usage unique), `Diner`, `DinerRestriction`, `Equipment`, `HouseholdEquipment`. Tout accès privé passe par `objects.for_household(...)` (`core.querysets`). Les vues utilisent `household_required` / `owner_required` ; une ressource d'un autre foyer répond 404.
- **Sans e-mail** : le propriétaire génère les liens d'invitation et de réinitialisation (`/foyer/`), affichés une seule fois ; la réinitialisation exige une réauthentification récente, comme le retrait d'un membre.
- **Limitation de débit** : compteurs allauth dans `DatabaseCache` (table `django_cache`, créée par `core.0001`), partagés entre instances serverless.
- **RLS** : `post_migrate` (`core.apps`) active Row Level Security sans politique sur toutes les tables du schéma `public`, y compris celles des jalons suivants.
- **Administration** : montée sous `ADMIN_PATH` seulement (vide en production), connexion via allauth donc MFA incluse.
