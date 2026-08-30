#!/usr/bin/env bash
# Sign in against production without holding the handset.
#
# The owner is in Canada and the test phones are in Afghanistan, so "read me
# the code" is a round trip through another person in another timezone. This
# does the whole thing from here: request a code, read the message VELRO
# itself sent back out of Twilio, and complete the sign-in.
#
#   ./scripts/verify-signin.sh +93775885900
#
# Two things this is NOT:
#
# It is not a back door into the product. Reading the message requires the
# Twilio account credentials, which live only in /opt/velro/deploy/.env on
# the server. Nothing on the public API returns a code -- config.load refuses
# to start production with the debug echo on, and that guard stays.
#
# And it is not free. Every run sends a real SMS at about $0.45 against a
# ~$50/month budget, so this is a check to run when something changed, not a
# loop.
set -euo pipefail

PHONE="${1:-}"
if [ -z "$PHONE" ]; then
  echo "usage: $0 +93XXXXXXXXX" >&2
  exit 2
fi

API="${VELRO_API:-https://api.velro.linumic.com}"
SSH_KEY="${VELRO_SSH_KEY:-$HOME/.ssh/velro_hetzner}"
SERVER="${VELRO_SERVER:-root@62.238.0.71}"
ACCOUNT="AC5d9488036f52a613e45aa87b84d20f77"

remote() { ssh -i "$SSH_KEY" "$SERVER" "$@"; }

echo "1. asking $API for a code"
curl -fsS -X POST "$API/api/v1/auth/otp/request" \
  -H 'Content-Type: application/json' \
  -d "{\"phone\":\"$PHONE\",\"locale\":\"fa-AF\"}" > /dev/null
sleep 4

echo "2. finding the message the server just sent"
sid=$(remote "cd /opt/velro/deploy && docker compose logs --since 40s api 2>&1 \
  | grep 'sms.accepted' | tail -1" | grep -oE 'SM[0-9a-f]{32}' || true)
if [ -z "$sid" ]; then
  echo "   no send was logged -- check: docker compose logs api | grep sms" >&2
  exit 1
fi
echo "   $sid"

echo "3. reading it back"
# Fed to the remote shell as stdin rather than as a quoted argument. Nesting
# the credentials inside a double-quoted ssh string is how the first two
# attempts at this broke -- and each failure cost a real 45-cent SMS, which is
# its own argument for getting the quoting out of the way entirely.
#
# The secrets never leave the server: it sources .env there and prints only
# the digits.
code=$(ssh -i "$SSH_KEY" "$SERVER" bash -s "$ACCOUNT" "$sid" <<'REMOTE'
set -euo pipefail
cd /opt/velro/deploy
set -a; . ./.env; set +a
curl -fsS "https://api.twilio.com/2010-04-01/Accounts/$1/Messages/$2.json" \
  -u "$TWILIO_API_KEY_SID:$TWILIO_AUTH_TOKEN" \
| python3 -c 'import json,re,sys; b=json.load(sys.stdin).get("body") or ""; m=re.search(r"\d{4,8}", b); print(m.group(0) if m else "")'
REMOTE
)

if [ -z "$code" ]; then
  echo "   could not read the code back from Twilio" >&2
  exit 1
fi

echo "4. signing in"
curl -fsS -X POST "$API/api/v1/auth/otp/verify" \
  -H 'Content-Type: application/json' \
  -d "{\"phone\":\"$PHONE\",\"code\":\"$code\"}" \
  | python3 -c '
import json, sys
d = json.load(sys.stdin)
if not d.get("success"):
    print("   FAILED:", d.get("error")); sys.exit(1)
v = d["data"]
print("   signed in.",
      "new account." if v.get("is_new_user") else "existing account.")
print("   access token:", (v.get("access_token") or "")[:28] + "...")
print("   refresh token:", "present" if v.get("refresh_token") else "MISSING")
'
