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


def get_doctors(db_path: str | Path | None = None) -> list[sqlite3.Row]:
    """Return all doctors ordered by name."""
    with get_db(db_path) as connection:
        return connection.execute(
            """
            SELECT doctor_id, name, specialization
            FROM doctors
            ORDER BY name
            """
        ).fetchall()


def search_patients(
    patient_id: str = "", name: str = "", db_path: str | Path | None = None
) -> list[sqlite3.Row]:
    """Return patients matching the supplied ID and name filters."""
    clauses: list[str] = []
    parameters: list[str] = []

    if patient_id:
        clauses.append("patient_id = ?")
        parameters.append(patient_id)

    if name:
        clauses.append("instr(lower(name), lower(?)) > 0")
        parameters.append(name)

    query = """
        SELECT patient_id, name, age, gender, phone, email, address
        FROM patients
    """
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY patient_id"

    with get_db(db_path) as connection:
        return connection.execute(query, parameters).fetchall()


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DATABASE_PATH}")
