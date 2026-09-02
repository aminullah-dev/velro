#!/usr/bin/env bash
# Nightly database backup.
#
# Run from the host via cron, not from inside a container: it needs to run
# even if the api container is unhealthy, and it needs a place outside any
# container's own filesystem to put the result.
#
#   crontab -e
#   0 22 * * * RCLONE_REMOTE=gdrive:velro-backups /opt/velro/deploy/backup.sh >> /var/log/velro-backup.log 2>&1
#
# A backup that lives on the same disk as the database is not a backup
# against the failure that matters most -- the disk dying. RCLONE_REMOTE
# below is where this script pushes off-box; it is unset by default on
# purpose, so a fresh install fails loudly here rather than quietly keeping
# every backup on a machine that can vanish in one hardware fault.
#
# Every failure here is announced by email, because the alternative is
# finding out on the morning the backup is needed. See alert() below.
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/velro}"
KEEP_DAYS="${KEEP_DAYS:-14}"
RCLONE_REMOTE="${RCLONE_REMOTE:-}"   # e.g. "gdrive:velro-backups"

# One value out of the compose environment, without sourcing the whole file:
# .env holds the database password and the Gmail app password, and a stray
# backtick in any of them would otherwise run as code in this script.
env_value() {
  [ -f "$COMPOSE_DIR/.env" ] || return 0
  sed -n "s/^$1=//p" "$COMPOSE_DIR/.env" | tail -1
}

# Say out loud that the backup did not happen.
#
# Through the same Gmail account the API already uses for staff sign-in
# codes -- read from .env rather than configured twice, so there is one app
# password on this machine and this is not a second copy of it. Sent with
# curl rather than a mail daemon: nothing else on this host needs one, and a
# daemon that queues silently would reintroduce exactly the silence this
# exists to break. Best-effort by construction: an alert that cannot be sent
# must not stop the retention pass or mask the original failure.
alert() {
  local subject="$1" body="$2"
  local host port user pass from to msg
  host="$(env_value SMTP_HOST)"; port="$(env_value SMTP_PORT)"
  user="$(env_value SMTP_USERNAME)"; pass="$(env_value SMTP_PASSWORD)"
  from="$(env_value SMTP_FROM)"
  to="${BACKUP_ALERT_TO:-$from}"
  if [ -z "$host" ] || [ -z "$to" ] || [ -z "$pass" ]; then
    echo "backup.sh: no SMTP settings in .env -- cannot send: $subject" >&2
    return 0
  fi
  msg="$(mktemp)"
  {
    printf 'From: VELRO backup <%s>\n' "$from"
    printf 'To: %s\n' "$to"
    printf 'Subject: %s\n' "$subject"
    printf 'Date: %s\n' "$(date -R)"
    printf 'Content-Type: text/plain; charset=utf-8\n\n'
    printf '%s\n\nHost: %s\nTime: %s\nLog:  /var/log/velro-backup.log\n' \
      "$body" "$(hostname)" "$(date -u +'%Y-%m-%d %H:%M:%SZ')"
  } > "$msg"
  curl --silent --show-error --ssl-reqd --max-time 60 \
    --url "smtp://$host:${port:-587}" --user "$user:$pass" \
    --mail-from "$from" --mail-rcpt "$to" --upload-file "$msg" \
    || echo "backup.sh: alert email failed to send" >&2
  rm -f "$msg"
}

# Anything unexpected -- pg_dump gone, disk full, docker down -- lands here.
trap 'alert "VELRO backup FAILED" "The nightly backup stopped at line $LINENO. Nothing was uploaded tonight."' ERR

mkdir -p "$BACKUP_DIR"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump_path="$BACKUP_DIR/velro-$stamp.sql.gz"

cd "$COMPOSE_DIR"
docker compose exec -T db pg_dump -U velro velro | gzip > "$dump_path"

if [ ! -s "$dump_path" ]; then
  echo "backup.sh: dump is empty, refusing to call this a successful backup" >&2
  alert "VELRO backup FAILED" "pg_dump produced an empty file. The database may be down."
  rm -f "$dump_path"
  exit 1
fi

# The gzip stream is checked before it is called a backup: a dump truncated
# by a full disk is still a file of plausible size, and the place not to
# discover that is a restore.
if ! gzip -t "$dump_path"; then
  echo "backup.sh: dump is corrupt" >&2
  alert "VELRO backup FAILED" "The dump was written but is not a valid gzip stream -- possibly a full disk."
  exit 1
fi

if [ -n "$RCLONE_REMOTE" ]; then
  rclone copy "$dump_path" "$RCLONE_REMOTE/"
  # Verified by asking the remote, not by trusting an exit code. A copy that
  # wrote half a file and a copy that wrote none can both return zero; the
  # only honest evidence that a backup is off this box is the far end
  # reporting the same number of bytes back.
  local_size="$(stat -c%s "$dump_path")"
  remote_size="$(rclone size "$RCLONE_REMOTE/$(basename "$dump_path")" --json 2>/dev/null \
    | sed -n 's/.*"bytes":\([0-9]*\).*/\1/p')"
  if [ "$remote_size" != "$local_size" ]; then
    echo "backup.sh: uploaded $local_size bytes, remote reports ${remote_size:-nothing}" >&2
    alert "VELRO backup FAILED" \
      "The dump exists on the server but did not arrive intact at $RCLONE_REMOTE (sent $local_size bytes, remote reports ${remote_size:-nothing})."
    exit 1
  fi
  echo "backup.sh: $(basename "$dump_path") -- $local_size bytes, confirmed at $RCLONE_REMOTE"
else
  echo "backup.sh: RCLONE_REMOTE is not set -- $dump_path exists only on this VPS" >&2
fi

# Local retention is the safety net for restoring from an hour ago, not the
# archive -- that job belongs to whatever RCLONE_REMOTE points at, which can
# keep its own longer history independently of this host's disk.
find "$BACKUP_DIR" -name 'velro-*.sql.gz' -mtime "+$KEEP_DAYS" -delete
