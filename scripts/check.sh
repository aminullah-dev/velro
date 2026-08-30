#!/usr/bin/env bash
#
# Everything that must be green before a change lands.
#
# One script, run identically by a person and by CI. A pipeline that runs
# different commands from the ones developers use is a pipeline that fails for
# reasons nobody can reproduce.
#
# Usage: scripts/check.sh [backend|admin|mobile]   (default: all)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET="${1:-all}"
FAILED=()

# Tests need a database and a signing secret. CI supplies its own; these are
# the local defaults and are not secrets -- the real ones never live in a file.
export VELRO_TEST_DATABASE_URL="${VELRO_TEST_DATABASE_URL:-postgresql+psycopg://localhost/velro_e2e}"
export VELRO_JWT_SECRET="${VELRO_JWT_SECRET:-test-secret-key-at-least-32-characters}"

step() {
  local name="$1"; shift
  printf '\n\033[1m▸ %s\033[0m\n' "$name"
  if "$@"; then
    printf '\033[32m  ✓ %s\033[0m\n' "$name"
  else
    printf '\033[31m  ✗ %s\033[0m\n' "$name"
    FAILED+=("$name")
  fi
}

backend() {
  cd "$ROOT/backend"
  local py=.venv/bin
  [ -x "$py/python" ] || { echo "backend/.venv missing -- see README"; return 1; }
  step "backend lint"        "$py/ruff" check .
  # The domain must be testable with no database and no fixtures. If this needs
  # PostgreSQL, the layering has been broken.
  step "backend unit"        "$py/pytest" tests/unit -q
  step "backend integration" "$py/pytest" tests/integration -q
  step "backend e2e"         "$py/pytest" tests/e2e -q
}

admin() {
  cd "$ROOT/admin"
  [ -d node_modules ] || npm ci --silent
  step "admin locales" node scripts/sync-locales.mjs
  step "admin tokens"  node scripts/check-tokens.mjs
  # The panel and the driver's app must agree on what day it is.
  step "admin calendar" node --experimental-strip-types --no-warnings \
    scripts/check-calendar.mjs
  # A paused query must not read as an empty list.
  step "admin gates"    node scripts/check-query-gates.mjs
  step "admin lint"    npm run --silent lint
  step "admin types"   npm run --silent typecheck
  step "admin build"   npm run --silent build
}

# A LazyColumn inside VelroScreen's scrolling frame crashes at measure time:
# Compose refuses a lazy list given infinite height. It is not a compile error
# and no unit test sees it, because the crash needs the list to have at least
# one row -- an empty branch renders an EmptyState and nothing is nested. The
# driver's board shipped this way: it worked all the way through testing and
# died the first time a passenger was actually waiting for a car.
#
# VelroScreen(scrollable = false) is the fix, and this is what stops the next
# screen repeating it.
nested_lazy_lists() {
  local bad=0 f
  while IFS= read -r f; do
    # Skip the file that defines VelroScreen: it names the lazy types in its
    # own documentation, which is the opposite of the mistake.
    grep -q "fun VelroScreen(" "$f" && continue
    grep -q "VelroScreen(" "$f" || continue
    grep -qE "LazyColumn\(|LazyRow\(|LazyVerticalGrid\(" "$f" || continue
    grep -q "scrollable = false" "$f" && continue
    echo "  $f has a lazy list inside VelroScreen but never passes scrollable = false" >&2
    bad=1
  done < <(find "$ROOT/mobile" -name "*.kt" -not -path "*/build/*")
  return $bad
}

mobile() {

  cd "$ROOT/mobile"
  command -v gradle >/dev/null || { echo "gradle not found; skipping mobile"; return 0; }
  # :domain is a plain Kotlin module, so this also proves it stayed free of
  # Android -- an android.* import there fails to compile.
  step "mobile domain"  gradle :domain:test --console=plain -q
  step "mobile data"    gradle :data:test --console=plain -q
  step "mobile core:ui" gradle :core:ui:testDebugUnitTest --console=plain -q
  # Calendar and numerals. Without this line the Nowruz fixtures never run.
  step "mobile core:i18n" gradle :core:i18n:testDebugUnitTest --console=plain -q
  step "mobile driver"  gradle :feature:driver:testDebugUnitTest --console=plain -q
  # The emergency numbers and the categories the sheet ships compiled in.
  step "mobile safety"  gradle :feature:safety:testDebugUnitTest --console=plain -q
  step "mobile auth"    gradle :feature:auth:testDebugUnitTest --console=plain -q
  step "mobile nesting" nested_lazy_lists
  step "mobile build"   gradle :app-driver:assembleDebug :app-passenger:assembleDebug --console=plain -q

  # Room migrations and the sign-out path, on a real device.
  #
  # These need an emulator, so they are skipped when none is attached rather
  # than failing -- but skipping quietly is how they rotted: an exported schema
  # was overwritten and committed, and the migration tests had been failing
  # unnoticed because nothing ever ran them. Both defects they cover are
  # unrecoverable on somebody's phone, so the skip says so out loud.
  local adb="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}/platform-tools/adb"
  command -v adb >/dev/null && adb=adb
  if [ -x "$adb" ] || command -v "$adb" >/dev/null 2>&1; then
    if "$adb" devices 2>/dev/null | grep -q "	device$"; then
      step "mobile device" gradle :data:connectedDebugAndroidTest --console=plain -q
    else
      printf '  \033[33m- mobile device (nothing attached; migrations unverified)\033[0m\n'
    fi
  else
    printf '  \033[33m- mobile device (no adb; migrations unverified)\033[0m\n'
  fi
}

case "$TARGET" in
  backend) backend ;;
  admin)   admin ;;
  mobile)  mobile ;;
  all)     backend; admin; mobile ;;
  *)       echo "unknown target: $TARGET"; exit 2 ;;
esac

printf '\n'
if [ ${#FAILED[@]} -eq 0 ]; then
  printf '\033[32mall checks passed\033[0m\n'
else
  printf '\033[31mfailed: %s\033[0m\n' "${FAILED[*]}"
  exit 1
fi
