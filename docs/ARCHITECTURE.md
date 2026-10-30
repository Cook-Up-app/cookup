# Architecture

Un projet Django unique, déployé comme une fonction Vercel (`config/wsgi.py`), PostgreSQL Supabase via le pooler transactionnel. Voir `SPEC.md` sections 3 à 5.

## État après M0

- `config/settings/{base,local,production}.py` : réglages communs, développement, production (HSTS, cookies `__Host-`, SSL redirect, WhiteNoise manifest).
- `apps/core` : `/sante` (état + base), `/internal/cron/daily` (Bearer `CRON_SECRET`, comparaison en temps constant, maintien de la base active), page d'accueil provisoire, middleware `Permissions-Policy`, lecture typée de l'environnement.
- Sécurité : CSP native Django 6.1 (`SECURE_CSP`, sans `unsafe-inline`/`unsafe-eval`), `X-Frame-Options`, `Referrer-Policy`, `nosniff`.
- `vercel.json` : région `cdg1`, `maxDuration` 60 s (Hobby : 300 s max, vérifié), cron quotidien 05:00.
