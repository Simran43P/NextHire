"""
Database engine and session handling.

SQLite through the async driver. Two settings matter more than they look:

- **WAL journaling.** The default rollback journal takes a global write lock,
  so a background task writing a task result would block every read. WAL lets
  readers continue during a write, which is the difference between the queue
  working and the app appearing to hang.

- **Foreign keys on.** SQLite ignores foreign key constraints unless asked,
  per connection. Without this, `ON DELETE CASCADE` silently does nothing and
  account deletion leaves orphaned resumes behind.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import config
from models import Base

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _configure_sqlite(dbapi_connection, _record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    # Wait rather than failing instantly when another writer holds the lock.
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        is_sqlite = config.DATABASE_URL.startswith("sqlite")
        _engine = create_async_engine(
            config.DATABASE_URL,
            echo=False,
            future=True,
            # A file-backed SQLite database does not benefit from a large pool,
            # and an in-memory one must not be pooled across connections at all.
            pool_pre_ping=not is_sqlite,
        )
        if is_sqlite:
            event.listen(_engine.sync_engine, "connect", _configure_sqlite)
        _sessionmaker = async_sessionmaker(
            _engine, expire_on_commit=False, class_=AsyncSession
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. One session per request, always closed."""
    async with get_sessionmaker()() as session:
        yield session


async def create_all() -> None:
    """
    Create any missing tables.

    Alembic owns schema changes; this exists so a fresh checkout and the test
    suite can stand up a database without running a migration first.
    """
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def healthcheck() -> bool:
    try:
        async with get_sessionmaker()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # pragma: no cover - only hit on a broken install
        print(f"[db] healthcheck failed: {exc}")
        return False


async def dispose() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
