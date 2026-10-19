"""Automated tests for SCRUM-7 Patient Registration."""

from __future__ import annotations

import re
import sys
import tempfile
from contextlib import closing, contextmanager
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import hms.app as app_module
from hms.app import create_app
from hms.db import SCHEMA_PATH, get_db
from hms.validators import validate_patient


@pytest.fixture(autouse=True)
def temp_database(monkeypatch):
    """Create and route every test to its own temporary SQLite database."""
    with tempfile.TemporaryDirectory(prefix="pytest_hms_", dir=Path.cwd()) as temp_dir:
        database_path = Path(temp_dir) / "test_hms.db"
        with closing(get_db(database_path)) as schema_connection:
            schema_connection.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        @contextmanager
        def temporary_get_db(db_path=None):
            connection = get_db(database_path)
            try:
                with connection:
                    yield connection
            finally:
                connection.close()

        monkeypatch.setattr(app_module, "get_db", temporary_get_db)
        yield database_path


@pytest.fixture
def client():
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


def patient_data(**overrides):
    data = {
        "name": "Anita Sharma",
        "age": "35",
        "gender": "Female",
        "phone": "9876543210",
        "email": "anita.sharma@example.com",
        "address": "12 Lake Road, Pune",
    }
    data.update(overrides)
    return data


def patient_count(database_path) -> int:
    with closing(get_db(database_path)) as connection:
        return connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0]


def test_tc_01_valid_registration_succeeds(client, temp_database):
    """TC-01: A valid patient is registered and Patient ID 1 is shown."""
    response = client.post("/patients/register", data=patient_data())

    assert response.status_code == 200
    assert b"Patient registered successfully. Patient ID: 1" in response.data
    with closing(get_db(temp_database)) as connection:
        row = connection.execute("SELECT * FROM patients").fetchone()
    assert row is not None
    assert row["name"] == "Anita Sharma"


def test_tc_02_patient_id_increments_for_second_patient(client, temp_database):
    """TC-02: The second valid patient receives the next Patient ID."""
    first = client.post("/patients/register", data=patient_data())
    second = client.post(
        "/patients/register",
        data=patient_data(
            name="Rahul Verma",
            phone="9876543211",
            email="rahul.verma@example.com",
        ),
    )

    assert b"Patient ID: 1" in first.data
    assert b"Patient ID: 2" in second.data
    with closing(get_db(temp_database)) as connection:
        ids = [row[0] for row in connection.execute(
            "SELECT patient_id FROM patients ORDER BY patient_id"
        ).fetchall()]
    assert ids == [1, 2]


def test_tc_03_inserted_row_matches_submitted_data(client, temp_database):
    """TC-03: Stored data exactly matches a successful POST."""
    submitted = patient_data(
        name="Kiran Patel",
        age="42",
        gender="Other",
        phone="9123456780",
        email="kiran.patel@example.org",
        address="44 Market Street, Mumbai",
    )
    response = client.post("/patients/register", data=submitted)

    assert b"Patient registered successfully" in response.data
    with closing(get_db(temp_database)) as connection:
        row = connection.execute(
            "SELECT name, age, gender, phone, email, address FROM patients"
        ).fetchone()
    assert dict(row) == {
        "name": submitted["name"],
        "age": int(submitted["age"]),
        "gender": submitted["gender"],
        "phone": submitted["phone"],
        "email": submitted["email"],
        "address": submitted["address"],
    }


def test_tc_04_duplicate_phone_rejected_without_second_row(client, temp_database):
    """TC-04: A duplicate phone is rejected and creates no second row."""
    client.post("/patients/register", data=patient_data())
    response = client.post(
        "/patients/register",
        data=patient_data(name="Second Person", email="second@example.com"),
    )

    assert b"This phone number is already registered." in response.data
    assert patient_count(temp_database) == 1


def test_tc_05_failed_validation_creates_no_row(client, temp_database):
    """TC-05: A validation failure never inserts a patient row."""
    response = client.post("/patients/register", data=patient_data(age="121"))

    assert b"Age must be between 0 and 120." in response.data
    assert patient_count(temp_database) == 0


def test_tc_06_get_registration_form_loads(client):
    """TC-06: GET /patients/register returns the registration form."""
    response = client.get("/patients/register")

    assert response.status_code == 200
    assert b"Register a New Patient" in response.data
    assert b'<form method="post"' in response.data


