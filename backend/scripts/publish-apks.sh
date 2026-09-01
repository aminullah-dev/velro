#!/usr/bin/env bash
# Build both apps and put them where the download page serves from.
#
#   scripts/publish-apks.sh api.velro.linumic.com          # signed release
#   scripts/publish-apks.sh 10.0.0.109 --debug             # testers on the LAN
#
# The host is baked into the APK: whoever installs this build talks to that
# backend. Publishing is the moment that choice is made, which is why it is
# an argument and not a default.
#
# Release is the default, and a release build is refused unless it came out
# signed. An unsigned APK cannot be installed at all, so publishing one would
# put a file on the download page that every single person who taps it fails
# to install -- discovering that only after the download.
set -euo pipefail
HOST="${1:?usage: publish-apks.sh <api-host> [--debug]}"
VARIANT="release"
[ "${2:-}" = "--debug" ] && VARIANT="debug"

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/backend/var/apks"
mkdir -p "$OUT"

cd "$ROOT/mobile"
if [ "$VARIANT" = "release" ]; then
    ./gradlew :app-passenger:assembleRelease :app-driver:assembleRelease \
        -Pvelro.apiHost="$HOST" -q
    PASSENGER="app-passenger/build/outputs/apk/release/app-passenger-release.apk"
    DRIVER="app-driver/build/outputs/apk/release/app-driver-release.apk"
    for apk in "$PASSENGER" "$DRIVER"; do
        if [ ! -f "$apk" ]; then
            echo "refusing to publish: $(basename "$apk") was not produced." >&2
            echo "The release came out unsigned, which means no keystore was" >&2
            echo "configured. See mobile/README.md -- either export" >&2
            echo "VELRO_KEYSTORE and VELRO_KEYSTORE_PASSWORD, or write" >&2
            echo "mobile/keystore.properties." >&2
            exit 1
        fi
    done
else
    ./gradlew :app-passenger:assembleDebug :app-driver:assembleDebug \
        -Pvelro.apiHost="$HOST" -q
    PASSENGER="app-passenger/build/outputs/apk/debug/app-passenger-debug.apk"
    DRIVER="app-driver/build/outputs/apk/debug/app-driver-debug.apk"
fi

cp "$PASSENGER" "$OUT/velro-passenger.apk"
cp "$DRIVER" "$OUT/velro-driver.apk"

NAME=$(grep '^velro.versionName=' gradle.properties | cut -d= -f2)
CODE=$(grep '^velro.versionCode=' gradle.properties | cut -d= -f2)
cat > "$OUT/release.json" <<JSON
{
  "passenger": {"version_name": "$NAME", "version_code": $CODE, "apk": "/app/velro-passenger.apk"},
  "driver": {"version_name": "$NAME", "version_code": $CODE, "apk": "/app/velro-driver.apk"}
}
JSON
echo "published $NAME ($CODE), $VARIANT build, for host $HOST"
ls -lh "$OUT"/*.apk | awk '{print "  " $NF, $5}'
