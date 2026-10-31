#!/usr/bin/env bash
# Sauvegarde chiffrée de la base : pg_dump (format custom) puis AES-256 protégé par une phrase secrète.
#
# Variables : BACKUP_DATABASE_URL (connexion directe ou pooler en mode session), BACKUP_PASSPHRASE,
#             BACKUP_OUTPUT (fichier de sortie, défaut backup.dump.enc),
#             PG_DUMP (commande, défaut « pg_dump » ; en CI : « docker run --rm -i postgres:17-alpine pg_dump »).
# Restauration : scripts/restore.sh (voir docs/operations.md).
set -euo pipefail

: "${BACKUP_DATABASE_URL:?BACKUP_DATABASE_URL est obligatoire}"
: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE est obligatoire}"
OUTPUT="${BACKUP_OUTPUT:-backup.dump.enc}"
PG_DUMP="${PG_DUMP:-pg_dump}"

# Schéma public seulement, sans propriétaires ni droits (propres à Supabase, inutiles à la restauration).
# La phrase secrète passe par l'environnement, jamais par la ligne de commande.
# shellcheck disable=SC2086
$PG_DUMP --format=custom --schema=public --no-owner --no-privileges "$BACKUP_DATABASE_URL" \
  | openssl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt -pass env:BACKUP_PASSPHRASE -out "$OUTPUT"

test -s "$OUTPUT" || { echo "Sauvegarde vide : échec." >&2; exit 1; }
echo "Sauvegarde écrite : $OUTPUT ($(wc -c < "$OUTPUT") octets, sha256 $(shasum -a 256 "$OUTPUT" | cut -d' ' -f1))"
