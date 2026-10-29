"""Playwright black-box tests for SCRUM-11 Appointment Scheduling."""

from __future__ import annotations

import os
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import pytest
from playwright.sync_api import Page


REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = REPO_ROOT / "docs" / "screenshots"
SEED_PATIENTS = [
    ("Anita Sharma", 35, "Female", "9100000001", "anita@example.com", "12 Lake Road, Pune"),
    ("Ravi Kumar", 42, "Male", "9100000002", "ravi@example.com", "8 MG Road, Mumbai"),
    ("Meera Nair", 29, "Other", "9100000003", "meera@example.com", "21 Park Street, Delhi"),
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="session")
def appointment_server():
    """Run the real HMS package against a disposable initialized database."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for pattern in ("BUG_TC-A*.png", "PASS_TC-A*.png"):
        for screenshot in SCREENSHOT_DIR.glob(pattern):
            screenshot.unlink()

    runtime = Path(tempfile.mkdtemp(prefix="pytest_appointments_", dir=REPO_ROOT))
    copied_package = runtime / "hms"
    shutil.copytree(
        REPO_ROOT / "hms",
        copied_package,
        ignore=shutil.ignore_patterns("hms.db", "__pycache__", "*.pyc"),
    )
    database_path = copied_package / "hms.db"
    schema = (copied_package / "schema.sql").read_text(encoding="utf-8")
    with closing(sqlite3.connect(database_path)) as connection:
        connection.executescript(schema)
        connection.executemany(
            """
            INSERT INTO patients (name, age, gender, phone, email, address)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            SEED_PATIENTS,
        )
        connection.commit()

    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(runtime)
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "flask",
            "--app",
            "hms.app:create_app",
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--no-debugger",
            "--no-reload",
        ],
        cwd=runtime,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        text=True,
    )

    deadline = time.time() + 20
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Flask appointment server exited before startup")
        try:
            with urllib.request.urlopen(f"{base_url}/appointments/book", timeout=1):
                break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("Flask appointment server did not start within 20 seconds")

    yield {"base_url": base_url, "database_path": database_path}

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(autouse=True)
def reset_appointments(appointment_server):
    """Give every black-box case a clean appointment table."""
    with closing(sqlite3.connect(appointment_server["database_path"])) as connection:
        connection.execute("DELETE FROM appointments")
        connection.execute("DELETE FROM sqlite_sequence WHERE name = 'appointments'")
        connection.commit()


@pytest.fixture(autouse=True)
def standard_viewport(page: Page):
    page.set_viewport_size({"width": 1440, "height": 1100})


def day(offset: int = 0) -> str:
    return (date.today() + timedelta(days=offset)).isoformat()


def open_booking(page: Page, server) -> None:
    page.goto(f"{server['base_url']}/appointments/book")


def booking_data(**overrides) -> dict[str, str]:
    data = {
        "patient_id": "1",
        "doctor_id": "1",
        "appointment_date": day(10),
        "time_slot": "10:00",
        "reason": "Routine consultation",
    }
    data.update(overrides)
    return data


def submit_booking(page: Page, server, **overrides) -> None:
    values = booking_data(**overrides)
    open_booking(page, server)
    page.locator("#patient_id").fill(values["patient_id"])
    page.locator("#doctor_id").select_option(values["doctor_id"])
    page.locator("#appointment_date").fill(values["appointment_date"])
    page.locator("#time_slot").select_option(values["time_slot"])
    page.locator("#reason").fill(values["reason"])
    page.get_by_role("button", name="Book Appointment").click()


def submit_raw(page: Page, server, **overrides) -> None:
    """Submit server-side edge cases that HTML attributes would otherwise block."""
    values = booking_data(**overrides)
    open_booking(page, server)
    page.evaluate(
        """values => {
            const form = document.querySelector('form');
            form.noValidate = true;
            for (const [name, value] of Object.entries(values)) {
                const field = form.elements.namedItem(name);
                if (field.tagName === 'SELECT' &&
                    !Array.from(field.options).some(option => option.value === value)) {
                    field.add(new Option(value, value));
                }
                if (field.type === 'number' || field.type === 'date') {
                    field.type = 'text';
                }
                field.removeAttribute('maxlength');
                field.value = value;
            }
            form.submit();
        }""",
        values,
    )
    page.wait_for_load_state("networkidle")


def save_screenshot(page: Page, filename: str) -> str:
    path = SCREENSHOT_DIR / filename
    page.screenshot(path=str(path), full_page=True)
    return f"docs/screenshots/{filename}"


def assert_with_evidence(condition: bool, page: Page, filename: str, message: str) -> None:
    if not condition:
        save_screenshot(page, filename)
    assert condition, message