def test_tc_07_valid_name_letters_spaces_and_trimmed(client, temp_database):
    """TC-07: A 2-50 character letters/spaces name is accepted after trimming."""
    response = client.post(
        "/patients/register", data=patient_data(name="  Mary Jane Watson  ")
    )

    assert b"Patient registered successfully" in response.data
    with closing(get_db(temp_database)) as connection:
        stored_name = connection.execute("SELECT name FROM patients").fetchone()[0]
    assert stored_name == "Mary Jane Watson"


def test_tc_08_each_required_field_rejects_empty_value(client, temp_database):
    """TC-08: Each required field rejects an empty value."""
    required_errors = {
        "name": "Name is required.",
        "age": "Age is required.",
        "gender": "Gender is required.",
        "phone": "Phone number is required.",
        "address": "Address is required.",
    }

    for field, error in required_errors.items():
        response = client.post(
            "/patients/register", data=patient_data(**{field: ""})
        )
        assert error.encode() in response.data
    assert patient_count(temp_database) == 0


def test_tc_09_whitespace_only_name_is_rejected(client, temp_database):
    """TC-09: A whitespace-only name is treated as empty."""
    response = client.post("/patients/register", data=patient_data(name="    "))

    assert b"Name is required." in response.data
    assert patient_count(temp_database) == 0


def test_tc_10_names_with_digits_or_symbols_are_rejected(client, temp_database):
    """TC-10: Names containing digits or symbols are invalid."""
    for invalid_name in ("John2", "Anne-Marie", "O'Connor", "Ravi!"):
        response = client.post(
            "/patients/register", data=patient_data(name=invalid_name)
        )
        assert b"Name may contain letters and spaces only." in response.data
    assert patient_count(temp_database) == 0


def test_tc_11_name_length_boundaries():
    """TC-11: Name lengths 1/2/50/51 enforce the inclusive 2-50 boundary."""
    expectations = {1: False, 2: True, 50: True, 51: False}

    for length, valid in expectations.items():
        errors = validate_patient(patient_data(name="A" * length))
        assert ("name" not in errors) is valid


def test_tc_12_age_boundaries():
    """TC-12: Ages -1/0/1/119/120/121 enforce the inclusive 0-120 boundary."""
    expectations = {-1: False, 0: True, 1: True, 119: True, 120: True, 121: False}

    for age, valid in expectations.items():
        errors = validate_patient(patient_data(age=str(age)))
        assert ("age" not in errors) is valid


def test_tc_13_age_text_decimal_and_empty_are_rejected():
    """TC-13: Text, decimal, and empty ages are rejected."""
    expected = {
        "thirty": "Age must be a whole number.",
        "35.5": "Age must be a whole number.",
        "": "Age is required.",
    }

    for age, message in expected.items():
        assert validate_patient(patient_data(age=age))["age"] == message


def test_tc_14_all_allowed_gender_values_are_accepted(client, temp_database):
    """TC-14: Male, Female, and Other are valid gender equivalence classes."""
    for index, gender in enumerate(("Male", "Female", "Other")):
        response = client.post(
            "/patients/register",
            data=patient_data(
                name=f"Patient {('One', 'Two', 'Three')[index]}",
                gender=gender,
                phone=f"98765432{index + 20}",
            ),
        )
        assert b"Patient registered successfully" in response.data
    assert patient_count(temp_database) == 3


def test_tc_15_invalid_gender_value_is_rejected(client, temp_database):
    """TC-15: A gender outside Male/Female/Other is rejected."""
    response = client.post("/patients/register", data=patient_data(gender="Unknown"))

    assert b"Gender must be Male, Female, or Other." in response.data
    assert patient_count(temp_database) == 0


def test_tc_16_phone_length_boundaries():
    """TC-16: Phone lengths 9/10/11 enforce exactly 10 digits."""
    expectations = {"123456789": False, "1234567890": True, "12345678901": False}

    for phone, valid in expectations.items():
        errors = validate_patient(patient_data(phone=phone))
        assert ("phone" not in errors) is valid


def test_tc_17_phone_letters_spaces_and_symbols_are_rejected(client, temp_database):
    """TC-17: Phone values containing letters, spaces, or symbols are invalid."""
    for invalid_phone in ("98765abcde", "98765 4321", "98765-4321"):
        response = client.post(
            "/patients/register", data=patient_data(phone=invalid_phone)
        )
        assert b"Phone number must contain exactly 10 digits." in response.data
    assert patient_count(temp_database) == 0


