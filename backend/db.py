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

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event, inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import config
from models import Base

_BACKEND_DIR = Path(__file__).resolve().parent

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
    Create any missing tables directly, bypassing Alembic.

    Used only by the test suite, where a throwaway database per test makes
    running migrations pure overhead. Application startup goes through
    `ensure_schema` so that exactly one thing owns the schema.
    """
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


def _alembic_config():
    """Alembic pointed at absolute paths, so the cwd does not matter."""
    from alembic.config import Config

    cfg = Config(str(_BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", config.DATABASE_URL)
    return cfg


async def _table_names() -> list[str]:
    engine = get_engine()
    async with engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).get_table_names()
        )


async def _current_revision(tables: list[str]) -> str | None:
    """
    The revision Alembic believes the database is at, or None.

    Checking for a *row* rather than for the table: a migration that failed
    part-way leaves `alembic_version` behind with nothing in it, and treating
    that as "already tracked" is what turns one failed upgrade into a database
    that can never be upgraded again.
    """
    if "alembic_version" not in tables:
        return None
    async with get_sessionmaker()() as session:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        row = result.first()
    return row[0] if row else None


async def ensure_schema() -> None:
    """
    Bring the database up to the current schema, whatever state it is in.

    Three cases have to work, because all three happen in practice:

    - **Empty database.** Migrations run and create everything.
    - **Already migrated.** `upgrade` is a no-op.
    - **Tables exist but Alembic has never seen them.** This is the one that
      bit: an earlier version of this app called `create_all()` on startup, so
      databases exist with a full schema and no migration history. Running
      `upgrade` against those fails with "table users already exists". They are
      stamped as current instead, which adopts the existing schema rather than
      trying to rebuild it. That also covers the half-failed case, where a
      previous upgrade left an empty `alembic_version` table behind.

    Alembic's API is synchronous and its env.py opens its own event loop, so it
    is run in a worker thread - calling `asyncio.run` inside a running loop
    would fail.
    """
    from alembic import command

    tables = await _table_names()
    revision = await _current_revision(tables)
    app_tables = [name for name in tables if name != "alembic_version"]
    cfg = _alembic_config()

    if app_tables and revision is None:
        print(
            f"[db] found {len(app_tables)} existing table(s) with no migration "
            "history; adopting them as the current schema"
        )
        await asyncio.to_thread(command.stamp, cfg, "head")

    await asyncio.to_thread(command.upgrade, cfg, "head")


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