def appointment_rows(server) -> list[sqlite3.Row]:
    connection = sqlite3.connect(server["database_path"])
    connection.row_factory = sqlite3.Row
    with closing(connection):
        return connection.execute(
            "SELECT * FROM appointments ORDER BY appointment_id"
        ).fetchall()


def test_tc_a01_booking_page_loads_with_seeded_dropdowns(page: Page, appointment_server):
    """TC-A01: GET shows all form fields, four doctors, and 09:00-16:30 slots."""
    open_booking(page, appointment_server)

    assert page.title() == "Book Appointment | HMS"
    assert page.locator("#patient_id").is_visible()
    assert page.locator("#doctor_id option").count() == 5
    assert page.locator("#time_slot option").count() == 17
    assert page.locator("#time_slot option").nth(1).inner_text() == "09:00"
    assert page.locator("#time_slot option").last.inner_text() == "16:30"
    save_screenshot(page, "PASS_TC-A01_booking-page-dropdowns.png")


def test_tc_a02_valid_booking_confirms_and_inserts_exact_row(page: Page, appointment_server):
    """TC-A02: A valid booking succeeds, confirms details, and is stored exactly."""
    submit_booking(page, appointment_server)

    confirmation = page.locator(".success-message")
    assert confirmation.get_by_text("Appointment booked successfully. Appointment ID: 1").is_visible()
    assert confirmation.get_by_text("Patient: Anita Sharma", exact=True).is_visible()
    assert confirmation.get_by_text("Doctor: Dr. Mehta - General Physician", exact=True).is_visible()
    assert confirmation.get_by_text(f"Date: {day(10)}", exact=True).is_visible()
    assert confirmation.get_by_text("Time: 10:00", exact=True).is_visible()
    rows = appointment_rows(appointment_server)
    assert len(rows) == 1
    assert dict(rows[0]) | {} == dict(rows[0])
    assert (rows[0]["patient_id"], rows[0]["doctor_id"], rows[0]["appointment_date"], rows[0]["time_slot"], rows[0]["reason"]) == (1, 1, day(10), "10:00", "Routine consultation")
    save_screenshot(page, "PASS_TC-A02_successful-confirmation.png")


def test_tc_a03_appointment_id_increments(page: Page, appointment_server):
    """TC-A03: A second valid booking receives the next Appointment ID."""
    submit_booking(page, appointment_server, time_slot="10:30")
    assert "Appointment ID: 1" in page.locator(".success-message").inner_text()
    submit_booking(page, appointment_server, doctor_id="2", time_slot="11:00")
    assert "Appointment ID: 2" in page.locator(".success-message").inner_text()
    assert [row["appointment_id"] for row in appointment_rows(appointment_server)] == [1, 2]


def test_tc_a04_today_date_boundary_is_accepted(page: Page, appointment_server):
    """TC-A04: Today's date is accepted at the lower valid boundary."""
    submit_booking(page, appointment_server, appointment_date=day(0), time_slot="11:30")
    assert page.locator(".success-message").is_visible()
    assert f"Date: {day(0)}" in page.locator(".success-message").inner_text()


def test_tc_a05_tomorrow_date_is_accepted(page: Page, appointment_server):
    """TC-A05: A future date is accepted."""
    submit_booking(page, appointment_server, appointment_date=day(1), time_slot="12:00")
    assert page.locator(".success-message").is_visible()
    assert len(appointment_rows(appointment_server)) == 1


def test_tc_a06_yesterday_date_is_rejected(page: Page, appointment_server):
    """TC-A06: Yesterday is rejected as a past appointment date."""
    submit_raw(page, appointment_server, appointment_date=day(-1), time_slot="12:30")

    rejected = page.get_by_text("Appointment date cannot be in the past.", exact=True).count() == 1
    assert_with_evidence(
        rejected and not appointment_rows(appointment_server),
        page,
        "BUG_TC-A06_yesterday-accepted.png",
        "Yesterday was accepted and inserted instead of being rejected.",
    )


def test_tc_a07_invalid_date_format_is_rejected(page: Page, appointment_server):
    """TC-A07: A non-date value produces a clear error and no insert."""
    submit_raw(page, appointment_server, appointment_date="not-a-date", time_slot="13:00")
    assert page.get_by_text("Enter a valid appointment date.", exact=True).is_visible()
    assert not appointment_rows(appointment_server)
    assert_with_evidence(
        page.locator("#appointment_date").input_value() == "not-a-date",
        page,
        "BUG_TC-A07_invalid-date-not-retained.png",
        "The invalid date was rejected but the entered value was not retained.",
    )