def test_tc_18_valid_email_is_accepted(client, temp_database):
    """TC-18: A syntactically valid optional email is accepted."""
    response = client.post(
        "/patients/register", data=patient_data(email="patient+tag@example.co.in")
    )

    assert b"Patient registered successfully" in response.data
    assert patient_count(temp_database) == 1


def test_tc_19_empty_email_is_accepted(client, temp_database):
    """TC-19: An empty optional email is accepted."""
    response = client.post("/patients/register", data=patient_data(email=""))

    assert b"Patient registered successfully" in response.data
    with closing(get_db(temp_database)) as connection:
        email = connection.execute("SELECT email FROM patients").fetchone()[0]
    assert email == ""


def test_tc_20_invalid_email_examples_are_rejected(client, temp_database):
    """TC-20: abc@, abc.com, and a@b are invalid email formats."""
    for invalid_email in ("abc@", "abc.com", "a@b"):
        response = client.post(
            "/patients/register", data=patient_data(email=invalid_email)
        )
        assert b"Enter a valid email address." in response.data
    assert patient_count(temp_database) == 0


def test_tc_21_address_length_boundaries(client, temp_database):
    """TC-21: Address length 200 is accepted and 201 is rejected."""
    accepted = client.post(
        "/patients/register", data=patient_data(address="A" * 200)
    )
    rejected = client.post(
        "/patients/register",
        data=patient_data(phone="9876543211", address="A" * 201),
    )

    assert b"Patient registered successfully" in accepted.data
    assert b"Address must be 200 characters or fewer." in rejected.data
    assert patient_count(temp_database) == 1


def test_tc_22_sql_injection_in_name_is_rejected_and_table_survives(
    client, temp_database
):
    """TC-22: A SQL injection string in name cannot damage the patients table."""
    injection = "Robert'); DROP TABLE patients;--"
    response = client.post("/patients/register", data=patient_data(name=injection))

    assert b"Name may contain letters and spaces only." in response.data
    with closing(get_db(temp_database)) as connection:
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='patients'"
        ).fetchone()
    assert table is not None
    assert patient_count(temp_database) == 0


def test_tc_23_sql_injection_in_address_is_stored_safely(
    client, temp_database
):
    """TC-23: SQL text in address is data and cannot damage the patients table."""
    injection = "Robert'); DROP TABLE patients;--"
    response = client.post(
        "/patients/register", data=patient_data(address=injection)
    )

    assert b"Patient registered successfully" in response.data
    with closing(get_db(temp_database)) as connection:
        row = connection.execute("SELECT address FROM patients").fetchone()
        table = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='patients'"
        ).fetchone()
    assert row["address"] == injection
    assert table is not None


def test_tc_24_representative_valid_age_partition():
    """TC-24: A representative whole-number age within range is valid."""
    assert "age" not in validate_patient(patient_data(age="35"))


def test_tc_25_representative_valid_phone_partition():
    """TC-25: A representative exactly-10-digit phone is valid."""
    assert "phone" not in validate_patient(patient_data(phone="8765432109"))


def test_tc_26_representative_valid_address_partition():
    """TC-26: A non-empty address below 200 characters is valid."""
    assert "address" not in validate_patient(
        patient_data(address="7 Green Park, New Delhi")
    )


def test_tc_27_valid_other_gender_and_empty_email_combination(client, temp_database):
    """TC-27: Valid partitions can be combined in one successful registration."""
    response = client.post(
        "/patients/register",
        data=patient_data(gender="Other", email="", age="0"),
    )

    assert b"Patient registered successfully. Patient ID: 1" in response.data
    assert patient_count(temp_database) == 1


def test_tc_28_validation_response_preserves_entered_values(client, temp_database):
    """TC-28: A rejected form shows its error and preserves other entered values."""
    response = client.post(
        "/patients/register",
        data=patient_data(name="Meera Nair", email="abc@"),
    )

    body = response.get_data(as_text=True)
    assert "Enter a valid email address." in body
    assert 'value="Meera Nair"' in body
    assert 'value="abc@"' in body
    assert patient_count(temp_database) == 0


def test_tc_29_created_at_is_populated_after_registration(client, temp_database):
    """TC-29: A successful insert populates the schema's created_at field."""
    response = client.post("/patients/register", data=patient_data())

    assert re.search(rb"Patient ID: 1", response.data)
    with closing(get_db(temp_database)) as connection:
        created_at = connection.execute("SELECT created_at FROM patients").fetchone()[0]
    assert created_at is not None
