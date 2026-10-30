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


def create_appointment(
    patient_id: str,
    doctor_id: str,
    appointment_date: str,
    time_slot: str,
    reason: str,
    db_path: str | Path | None = None,
) -> int:
    """Insert an appointment and return its generated ID."""
    with get_db(db_path) as connection:
        patient_exists = connection.execute(
            "SELECT 1 FROM patients WHERE patient_id = ?", (patient_id,)
        ).fetchone()
        if patient_exists is None:
            raise ValueError("Patient not found.")

        cursor = connection.execute(
            """
            INSERT INTO appointments (
                patient_id, doctor_id, appointment_date, time_slot, reason
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (patient_id, doctor_id, appointment_date, time_slot, reason),
        )
        return int(cursor.lastrowid)


def get_appointment_confirmation(
    appointment_id: int, db_path: str | Path | None = None
) -> sqlite3.Row | None:
    """Return confirmation details for one appointment."""
    with get_db(db_path) as connection:
        return connection.execute(
            """
            SELECT
                a.appointment_id,
                p.name AS patient_name,
                d.name AS doctor_name,
                d.specialization,
                a.appointment_date,
                a.time_slot
            FROM appointments AS a
            LEFT JOIN patients AS p ON p.patient_id = a.patient_id
            LEFT JOIN doctors AS d ON d.doctor_id = a.doctor_id
            WHERE a.appointment_id = ?
            """,
            (appointment_id,),
        ).fetchone()


def appointment_slot_taken(
    doctor_id: str,
    time_slot: str,
    db_path: str | Path | None = None,
) -> bool:
    """Return whether the selected doctor already has the requested slot."""
    with get_db(db_path) as connection:
        return connection.execute(
            """
            SELECT 1
            FROM appointments
            WHERE doctor_id = ? AND time_slot = ?
            LIMIT 1
            """,
            (doctor_id, time_slot),
        ).fetchone() is not None


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
