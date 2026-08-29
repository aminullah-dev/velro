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
  step "mobile build"   gradle :app-driver:assembleDebug :app-passenger:assembleDebug --console=plain -q
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
