#!/usr/bin/env bash
# Build both apps and put them where the download page serves from.
#
#   scripts/publish-apks.sh https://api.velro.linumic.com/api/v1/   # release
#   scripts/publish-apks.sh 10.0.0.109 --debug                      # LAN
#
# Publishing puts the files in backend/var/apks, which is where the download
# page serves from. On the server that directory is a docker volume, and the
# APKs get there by upload -- see deploy/README.md -- because the signing key
# lives on a laptop and never on the VPS.
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
TARGET="${1:?usage: publish-apks.sh <api-host-or-url> [--debug]}"
VARIANT="release"
[ "${2:-}" = "--debug" ] && VARIANT="debug"

# A bare host is the development shorthand and means http://host:8000; a
# full URL is used exactly as given, which is what production needs.
case "$TARGET" in
  https://*|http://*) GRADLE_ARG="-Pvelro.apiUrl=${TARGET%/}/" ;;
  *)                  GRADLE_ARG="-Pvelro.apiHost=$TARGET" ;;
esac

# A release build refuses cleartext, so pointing one at http is publishing an
# app that cannot reach its own backend -- and the person who finds out is
# whoever installed it, in a valley, with no way to tell why.
if [ "$VARIANT" = "release" ] && [ "${TARGET#https://}" = "$TARGET" ]; then
    echo "refusing: a release build talks HTTPS only, and $TARGET is not." >&2
    echo "For a LAN or emulator target use --debug; for production pass" >&2
    echo "the full https URL, e.g. https://api.velro.linumic.com/api/v1/" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
OUT="$ROOT/backend/var/apks"
mkdir -p "$OUT"

cd "$ROOT/mobile"
if [ "$VARIANT" = "release" ]; then
    ./gradlew :app-passenger:assembleRelease :app-driver:assembleRelease \
        "$GRADLE_ARG" -q
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
        "$GRADLE_ARG" -q
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
echo "published $NAME ($CODE), $VARIANT build, pointed at $TARGET"
ls -lh "$OUT"/*.apk | awk '{print "  " $NF, $5}'