def test_tc_a08_empty_optional_reason_is_accepted(page: Page, appointment_server):
    """TC-A08: An empty optional reason is accepted."""
    submit_booking(page, appointment_server, reason="", time_slot="13:30")
    assert page.locator(".success-message").is_visible()
    assert appointment_rows(appointment_server)[0]["reason"] == ""


def test_tc_a09_one_character_reason_is_accepted(page: Page, appointment_server):
    """TC-A09: A one-character reason is accepted."""
    submit_booking(page, appointment_server, reason="A", time_slot="14:00")
    assert page.locator(".success-message").is_visible()
    assert appointment_rows(appointment_server)[0]["reason"] == "A"


def test_tc_a10_two_hundred_character_reason_is_accepted(page: Page, appointment_server):
    """TC-A10: A 200-character reason is accepted at the maximum boundary."""
    reason = "R" * 200
    submit_booking(page, appointment_server, reason=reason, time_slot="14:30")
    assert page.locator(".success-message").is_visible()
    assert appointment_rows(appointment_server)[0]["reason"] == reason


def test_tc_a11_two_hundred_one_character_reason_is_rejected(page: Page, appointment_server):
    """TC-A11: A 201-character reason is rejected above the maximum boundary."""
    submit_raw(page, appointment_server, reason="R" * 201, time_slot="15:00")

    rejected = page.get_by_text("Reason must be 200 characters or fewer.", exact=True).count() == 1
    assert_with_evidence(
        rejected and not appointment_rows(appointment_server),
        page,
        "BUG_TC-A11_reason-201-accepted.png",
        "A 201-character reason was accepted and inserted.",
    )


def test_tc_a12_first_time_slot_boundary_is_accepted(page: Page, appointment_server):
    """TC-A12: The first valid slot 09:00 is accepted."""
    submit_booking(page, appointment_server, time_slot="09:00")
    assert "Time: 09:00" in page.locator(".success-message").inner_text()


def test_tc_a13_last_time_slot_boundary_is_accepted(page: Page, appointment_server):
    """TC-A13: The last valid slot 16:30 is accepted."""
    submit_booking(page, appointment_server, time_slot="16:30")
    assert "Time: 16:30" in page.locator(".success-message").inner_text()


def test_tc_a14_unknown_patient_id_is_rejected(page: Page, appointment_server):
    """TC-A14: A positive but unregistered Patient ID is rejected."""
    submit_booking(page, appointment_server, patient_id="9999", doctor_id="2", time_slot="09:30")

    has_error = page.get_by_text("Patient not found.", exact=True).count() == 1
    assert_with_evidence(
        has_error and not appointment_rows(appointment_server),
        page,
        "BUG_TC-A14_unknown-patient-booked.png",
        "An appointment was inserted for an unregistered Patient ID.",
    )


def test_tc_a15_empty_patient_id_is_rejected_and_retained(page: Page, appointment_server):
    """TC-A15: Empty Patient ID shows the required error and no insert."""
    submit_raw(page, appointment_server, patient_id="", doctor_id="2", time_slot="10:00")
    assert page.get_by_text("Patient ID is required.", exact=True).is_visible()
    assert page.locator("#patient_id").input_value() == ""
    assert not appointment_rows(appointment_server)
    save_screenshot(page, "PASS_TC-A15_validation-error.png")


def test_tc_a16_text_patient_id_is_rejected_and_retained(page: Page, appointment_server):
    """TC-A16: Text Patient ID is rejected as non-whole-number input."""
    submit_raw(page, appointment_server, patient_id="abc", doctor_id="2", time_slot="10:30")
    assert page.get_by_text("Patient ID must be a whole number.", exact=True).is_visible()
    assert not appointment_rows(appointment_server)
    assert_with_evidence(
        page.locator("#patient_id").input_value() == "abc",
        page,
        "BUG_TC-A16_text-patient-id-not-retained.png",
        "The text Patient ID was rejected but the entered value was not retained.",
    )


def test_tc_a17_missing_doctor_is_rejected_and_retained(page: Page, appointment_server):
    """TC-A17: Missing doctor shows a required error and preserves other values."""
    submit_raw(page, appointment_server, doctor_id="", time_slot="11:00")
    assert page.get_by_text("Doctor is required.", exact=True).is_visible()
    assert page.locator("#appointment_date").input_value() == day(10)
    assert not appointment_rows(appointment_server)


def test_tc_a18_missing_time_slot_is_rejected_and_retained(page: Page, appointment_server):
    """TC-A18: Missing time slot shows a required error and preserves other values."""
    submit_raw(page, appointment_server, doctor_id="2", time_slot="")
    assert page.get_by_text("Time slot is required.", exact=True).is_visible()
    assert page.locator("#doctor_id").input_value() == "2"
    assert not appointment_rows(appointment_server)


