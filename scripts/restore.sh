#!/usr/bin/env bash
# Restaure une sauvegarde produite par backup.sh dans une base VIDE de votre choix.
#
# Usage : BACKUP_PASSPHRASE=... RESTORE_DATABASE_URL=postgres://... scripts/restore.sh backup.dump.enc
# Ne jamais viser la base de production sans l'avoir vidée et sans comprendre ce que --clean supprime.
set -euo pipefail

: "${BACKUP_PASSPHRASE:?BACKUP_PASSPHRASE est obligatoire}"
: "${RESTORE_DATABASE_URL:?RESTORE_DATABASE_URL est obligatoire}"
INPUT="${1:?Usage : restore.sh <fichier chiffré>}"
PG_RESTORE="${PG_RESTORE:-pg_restore}"
PSQL="${PSQL:-psql}"

# Les extensions ne font pas partie de la sauvegarde : sans pg_trgm, les index de recherche échouent.
# shellcheck disable=SC2086
$PSQL "$RESTORE_DATABASE_URL" -v ON_ERROR_STOP=1 -qc "CREATE EXTENSION IF NOT EXISTS pg_trgm"

openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 -pass env:BACKUP_PASSPHRASE -in "$INPUT" \
  | $PG_RESTORE --no-owner --no-privileges --dbname "$RESTORE_DATABASE_URL" 2> >(grep -v 'schema "public" already exists' >&2 || true)
echo "Restauration terminée."
