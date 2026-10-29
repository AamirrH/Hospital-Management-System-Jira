"""White-box unit and database tests for SCRUM-11 Appointment Scheduling."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hms.db import (
    appointment_slot_taken,
    create_appointment,
    get_appointment_confirmation,
    get_db,
    get_doctors,
    init_db,
)
from hms.validators import normalize_appointment_data, validate_appointment


VALID_DOCTORS = {"1", "2", "3", "4"}
VALID_SLOTS = {
    f"{hour:02d}:{minute:02d}"
    for hour in range(9, 17)
    for minute in (0, 30)
}
FIXED_TODAY = date(2026, 10, 30)


@pytest.fixture
def appointment_db():
    """Initialize a fresh database and seed three valid registered patients."""
    repo_root = Path(__file__).resolve().parents[1]
    temp_dir = tempfile.mkdtemp(prefix="pytest_appointment_unit_", dir=repo_root)
    database_path = Path(temp_dir) / "appointment_test.db"
    init_db(database_path)
    with get_db(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO patients (name, age, gender, phone, email, address)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("Anita Sharma", 35, "Female", "9200000001", "anita@example.com", "Pune"),
                ("Ravi Kumar", 42, "Male", "9200000002", "ravi@example.com", "Mumbai"),
                ("Meera Nair", 29, "Other", "9200000003", "meera@example.com", "Delhi"),
            ],
        )
    yield database_path


def valid_form(**overrides) -> dict[str, str]:
    data = {
        "patient_id": "1",
        "doctor_id": "1",
        "appointment_date": FIXED_TODAY.isoformat(),
        "time_slot": "09:00",
        "reason": "Consultation",
    }
    data.update(overrides)
    return data


def validate(data: dict[str, str]) -> dict[str, str]:
    return validate_appointment(
        data,
        valid_doctor_ids=VALID_DOCTORS,
        valid_time_slots=VALID_SLOTS,
        today=FIXED_TODAY,
    )


def test_tc_w01_normalize_appointment_data_trims_and_fills_missing_fields():
    """TC-W01: Normalization trims all values and supplies missing fields."""
    normalized = normalize_appointment_data(
        {"patient_id": " 1 ", "doctor_id": " 2 ", "reason": "  Follow up  "}
    )
    assert normalized == {
        "patient_id": "1",
        "doctor_id": "2",
        "appointment_date": "",
        "time_slot": "",
        "reason": "Follow up",
    }


def test_tc_w02_valid_appointment_accepts_today_and_future_dates():
    """TC-W02: Valid data has no errors for today or a future date."""
    assert validate(valid_form()) == {}
    assert validate(valid_form(appointment_date=(FIXED_TODAY + timedelta(days=30)).isoformat())) == {}


def test_tc_w03_patient_id_validation_exercises_required_format_and_lower_bound():
    """TC-W03: Patient ID branches return each required error message."""
    assert validate(valid_form(patient_id=""))["patient_id"] == "Patient ID is required."
    assert validate(valid_form(patient_id="abc"))["patient_id"] == "Patient ID must be a whole number."
    assert validate(valid_form(patient_id="0"))["patient_id"] == "Patient ID must be 1 or greater."


def test_tc_w04_doctor_validation_exercises_required_and_membership_branches():
    """TC-W04: Doctor branches reject missing and unknown doctor IDs."""
    assert validate(valid_form(doctor_id=""))["doctor_id"] == "Doctor is required."
    assert validate(valid_form(doctor_id="999"))["doctor_id"] == "Select a valid doctor."


def test_tc_w05_date_validation_exercises_required_invalid_and_past_branches():
    """TC-W05: Date branches reject missing, malformed, and yesterday values."""
    assert validate(valid_form(appointment_date=""))["appointment_date"] == "Appointment date is required."
    assert validate(valid_form(appointment_date="30/10/2026"))["appointment_date"] == "Enter a valid appointment date."
    yesterday = (FIXED_TODAY - timedelta(days=1)).isoformat()
    assert validate(valid_form(appointment_date=yesterday))["appointment_date"] == "Appointment date cannot be in the past."


def test_tc_w06_time_slot_validation_exercises_required_and_membership_branches():
    """TC-W06: Time-slot branches reject missing and unsupported values."""
    assert validate(valid_form(time_slot=""))["time_slot"] == "Time slot is required."
    assert validate(valid_form(time_slot="08:30"))["time_slot"] == "Select a valid time slot."


def test_tc_w07_reason_boundaries_zero_one_and_two_hundred_are_valid():
    """TC-W07: Reason lengths 0, 1, and 200 are accepted."""
    for reason in ("", "R", "R" * 200):
        assert "reason" not in validate(valid_form(reason=reason))


def test_tc_w08_reason_length_two_hundred_one_is_rejected():
    """TC-W08: Reason length 201 returns the maximum-length error."""
    assert validate(valid_form(reason="R" * 201))["reason"] == "Reason must be 200 characters or fewer."


def test_tc_w09_get_doctors_returns_all_seeded_doctors_in_name_order(appointment_db):
    """TC-W09: get_doctors returns the four schema seeds in name order."""
    doctors = get_doctors(appointment_db)
    assert [(row["name"], row["specialization"]) for row in doctors] == [
        ("Dr. Iyer", "Pediatrician"),
        ("Dr. Khan", "Orthopedic"),
        ("Dr. Mehta", "General Physician"),
        ("Dr. Rao", "Cardiologist"),
    ]


def test_tc_w10_get_doctors_returns_empty_result_when_table_has_no_rows(appointment_db):
    """TC-W10: get_doctors cleanly returns an empty list."""
    with get_db(appointment_db) as connection:
        connection.execute("DELETE FROM doctors")
    assert get_doctors(appointment_db) == []


def test_tc_w11_create_and_confirmation_join_return_exact_details(appointment_db):
    """TC-W11: Insert returns an ID and confirmation joins patient and doctor."""
    appointment_id = create_appointment(
        "1", "1", "2026-11-01", "10:00", "Review", appointment_db
    )
    confirmation = get_appointment_confirmation(appointment_id, appointment_db)
    assert appointment_id == 1
    assert dict(confirmation) == {
        "appointment_id": 1,
        "patient_name": "Anita Sharma",
        "doctor_name": "Dr. Mehta",
        "specialization": "General Physician",
        "appointment_date": "2026-11-01",
        "time_slot": "10:00",
    }


def test_tc_w12_confirmation_lookup_returns_none_for_unknown_id(appointment_db):
    """TC-W12: Confirmation lookup has a clean empty-result path."""
    assert get_appointment_confirmation(9999, appointment_db) is None


def test_tc_w13_conflict_check_returns_false_when_no_appointment_exists(appointment_db):
    """TC-W13: Conflict basis path with no rows returns False."""
    assert appointment_slot_taken("1", "11:00", appointment_db) is False


def test_tc_w14_conflict_check_returns_true_for_same_doctor_date_and_slot(appointment_db):
    """TC-W14: Conflict basis path finds the same doctor/date/slot."""
    create_appointment("1", "2", "2026-11-02", "11:30", "", appointment_db)
    assert appointment_slot_taken("2", "11:30", appointment_db) is True


def test_tc_w15_conflict_check_allows_same_doctor_and_slot_on_different_date(appointment_db):
    """TC-W15: Conflict logic must isolate appointments by date."""
    create_appointment("1", "2", "2026-11-02", "12:00", "", appointment_db)
    conflict_for_2026_11_03 = appointment_slot_taken("2", "12:00", appointment_db)
    assert conflict_for_2026_11_03 is False


def test_tc_w16_conflict_check_allows_different_doctor(appointment_db):
    """TC-W16: Conflict basis path with a different doctor returns False."""
    create_appointment("1", "2", "2026-11-02", "12:30", "", appointment_db)
    assert appointment_slot_taken("3", "12:30", appointment_db) is False


def test_tc_w17_unknown_patient_cannot_be_inserted(appointment_db):
    """TC-W17: Database booking rejects an unregistered Patient ID."""
    with pytest.raises((sqlite3.IntegrityError, ValueError)):
        create_appointment("9999", "1", "2026-11-03", "13:00", "", appointment_db)
    with closing(get_db(appointment_db)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 0


def test_tc_w18_first_and_last_slot_values_round_trip_through_database(appointment_db):
    """TC-W18: Database insert preserves the 09:00 and 16:30 slot boundaries."""
    first_id = create_appointment("1", "1", "2026-11-04", "09:00", "", appointment_db)
    last_id = create_appointment("2", "4", "2026-11-04", "16:30", "", appointment_db)
    with get_db(appointment_db) as connection:
        slots = [row[0] for row in connection.execute(
            "SELECT time_slot FROM appointments ORDER BY appointment_id"
        ).fetchall()]
    assert (first_id, last_id) == (1, 2)
    assert slots == ["09:00", "16:30"]
