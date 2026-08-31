#!/usr/bin/env bash
# Local API for driving the Android emulator against a real backend.
#
# Not a deployment path: the database URL and JWT secret here are development
# values, and otp_debug_echo in velro.toml returns the sign-in code in the API
# response so a developer never spends an SMS. Production takes both from the
# environment and refuses debug echo outright (shared/config.py).
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH=.
export VELRO_DATABASE_URL="${VELRO_DATABASE_URL:-postgresql+psycopg://aminullahhashemi@localhost:5432/velro_dev}"
export VELRO_JWT_SECRET="${VELRO_JWT_SECRET:-dev-only-local-secret-not-for-production}"
exec .venv/bin/uvicorn --factory ui.api.app:create_app --host 0.0.0.0 --port 8000 "$@"
