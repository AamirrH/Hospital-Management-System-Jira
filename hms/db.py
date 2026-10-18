"""SQLite connection and database initialization helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path


DATABASE_PATH = Path(__file__).with_name("hms.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def get_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Return a SQLite connection for the HMS database."""
    connection = sqlite3.connect(db_path or DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: str | Path | None = None) -> None:
    """Create the database tables defined in schema.sql."""
    with get_db(db_path) as connection:
        connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DATABASE_PATH}")
