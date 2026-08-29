"""Test fixtures.

Integration tests run against a real PostgreSQL, because the guarantees being
tested -- row locks, unique constraints, transaction isolation -- do not exist
in a fake.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text

import infrastructure.db.models  # noqa: F401  -- registers every table
from infrastructure.db.base import Base
from infrastructure.db.session import build_engine, build_session_factory

TEST_DATABASE_URL = os.environ.get(
    "VELRO_TEST_DATABASE_URL", "postgresql+psycopg://localhost/velro_test"
)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    engine = build_engine(TEST_DATABASE_URL)
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session_factory(engine: Engine):
    return build_session_factory(engine)


@pytest.fixture()
def clean_database(engine: Engine) -> Iterator[None]:
    """Truncate between tests rather than recreating: an order of magnitude faster."""
    yield
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
