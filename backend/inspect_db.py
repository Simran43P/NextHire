"""
Look inside the database from the terminal.

    python inspect_db.py                 # row counts for every table
    python inspect_db.py users           # rows in one table
    python inspect_db.py profiles --full # untruncated values
    python inspect_db.py --sql "SELECT email FROM users"

Read-only: the connection is opened in read-only mode, so nothing here can
modify or corrupt the database, and it is safe to run while the server is up.

Password hashes and session tokens are masked. They are already stored hashed -
this only stops them being shoulder-surfed out of a terminal.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import config

MASKED_COLUMNS = {"password_hash", "token_hash"}
DEFAULT_WIDTH = 48


def _db_path() -> Path:
    """Resolve the SQLite file out of the configured DATABASE_URL."""
    url = config.DATABASE_URL
    if "sqlite" not in url:
        print(f"This helper only understands SQLite. DATABASE_URL is: {url}")
        raise SystemExit(2)
    raw = url.split("///", 1)[-1]
    return (Path(__file__).resolve().parent / raw).resolve() if raw.startswith(".") else Path(raw)


def _connect(path: Path) -> sqlite3.Connection:
    # Opened read-only so this can never be the thing that breaks the database.
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _render(value, width: int | None) -> str:
    if value is None:
        return "-"
    text = str(value)
    # JSON columns are stored as text; show them on one line.
    if text.startswith(("{", "[")):
        try:
            text = json.dumps(json.loads(text), separators=(",", ":"))
        except (ValueError, TypeError):
            pass
    text = text.replace("\n", " ").replace("\r", " ")
    if width and len(text) > width:
        return text[: width - 1] + "…"
    return text


def summarise(connection: sqlite3.Connection) -> None:
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    print(f"\n{'table':<22} rows")
    print("-" * 30)
    for table in tables:
        count = connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
        print(f"{table:<22} {count}")
    print(f"\n{len(tables)} tables. Pass a table name to see its rows.\n")


def show_table(connection: sqlite3.Connection, table: str, limit: int, full: bool) -> None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        print(f"No table called {table!r}.")
        raise SystemExit(1)

    rows = connection.execute(f'SELECT * FROM "{table}" LIMIT ?', (limit,)).fetchall()
    if not rows:
        print(f"\n{table} is empty.\n")
        return

    width = None if full else DEFAULT_WIDTH
    print(f"\n{table} - showing {len(rows)} row(s)\n")
    for index, row in enumerate(rows, start=1):
        print(f"  [{index}]")
        for key in row.keys():
            value = "<masked>" if key in MASKED_COLUMNS else _render(row[key], width)
            print(f"    {key:<20} {value}")
        print()


def run_sql(connection: sqlite3.Connection, statement: str, full: bool) -> None:
    try:
        rows = connection.execute(statement).fetchall()
    except sqlite3.Error as exc:
        print(f"SQL error: {exc}")
        raise SystemExit(1)

    if not rows:
        print("\nNo rows.\n")
        return

    width = None if full else DEFAULT_WIDTH
    print()
    for row in rows:
        parts = [
            f"{key}={'<masked>' if key in MASKED_COLUMNS else _render(row[key], width)}"
            for key in row.keys()
        ]
        print("  " + "  ".join(parts))
    print(f"\n{len(rows)} row(s).\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the NextHire database.")
    parser.add_argument("table", nargs="?", help="table to show; omit for a summary")
    parser.add_argument("--limit", type=int, default=20, help="max rows (default 20)")
    parser.add_argument("--full", action="store_true", help="do not truncate values")
    parser.add_argument("--sql", help="run a read-only SQL statement")
    args = parser.parse_args()

    path = _db_path()
    if not path.is_file():
        print(f"No database at {path}. Start the server once and it will be created.")
        return 1

    print(f"{path}  ({path.stat().st_size / 1024:.0f} KB)")

    with _connect(path) as connection:
        if args.sql:
            run_sql(connection, args.sql, args.full)
        elif args.table:
            show_table(connection, args.table, args.limit, args.full)
        else:
            summarise(connection)
    return 0


if __name__ == "__main__":
    sys.exit(main())
