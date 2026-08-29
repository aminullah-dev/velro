"""End-to-end fixtures.

One fully wired application against its own seeded database, shared by every
module here. Session-scoped: seeding is the slow part, and the tests are written
not to depend on each other's leftovers.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from infrastructure.db.session import build_engine, build_session_factory
from shared import config

DATABASE_URL = os.environ.get(
    "VELRO_TEST_DATABASE_URL", "postgresql+psycopg://localhost/velro_e2e"
)


@pytest.fixture(scope="session")
def client():
    """A fully wired application against its own seeded database."""
    os.environ["VELRO_DATABASE_URL"] = DATABASE_URL
    os.environ.setdefault("VELRO_JWT_SECRET", "test-secret-key-at-least-32-characters")
    os.environ["VELRO_OTP_DEBUG_ECHO"] = "true"

    import infrastructure.db.models  # noqa: F401
    from infrastructure.db.base import Base
    from scripts.seed import seed
    from ui.api import deps

    # The composition root caches settings and the engine; clear them so this
    # module's database is the one that gets used.
    deps.settings.cache_clear()
    deps._engine.cache_clear()
    deps._session_factory.cache_clear()
    deps.tokens.cache_clear()

    engine = build_engine(DATABASE_URL)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with build_session_factory(engine)() as session:
        seed(session)

    from ui.api.app import create_app

    with TestClient(create_app(config.load()), raise_server_exceptions=False) as c:
        yield c