def test_tc_a19_missing_date_is_rejected_and_retained(page: Page, appointment_server):
    """TC-A19: Missing appointment date shows a required error."""
    submit_raw(page, appointment_server, doctor_id="2", appointment_date="", time_slot="11:30")
    assert page.get_by_text("Appointment date is required.", exact=True).is_visible()
    assert page.locator("#appointment_date").input_value() == ""
    assert not appointment_rows(appointment_server)


def test_tc_a20_same_doctor_date_and_slot_is_rejected(page: Page, appointment_server):
    """TC-A20: A second booking for the same doctor/date/slot is rejected."""
    submit_booking(page, appointment_server, doctor_id="3", appointment_date=day(20), time_slot="12:00")
    assert page.locator(".success-message").is_visible()
    submit_booking(page, appointment_server, patient_id="2", doctor_id="3", appointment_date=day(20), time_slot="12:00")
    assert page.get_by_text("This doctor is already booked for the selected date and time.", exact=True).is_visible()
    assert len(appointment_rows(appointment_server)) == 1


def test_tc_a21_same_doctor_slot_on_different_date_is_allowed(page: Page, appointment_server):
    """TC-A21: The same doctor and slot on a different date is allowed."""
    submit_booking(page, appointment_server, doctor_id="3", appointment_date=day(21), time_slot="12:30")
    assert page.locator(".success-message").is_visible()
    submit_booking(page, appointment_server, patient_id="2", doctor_id="3", appointment_date=day(22), time_slot="12:30")

    allowed = page.locator(".success-message").count() == 1 and len(appointment_rows(appointment_server)) == 2
    assert_with_evidence(
        allowed,
        page,
        "BUG_TC-A21_cross-date-slot-rejected.png",
        "A valid booking on a different date was rejected as a conflict.",
    )


def test_tc_a22_different_doctor_same_date_and_slot_is_allowed(page: Page, appointment_server):
    """TC-A22: Different doctors may use the same date and time slot."""
    submit_booking(page, appointment_server, doctor_id="1", appointment_date=day(23), time_slot="13:00")
    submit_booking(page, appointment_server, patient_id="2", doctor_id="2", appointment_date=day(23), time_slot="13:00")
    assert page.locator(".success-message").is_visible()
    assert len(appointment_rows(appointment_server)) == 2


def test_tc_a23_registered_patient_can_book_and_name_matches(page: Page, appointment_server):
    """TC-A23: A patient registered through the real form can book an appointment."""
    page.goto(f"{appointment_server['base_url']}/patients/register")
    page.locator("#name").fill("Kavya Menon")
    page.locator("#age").fill("31")
    page.locator("#gender").select_option("Female")
    page.locator("#phone").fill("9100000099")
    page.locator("#email").fill("kavya@example.com")
    page.locator("#address").fill("9 River View, Kochi")
    page.get_by_role("button", name="Register Patient").click()
    registration_text = page.locator(".success-message").inner_text()
    patient_id = re.search(r"Patient ID: (\d+)", registration_text).group(1)

    submit_booking(page, appointment_server, patient_id=patient_id, doctor_id="4", time_slot="13:30")
    assert page.get_by_text("Patient: Kavya Menon", exact=True).is_visible()
    assert appointment_rows(appointment_server)[0]["patient_id"] == int(patient_id)


def test_tc_a24_sql_injection_reason_is_stored_safely(page: Page, appointment_server):
    """TC-A24: SQL injection-like Reason text cannot damage database tables."""
    injection = "Robert'); DROP TABLE appointments;--"
    submit_booking(page, appointment_server, doctor_id="4", time_slot="14:00", reason=injection)
    assert page.locator(".success-message").is_visible()
    with closing(sqlite3.connect(appointment_server["database_path"])) as connection:
        stored = connection.execute("SELECT reason FROM appointments").fetchone()[0]
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert stored == injection
    assert {"patients", "doctors", "appointments"}.issubset(tables)


def test_tc_a25_invalid_doctor_value_is_rejected(page: Page, appointment_server):
    """TC-A25: A doctor value outside the seeded list is rejected."""
    submit_raw(page, appointment_server, doctor_id="999", time_slot="14:30")
    assert page.get_by_text("Select a valid doctor.", exact=True).is_visible()
    assert not appointment_rows(appointment_server)
    assert_with_evidence(
        page.locator("#doctor_id").input_value() == "999",
        page,
        "BUG_TC-A25_invalid-doctor-not-retained.png",
        "The invalid doctor value was rejected but the entered value was not retained.",
    )
