#!/usr/bin/env bash
# Build both apps and put them where the download page serves from.
#
# Usage: scripts/publish-apks.sh <api-host>
#   e.g. scripts/publish-apks.sh 10.0.0.109     (testers on the LAN)
#        scripts/publish-apks.sh api.velro.linumic.com
#
# The host is baked into the APK: whoever installs this build talks to that
# backend. Publishing is the moment that choice is made, which is why it is
# an argument and not a default.
set -euo pipefail
HOST="${1:?usage: publish-apks.sh <api-host>}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/backend/var/apks"
mkdir -p "$OUT"

cd "$ROOT/mobile"
gradle :app-passenger:assembleDebug :app-driver:assembleDebug -Pvelro.apiHost="$HOST" -q

cp app-passenger/build/outputs/apk/debug/app-passenger-debug.apk "$OUT/velro-passenger.apk"
cp app-driver/build/outputs/apk/debug/app-driver-debug.apk "$OUT/velro-driver.apk"

NAME=$(grep '^velro.versionName=' gradle.properties | cut -d= -f2)
CODE=$(grep '^velro.versionCode=' gradle.properties | cut -d= -f2)
cat > "$OUT/release.json" <<JSON
{
  "passenger": {"version_name": "$NAME", "version_code": $CODE, "apk": "/app/velro-passenger.apk"},
  "driver": {"version_name": "$NAME", "version_code": $CODE, "apk": "/app/velro-driver.apk"}
}
JSON
echo "published $NAME ($CODE) for host $HOST -> $OUT"
