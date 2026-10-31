# Architecture

Un projet Django unique, déployé comme une fonction Vercel (`config/wsgi.py`), PostgreSQL Supabase via le pooler transactionnel. Voir `SPEC.md` sections 3 à 5.

## État après M0

- `config/settings/{base,local,production}.py` : réglages communs, développement, production (HSTS, cookies `__Host-`, SSL redirect, WhiteNoise manifest).
- `apps/core` : `/sante` (état + base), `/internal/cron/daily` (Bearer `CRON_SECRET`, comparaison en temps constant, maintien de la base active), page d'accueil provisoire, middleware `Permissions-Policy`, lecture typée de l'environnement.
- Sécurité : CSP native Django 6.1 (`SECURE_CSP`, sans `unsafe-inline`/`unsafe-eval`), `X-Frame-Options`, `Referrer-Policy`, `nosniff`.
- `vercel.json` : région `cdg1`, `maxDuration` 60 s (Hobby : 300 s max, vérifié), cron quotidien 05:00.

## État après M1

- **Authentification** : `accounts.User` (UUID, e-mail unique insensible à la casse), Argon2id, allauth (sessions, TOTP, passkeys, codes de récupération, réauthentification). Inscription fermée (`ClosedAccountAdapter`).
- **Refus par défaut** : `AccessPolicyMiddleware` (dernier de la pile, ses redirections traversent CSP et en-têtes) exige une session sur toute route absente de `PUBLIC_URL_NAMES`. La MFA enrôlée (TOTP ou passkey ; les codes de récupération seuls ne comptent pas) n'est exigée que des administrateurs (`mfa_required` : staff ou propriétaire de foyer) ; un simple membre qui l'active se la voit demander à la connexion.
- **Foyer automatique** : `ensure_household` crée « Mon foyer » (4 portions) au premier passage ; les invitations sont facultatives et n'expirent pas par défaut. Sessions d'un an, prolongées à chaque requête.
- **Foyers** (`apps/households`) : `Household`, `Membership` (propriétaire/membre), `Invitation` (jeton haché, 7 jours, usage unique), `Diner`, `DinerRestriction`, `Equipment`, `HouseholdEquipment`. Tout accès privé passe par `objects.for_household(...)` (`core.querysets`). Les vues utilisent `household_required` / `owner_required` ; une ressource d'un autre foyer répond 404.
- **Sans e-mail** : le propriétaire génère les liens d'invitation et de réinitialisation (`/foyer/`), affichés une seule fois ; la réinitialisation exige une réauthentification récente, comme le retrait d'un membre.
- **Limitation de débit** : compteurs allauth dans `DatabaseCache` (table `django_cache`, créée par `core.0001`), partagés entre instances serverless.
- **RLS** : `post_migrate` (`core.apps`) active Row Level Security sans politique sur toutes les tables du schéma `public`, y compris celles des jalons suivants.
- **Administration** : montée sous `ADMIN_PATH` seulement (vide en production), connexion via allauth donc MFA incluse.
