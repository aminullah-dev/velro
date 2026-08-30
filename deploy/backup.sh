#!/usr/bin/env bash
# Nightly database backup.
#
# Run from the host via cron, not from inside a container: it needs to run
# even if the api container is unhealthy, and it needs a place outside any
# container's own filesystem to put the result.
#
#   crontab -e
#   0 2 * * * /opt/velro/deploy/backup.sh >> /var/log/velro-backup.log 2>&1
#
# A backup that lives on the same disk as the database is not a backup
# against the failure that matters most -- the disk dying. RCLONE_REMOTE
# below is where this script pushes off-box; it is unset by default on
# purpose, so a fresh install fails loudly here rather than quietly keeping
# every backup on a machine that can vanish in one hardware fault.
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/velro}"
KEEP_DAYS="${KEEP_DAYS:-14}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"   # e.g. "hetzner-storagebox:velro-backups"

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump_path="$BACKUP_DIR/velro-$stamp.sql.gz"

cd "$COMPOSE_DIR"
docker compose exec -T db pg_dump -U velro velro | gzip > "$dump_path"

if [ ! -s "$dump_path" ]; then
  echo "backup.sh: dump is empty, refusing to call this a successful backup" >&2
  rm -f "$dump_path"
  exit 1
fi

if [ -n "$RCLONE_REMOTE" ]; then
  rclone copy "$dump_path" "$RCLONE_REMOTE/"
else
  echo "backup.sh: RCLONE_REMOTE is not set -- $dump_path exists only on this VPS" >&2
fi

# Local retention is the safety net for restoring from an hour ago, not the
# archive -- that job belongs to whatever RCLONE_REMOTE points at, which can
# keep its own longer history independently of this host's disk.
find "$BACKUP_DIR" -name 'velro-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
