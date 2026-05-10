#!/usr/bin/env bash
set -euo pipefail

# Borg backup: pg_dumpall -> borg archive -> Hetzner Storage Box
# Requires: BORG_REPO, BORG_PASSPHRASE in .env or environment
# Cron: 0 3 * * * /srv/godoman/autoagent/scripts/backup.sh >> /var/log/borg-backup.log 2>&1

REPO_DIR="/srv/godoman/autoagent"
DUMP_DIR="/tmp/borg-dumps"
DATE=$(date +%Y-%m-%dT%H-%M-%S)

if [[ -f "$REPO_DIR/.env" ]]; then
  set -a
  source "$REPO_DIR/.env"
  set +a
fi

: "${BORG_REPO:?BORG_REPO must be set}"
: "${BORG_PASSPHRASE:?BORG_PASSPHRASE must be set}"
export BORG_PASSPHRASE

mkdir -p "$DUMP_DIR"

echo "==> Dumping databases ($DATE)..."
PG_CONTAINER=$(docker compose -f "$REPO_DIR/docker-compose.yml" ps -q postgres)
docker exec "$PG_CONTAINER" pg_dumpall -U "${POSTGRES_USER:-ops}" > "$DUMP_DIR/all_dbs.sql"

echo "==> Creating borg archive..."
borg create \
  --verbose \
  --stats \
  --compression lz4 \
  "${BORG_REPO}::autoagent-${DATE}" \
  "$DUMP_DIR"

echo "==> Pruning old archives..."
borg prune \
  --verbose \
  --keep-daily 7 \
  --keep-weekly 4 \
  --keep-monthly 3 \
  "${BORG_REPO}"

echo "==> Cleaning up dumps..."
rm -rf "$DUMP_DIR"

echo "==> Backup complete ($DATE)."
