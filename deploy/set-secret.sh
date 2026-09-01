#!/usr/bin/env bash
# Put a secret into deploy/.env without it appearing anywhere else.
#
#   deploy/set-secret.sh TELEGRAM_GATEWAY_TOKEN
#
# It asks for the value with the echo off, so it is not on the screen; it
# does not take the value as an argument, so it is not in the shell history
# or in ps output; and it never prints it back. The only place it lands is
# the file that is already git-ignored and already holds the database
# password.
#
# Replaces the key if it is already there rather than appending a second
# line: two lines for one key is a config whose meaning depends on which
# one the parser reads last.
set -euo pipefail

KEY="${1:?usage: set-secret.sh KEY_NAME}"
case "$KEY" in
  [A-Z_]*) ;;
  *) echo "a key name is upper case with underscores: $KEY" >&2; exit 1 ;;
esac

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f .env ] || { echo "no deploy/.env here -- run bootstrap.sh first" >&2; exit 1; }

printf 'value for %s (not shown): ' "$KEY" >&2
read -rs VALUE
printf '\n' >&2
[ -n "$VALUE" ] || { echo "empty; nothing changed" >&2; exit 1; }

# A temp file beside .env, then a move: an interrupted write must not leave
# the deployment holding half a password.
tmp="$(mktemp .env.XXXXXX)"
trap 'rm -f "$tmp"' EXIT
grep -v "^${KEY}=" .env > "$tmp" || true
printf '%s=%s\n' "$KEY" "$VALUE" >> "$tmp"
unset VALUE
chmod --reference=.env "$tmp" 2>/dev/null || chmod 600 "$tmp"
mv "$tmp" .env
trap - EXIT

echo "$KEY set. Restarting the API so it reads it."
docker compose up -d api >/dev/null
sleep 3
docker compose exec -T api python -c "
from shared import config
c = config.load()
name = '$KEY'
value = getattr(c, name.replace('VELRO_', '').lower(), None) or getattr(c, name.lower(), None)
print(name, 'is now', 'set' if value else 'STILL EMPTY -- check the name matches the compose file')
"
