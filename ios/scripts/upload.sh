#!/usr/bin/env bash
#
# Archive the VELRO passenger app and send it to App Store Connect (TestFlight),
# in one command. The same shape as Namazia's scripts/upload.sh.
#
#   ios/scripts/upload.sh              archive, export, upload
#   ios/scripts/upload.sh --dry-run    archive and export only, no upload
#   ios/scripts/upload.sh --build 7    use build number 7 instead of the next one
#
# The API key is named in ios/scripts/.env (git-ignored; see .env.example).
# Release builds talk to https://api.velro.linumic.com -- this is the real app.

set -euo pipefail

cd "$(dirname "$0")/.."          # ios/
ROOT="$PWD"
BUILD_DIR="$ROOT/build/upload"
ARCHIVE="$BUILD_DIR/Velro.xcarchive"
EXPORT_DIR="$BUILD_DIR/export"

DRY_RUN=false
FORCED_BUILD=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --build)   FORCED_BUILD="${2:-}"; shift 2 ;;
        -h|--help) sed -n '3,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
done

[[ -f "$ROOT/scripts/.env" ]] && { set -a; source "$ROOT/scripts/.env"; set +a; }
DEVELOPMENT_TEAM="${DEVELOPMENT_TEAM:-27RXPRW77S}"
missing=()
for var in ASC_KEY_ID ASC_ISSUER_ID ASC_KEY_PATH; do
    [[ -n "${!var:-}" ]] || missing+=("$var")
done
if [[ ${#missing[@]} -gt 0 ]]; then
    echo "Missing: ${missing[*]} -- set them in ios/scripts/.env (see .env.example)." >&2
    exit 1
fi
ASC_KEY_PATH="${ASC_KEY_PATH/#\~/$HOME}"
[[ -f "$ASC_KEY_PATH" ]] || { echo "ASC_KEY_PATH does not exist: $ASC_KEY_PATH" >&2; exit 1; }

# App Store Connect refuses a build number it has seen before, even from a
# build that was never released; bumping it here stops the commonest failed
# upload. Commit project.yml afterwards so the next run starts from it.
if [[ -n "$FORCED_BUILD" ]]; then
    BUILD_NUMBER="$FORCED_BUILD"
else
    CURRENT=$(grep -E '^[[:space:]]*CURRENT_PROJECT_VERSION:' project.yml | head -1 | sed -E 's/.*"([0-9]+)".*/\1/')
    BUILD_NUMBER=$((CURRENT + 1))
fi
sed -i '' -E "s/(CURRENT_PROJECT_VERSION: )\"[0-9]+\"/\1\"$BUILD_NUMBER\"/" project.yml
MARKETING=$(grep -E '^[[:space:]]*MARKETING_VERSION:' project.yml | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
echo "▸ VELRO $MARKETING (build $BUILD_NUMBER)"

AUTH=(-allowProvisioningUpdates
      -authenticationKeyPath "$ASC_KEY_PATH"
      -authenticationKeyID "$ASC_KEY_ID"
      -authenticationKeyIssuerID "$ASC_ISSUER_ID")

echo "▸ Generating project"
xcodegen generate --quiet
rm -rf "$BUILD_DIR"; mkdir -p "$BUILD_DIR"

echo "▸ Archiving (a few minutes)"
xcodebuild archive -project Velro.xcodeproj -scheme VelroPassenger -configuration Release \
    -destination 'generic/platform=iOS' -archivePath "$ARCHIVE" \
    "${AUTH[@]}" DEVELOPMENT_TEAM="$DEVELOPMENT_TEAM" | tail -5

# destination=upload hands the build straight to App Store Connect: no altool.
DESTINATION="upload"; $DRY_RUN && DESTINATION="export"
OPTIONS="$BUILD_DIR/ExportOptions.plist"
cat > "$OPTIONS" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>method</key><string>app-store-connect</string>
    <key>destination</key><string>$DESTINATION</string>
    <key>teamID</key><string>$DEVELOPMENT_TEAM</string>
    <key>signingStyle</key><string>automatic</string>
    <key>uploadSymbols</key><true/>
    <key>manageAppVersionAndBuildNumber</key><false/>
</dict>
</plist>
PLIST

if $DRY_RUN; then echo "▸ Exporting (no upload)"; else echo "▸ Exporting and uploading"; fi
xcodebuild -exportArchive -archivePath "$ARCHIVE" -exportOptionsPlist "$OPTIONS" \
    -exportPath "$EXPORT_DIR" "${AUTH[@]}" | tail -5

echo
if $DRY_RUN; then
    echo "✓ Build $BUILD_NUMBER exported to ios/build/upload/export -- nothing uploaded."
else
    echo "✓ Build $BUILD_NUMBER uploaded. It is processed in 10-30 minutes; TestFlight emails either way."
fi
echo "  Commit the build number: git commit -am \"iOS build $BUILD_NUMBER\""
