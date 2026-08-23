"""Async engine and session plumbing.

Two responsibilities:

1. Own a single lazily-created `AsyncEngine`. Creating it on first use rather
   than at import time means importing this package never touches the network
   or the filesystem, and a bad configuration raises `ConfigurationError` at a
   point the caller can act on.

2. Provide the ambient-session mechanism the service layer relies on. Services
   call `auto_session()` and get either the caller's open transaction or a
   fresh, self-committing one, so the same function works standalone and as
   part of a larger unit of work.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine

from .settings import DatabaseSettings, load_settings

# Created on first use by _ensure_engine(); reset by configure()/dispose_engine().
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_settings: DatabaseSettings | None = None

# The session an enclosing transaction has published for nested calls to join.
_current_session: ContextVar[AsyncSession | None] = ContextVar(
    "con_mcp_current_session", default=None
)


def _build_engine(url: str, *, echo: bool) -> AsyncEngine:
    """Create an engine and apply dialect-specific connection setup."""
    engine = create_async_engine(url, echo=echo)

    if engine.dialect.name == "sqlite":
        # SQLite ignores foreign keys unless each connection opts in, which
        # would silently disable every ON DELETE CASCADE in the schema and
        # leave orphaned labels, comments and edges behind after a delete.
        @event.listens_for(engine.sync_engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record):  # noqa: ANN001
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def configure(url: str, *, echo: bool = False) -> None:
    """Point the process at an explicit database URL.

    Overrides whatever the environment says. Intended for tests and embedding;
    any previously built engine is dropped, so call this before issuing work.
    """
    global _engine, _session_factory, _settings

    _engine = _build_engine(url, echo=echo)
    _session_factory = async_sessionmaker(
        bind=_engine, class_=AsyncSession, expire_on_commit=False
    )
    _settings = DatabaseSettings(backend="custom", url=url)


def _ensure_engine() -> None:
    """Build the engine from environment settings if it does not exist yet."""
    global _engine, _session_factory, _settings

    if _session_factory is not None:
        return

    _settings = load_settings()
    _engine = _build_engine(_settings.url, echo=False)
    _session_factory = async_sessionmaker(
        bind=_engine, class_=AsyncSession, expire_on_commit=False
    )


def get_engine() -> AsyncEngine:
    """Return the process-wide engine, creating it on first call."""
    _ensure_engine()
    assert _engine is not None  # narrowed by _ensure_engine
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the session factory bound to the current engine."""
    _ensure_engine()
    assert _session_factory is not None  # narrowed by _ensure_engine
    return _session_factory


def get_database_url() -> str:
    """Return the resolved database URL (used by Alembic's env.py)."""
    _ensure_engine()
    assert _settings is not None  # narrowed by _ensure_engine
    return _settings.url


async def dispose_engine() -> None:
    """Close pooled connections and forget the engine.

    Tests call this between cases; long-running processes rarely need it.
    """
    global _engine, _session_factory, _settings

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _session_factory = None
    _settings = None


def get_session() -> AsyncSession | None:
    """Return the ambient session, or None when no transaction is open."""
    return _current_session.get()


@asynccontextmanager
async def auto_session() -> AsyncIterator[AsyncSession]:
    """Join the ambient transaction, or run standalone and commit on success.

    Service functions wrap their bodies in this. When one service calls another
    the inner call sees the outer session and contributes to the same
    transaction, so a failure part-way through a composite operation rolls the
    whole thing back instead of leaving half-written rows behind.
    """
    ambient = _current_session.get()

    if ambient is not None:
        yield ambient
        return

    async with get_session_factory()() as session:
        token = _current_session.set(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            _current_session.reset(token)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Group several service calls into one explicit transaction.

    async with session_scope():
        await create_issue(title="parent")
        await add_comment(...)
    # both committed together, or neither
    """
    async with get_session_factory()() as session:
        token = _current_session.set(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            _current_session.reset(token)
