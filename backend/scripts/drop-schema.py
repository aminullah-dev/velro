"""Empty the database named by VELRO_DATABASE_URL, so a migration walk starts
from nothing.

For scripts/check.sh only. The test suites build their tables with
create_all and leave no alembic_version behind, so `alembic upgrade head`
against that database would trip over tables it did not create. This
removes every table the models know about and the version table, and
refuses to run anywhere but a database whose name says it is for tests --
a check script must not be able to empty production by a mistyped variable.
"""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, text

import infrastructure.db.models  # noqa: F401  -- registers every table
from infrastructure.db.base import Base

url = os.environ.get("VELRO_DATABASE_URL", "")
name = url.rsplit("/", 1)[-1]
if not ("test" in name or "e2e" in name):
    sys.exit(f"refusing to drop schema of {name!r}: not a test database")

engine = create_engine(url)
Base.metadata.drop_all(engine)
with engine.begin() as connection:
    connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
print(f"dropped every table in {name}")
