#!/usr/bin/env bash
# Put one number on OTP_TEST_NUMBERS and GEOFENCE_EXEMPT_PHONES, then restart
# the API so it reads them.
#
#   deploy/list-test-number.sh +12025550142
#
# For App Review's demo account, and any number like it: a listed number gets
# its sign-in code in the answer instead of an SMS, may ask for a ride from
# outside the service area, and -- because it is on OTP_TEST_NUMBERS -- is
# only ever shown to test drivers (ADR 0014's neighbour, _board_scope).
#
# Appends, never replaces: GEOFENCE_EXEMPT_PHONES already holds the owner's
# own handset abroad. Keeps a dated copy of .env beside it, and prints only
# the two lines it touched -- the rest of that file is passwords.
set -euo pipefail

NUMBER="${1:?usage: list-test-number.sh +E164NUMBER}"
case "$NUMBER" in
  +[1-9][0-9][0-9][0-9][0-9][0-9][0-9]*) ;;
  *) echo "a number in E.164, with its +: $NUMBER" >&2; exit 1 ;;
esac

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-.env}"
[ -f "$ENV_FILE" ] || { echo "no $ENV_FILE here -- run bootstrap.sh first" >&2; exit 1; }

# Unique even for two runs in one second, so a second run never overwrites
# the copy of the file as it was before the first.
cp -p "$ENV_FILE" "$(mktemp "$ENV_FILE.bak-$(date -u +%Y%m%dT%H%M%SZ)-XXXX")"
tmp="$(mktemp "$ENV_FILE.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

# index(), not a regex: a number starts with +, which a regex reads as "one
# or more of nothing".
awk -v n="$NUMBER" '
  BEGIN { want["OTP_TEST_NUMBERS"] = 1; want["GEOFENCE_EXEMPT_PHONES"] = 1 }
  {
    eq = index($0, "=")
    key = eq ? substr($0, 1, eq - 1) : ""
    if (key in want) {
      value = substr($0, eq + 1)
      seen[key] = 1
      if (index("," value ",", "," n ",") == 0) value = (value == "" ? n : value "," n)
      print key "=" value
      next
    }
    print
  }
  END { for (k in want) if (!(k in seen)) print k "=" n }
' "$ENV_FILE" > "$tmp"

chmod --reference="$ENV_FILE" "$tmp" 2>/dev/null || chmod 600 "$tmp"
mv "$tmp" "$ENV_FILE"
trap - EXIT

grep -E '^(OTP_TEST_NUMBERS|GEOFENCE_EXEMPT_PHONES)=' "$ENV_FILE"

if [ -z "${NO_RESTART:-}" ]; then
  # Compose recreates the API because its environment changed; the database
  # and Caddy are left alone.
  docker compose up -d api
  docker compose exec -T api printenv VELRO_OTP_TEST_NUMBERS VELRO_GEOFENCE_EXEMPT_PHONES
fi
