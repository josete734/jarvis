#!/usr/bin/env bash
# Daily restic backup to the 1TB data disk /mnt/storage (disco físico distinto del
# NVMe donde vive el sistema y /srv/jarvis). Timer: 05:00.
# One-time setup:
#   sudo mkdir -p /mnt/storage/jarvis-backup/restic
#   sudo sh -c 'openssl rand -hex 32 > /root/.restic-pass && chmod 600 /root/.restic-pass'
#   sudo restic -r /mnt/storage/jarvis-backup/restic init --password-file /root/.restic-pass
set -euo pipefail

export RESTIC_REPOSITORY=${RESTIC_REPOSITORY:-/mnt/storage/jarvis-backup/restic}
export RESTIC_PASSWORD_FILE=${RESTIC_PASSWORD_FILE:-/root/.restic-pass}
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"

command -v restic >/dev/null || { echo "restic not installed (apt install restic)"; exit 1; }
mountpoint -q /mnt/storage || { echo "/mnt/storage not mounted — skipping"; exit 1; }

echo "==> postgres dump"
docker compose -f "$REPO_DIR/docker-compose.yml" exec -T postgres \
    pg_dump -U n8n n8n > /srv/jarvis/postgres-dump.sql

echo "==> restic backup"
restic backup --tag jarvis \
    /srv/jarvis/chroma \
    /srv/jarvis/mem0 \
    /srv/jarvis/n8n \
    /srv/jarvis/faces \
    /srv/jarvis/logs/events.db \
    /srv/jarvis/logs/aprendido.md \
    /srv/jarvis/postgres-dump.sql \
    "$REPO_DIR/persona" \
    "$REPO_DIR/prompts" \
    "$REPO_DIR/config" \
    "$REPO_DIR/.env"

echo "==> retention 7d/4w/6m + prune"
restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 6 --prune

echo "==> quick integrity check"
restic check --read-data-subset=2%

echo "Backup OK $(date -Is)"
# Monthly restore drill (calendar reminder): restic restore latest --target /tmp/restore-test
