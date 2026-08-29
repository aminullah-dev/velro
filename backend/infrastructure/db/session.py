"""Engine, session and unit of work.

One use case, one transaction. ``UnitOfWork`` commits on clean exit and rolls
back on any exception. Repositories never commit -- a repository that calls
``session.commit()`` makes every multi-step use case non-atomic, and the symptom
is a half-written booking discovered a week later.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from types import TracebackType

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def build_engine(url: str, *, echo: bool = False) -> Engine:
    if url.startswith("sqlite"):
        engine = create_engine(url, echo=echo, future=True)

        @event.listens_for(engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            # Foreign keys are off by default in SQLite. A schema whose
            # constraints are silently ignored is worse than one with none.
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

        return engine

    return create_engine(
        url,
        echo=echo,
        future=True,
        pool_pre_ping=True,     # a connection killed by a network blip fails once, not forever
        pool_size=10,
        max_overflow=20,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)


class UnitOfWork:
    """The transaction boundary. Owned by a use case, never by a repository."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("unit of work used outside its context manager")
        return self._session

    def __enter__(self) -> UnitOfWork:
        self._session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self._session is not None
        try:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None

    def flush(self) -> None:
        """Make pending writes visible to later statements in the same transaction.

        Needed when a constraint violation should surface now -- for instance
        the unique index on a reserved seat -- rather than at commit.
        """
        self.session.flush()


@contextmanager
def unit_of_work(session_factory: sessionmaker[Session]) -> Iterator[UnitOfWork]:
    with UnitOfWork(session_factory) as uow:
        yield uow
