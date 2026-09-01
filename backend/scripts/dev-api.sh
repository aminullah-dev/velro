#!/usr/bin/env bash
# Local API for driving the Android emulator against a real backend.
#
# Not a deployment path: the database URL and JWT secret here are development
# values, and this script turns on OTP echo so the sign-in code comes back in
# the API response -- a developer never spends an SMS, and the admin tools
# (/admin/placer) can fill the code in themselves. velro.toml keeps echo OFF,
# so the real SMS path is what runs anywhere this script does not, and
# shared/config.py refuses echo outright when environment = production.
#
# To exercise the real code path locally instead:
#   VELRO_OTP_DEBUG_ECHO=false scripts/dev-api.sh
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.
export VELRO_DATABASE_URL="${VELRO_DATABASE_URL:-postgresql+psycopg://aminullahhashemi@localhost:5432/velro_dev}"
export VELRO_JWT_SECRET="${VELRO_JWT_SECRET:-dev-only-local-secret-not-for-production}"
export VELRO_OTP_DEBUG_ECHO="${VELRO_OTP_DEBUG_ECHO:-true}"
exec .venv/bin/uvicorn --factory ui.api.app:create_app --host 0.0.0.0 --port 8000 "$@"
