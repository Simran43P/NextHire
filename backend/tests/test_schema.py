"""
Schema bring-up.

`ensure_schema` has to cope with databases in states nobody planned for,
because all of them happen: a fresh one, an already-migrated one, one built by
an older version of the app that called `create_all()` directly, and one left
half-finished by a migration that failed. The third and fourth are not
hypothetical - they are what this project actually hit.
"""

import sqlite3

import pytest
from sqlalchemy import text

import config
import db as database
from models import Base


def _tables(path) -> set[str]:
    connection = sqlite3.connect(path)
    names = {
        row[0]
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    connection.close()
    return names


def _revision(path) -> str | None:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    except sqlite3.OperationalError:
        row = None
    connection.close()
    return row[0] if row else None


@pytest.fixture
async def db_path(tmp_path, monkeypatch):
    path = tmp_path / "schema.db"
    monkeypatch.setattr(config, "DATABASE_URL", f"sqlite+aiosqlite:///{path}")
    await database.dispose()
    yield path
    await database.dispose()


class TestEnsureSchema:
    async def test_an_empty_database_is_migrated(self, db_path):
        await database.ensure_schema()

        tables = _tables(db_path)
        assert "users" in tables
        assert "ats_analyses" in tables
        assert _revision(db_path) is not None

    async def test_running_twice_is_a_no_op(self, db_path):
        await database.ensure_schema()
        first = _revision(db_path)
        await database.ensure_schema()
        assert _revision(db_path) == first

    async def test_tables_without_migration_history_are_adopted(self, db_path):
        """
        The bug this exists for.

        An older build called `create_all()` on startup, leaving real databases
        with a full schema and no history. `alembic upgrade head` against one of
        those dies with "table users already exists".
        """
        engine = database.get_engine()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        assert _revision(db_path) is None
        assert "users" in _tables(db_path)

        await database.ensure_schema()

        assert _revision(db_path) is not None
        assert "users" in _tables(db_path)

    async def test_an_empty_version_table_is_treated_as_no_history(self, db_path):
        """
        A migration that fails part-way leaves `alembic_version` behind with no
        row in it. Reading that as "already tracked" would turn one failed
        upgrade into a database that can never be upgraded again.
        """
        engine = database.get_engine()
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
            )

        assert "alembic_version" in _tables(db_path)
        assert _revision(db_path) is None

        await database.ensure_schema()

        assert _revision(db_path) is not None

    async def test_the_migration_matches_the_models(self, db_path):
        """
        Every table the code expects is one the migration actually creates.

        Cheap insurance against adding a model and forgetting the migration,
        which fails at runtime rather than at import.
        """
        await database.ensure_schema()

        created = _tables(db_path)
        for table in Base.metadata.tables:
            assert table in created, f"{table} is in the models but not the migration"
