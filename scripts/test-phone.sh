#!/usr/bin/env bash
# Point sign-in at a country other than Afghanistan, for testing on a real
# handset you own.
#
#   scripts/test-phone.sh 1     # bare numbers become +1  (Canada / US)
#   scripts/test-phone.sh 93    # back to Afghanistan, the product default
#
# Only affects a number typed WITHOUT a prefix. "+93700123456" and
# "+13438677631" are honoured whatever this is set to.
#
# The API must also run with VELRO_OTP_DEBUG_ECHO=true, because VELRO has no
# SMS transport: the code comes back in the response and the app prefills it.
# Never set that outside development -- it hands anyone a code for any number.
set -euo pipefail

CODE="${1:-93}"
DB="${VELRO_DATABASE_URL:-postgresql+psycopg://localhost/velro_dev}"

[[ "$CODE" =~ ^[0-9]{1,4}$ ]] || { echo "country code must be 1-4 digits"; exit 2; }

cd "$(dirname "$0")/../backend"
.venv/bin/python - "$CODE" "$DB" <<'PY'
import json
import sys

from sqlalchemy import create_engine, text

from infrastructure.services.settings import wrap

code, url = sys.argv[1], sys.argv[2]
engine = create_engine(url)
with engine.begin() as conn:
    # Through the same {"v": ...} envelope every other setting uses. A row
    # written without it is the reason _unwrap's double-decode was found.
    updated = conn.execute(
        text(
            "UPDATE app_settings SET value = CAST(:v AS json), version = version + 1 "
            "WHERE key = 'auth.default_country_code'"
        ),
        {"v": json.dumps(wrap(code))},
    ).rowcount
    if not updated:
        conn.execute(
            text(
                "INSERT INTO app_settings (id, key, value, value_type, "
                "description_key, is_secret, created_at, updated_at, version) "
                "VALUES (:id, 'auth.default_country_code', CAST(:v AS json), 'str', "
                "'setting.auth_default_country_code', false, now(), now(), 1)"
            ),
            {"id": "01a05000-0000-7000-8000-000000000010", "v": json.dumps(wrap(code))},
        )
print(f"a number typed without a prefix is now +{code}")
PY
echo "restart the API for it to take effect (settings are cached per request,"
echo "but a running process holds its own connection pool)."
