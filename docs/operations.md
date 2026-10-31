# Exploitation

## Maintien de Supabase actif
Le plan Free met en pause un projet inactif 7 jours. La tâche Vercel Cron `/internal/cron/daily` (05:00) exécute une requête, purge les invitations expirées et les sessions périmées, et enregistre son passage. **Vérification** : `https://<domaine>/sante` doit répondre `"keepalive": "ok"` ; `"stale"` signifie plus de 36 h sans passage (cron désactivé, `CRON_SECRET` désaligné), `"never"` qu'il n'a jamais tourné.

## Sauvegarde hebdomadaire
Le plan Free de Supabase n'a pas de sauvegarde. Le workflow `.github/workflows/backup.yml` (dimanche 03:00 UTC, ou à la demande) exporte le schéma `public` (`pg_dump` 17, format custom), le chiffre en AES-256 (`openssl`, PBKDF2) et le conserve 90 jours comme artefact GitHub.

Secrets GitHub à créer (sans eux, le workflow s'ignore et ne fait rien) :
- `BACKUP_DATABASE_URL` : chaîne **Session pooler** ou directe de Supabase (port 5432, jamais le pooler transactionnel) ;
- `BACKUP_PASSPHRASE` : phrase secrète longue (`openssl rand -hex 32`). **Gardez-la ailleurs que dans GitHub** : sans elle, une sauvegarde est illisible.

Un artefact GitHub n'est pas un stockage privé indépendant : pour une vraie copie hors GitHub, téléchargez-en une de temps en temps ou adaptez le workflow vers un bucket privé.

### Restaurer
1. Créez une base PostgreSQL 15 ou plus **vide** (locale ou nouveau projet Supabase).
2. Téléchargez l'artefact, puis :
   ```bash
   BACKUP_PASSPHRASE='…' RESTORE_DATABASE_URL='postgres://…' scripts/restore.sh backup.dump.enc
   ```
   Le script active `pg_trgm` (les extensions ne sont pas dans la sauvegarde), déchiffre et restaure. L'avertissement « schema public already exists » est normal.
3. Vérifiez : `SELECT count(*) FROM catalog_recipe;`, puis lancez `make migrate` si le code est plus récent que la sauvegarde.

Essai réalisé le 2026-10-31 sur une base locale : 87 recettes et 213 ingrédients restaurés à l'identique, index de recherche compris, et une mauvaise phrase secrète est refusée.

## Rotation d'un secret
`CRON_SECRET` : le régénérer (`openssl rand -hex 32`), puis mettre à jour Vercel, `.env` et le secret GitHub, et redéployer. `SECRET_KEY` : placer l'ancienne valeur dans `SECRET_KEY_FALLBACKS` avant de la remplacer.

## Hors ligne (PWA)
Voir `docs/ARCHITECTURE.md` (section M6). Pour repartir de zéro sur un appareil : désinstaller l'application, ou, dans le navigateur, effacer les données du site (cela supprime la file des modifications non synchronisées).
