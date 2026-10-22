"""Playwright acceptance tests for SCRUM-9 Patient Search."""

from __future__ import annotations

import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path

import pytest
from playwright.sync_api import Page


REPO_ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_DIR = REPO_ROOT / "docs" / "screenshots"
LONG_NAME = "A" * 50
SEED_PATIENTS = [
    ("Ravi Kumar", 34, "Male", "9000000001", "ravi@example.com", "12 MG Road, Pune"),
    ("Priya Sharma", 29, "Female", "9000000002", "priya@example.com", "21 Park Street, Delhi"),
    ("Anil Kumar", 41, "Male", "9000000003", "anil@example.com", "8 Lake View, Mumbai"),
    ("ravi singh", 26, "Other", "9000000004", "ravi.singh@example.com", "5 Hill Road, Jaipur"),
    ("Sneha Patil", 37, "Female", "9000000005", "sneha@example.com", "44 Station Road, Nashik"),
    (LONG_NAME, 52, "Male", "9000000006", "long.name@example.com", "50 Boundary Lane, Pune"),
]


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


@pytest.fixture(scope="session")
def search_server():
    """Run a copied HMS package against a seeded disposable SQLite database."""
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for screenshot in SCREENSHOT_DIR.glob("*.png"):
        screenshot.unlink()

    runtime = Path(tempfile.mkdtemp(prefix="pytest_search_", dir=REPO_ROOT))
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
            raise RuntimeError("Flask server exited before startup")
        try:
            with urllib.request.urlopen(f"{base_url}/patients/search", timeout=1):
                break
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("Flask server did not start within 20 seconds")

    yield {"base_url": base_url, "database_path": database_path}

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    shutil.rmtree(runtime)


@pytest.fixture(autouse=True)
def standard_viewport(page: Page):
    page.set_viewport_size({"width": 1440, "height": 1000})


def open_search(page: Page, search_server) -> None:
    page.goto(f"{search_server['base_url']}/patients/search")


def submit_search(page: Page, search_server, patient_id: str = "", name: str = "") -> None:
    open_search(page, search_server)
    if patient_id:
        page.locator("#patient_id").fill(patient_id)
    if name:
        page.locator("#name").fill(name)
    page.get_by_role("button", name="Search").click()


def open_query(page: Page, search_server, patient_id: str = "", name: str = "") -> None:
    query = urllib.parse.urlencode({"patient_id": patient_id, "name": name})
    page.goto(f"{search_server['base_url']}/patients/search?{query}")


def result_names(page: Page) -> list[str]:
    return page.locator("tbody tr td:nth-child(2)").all_inner_texts()


def save_screenshot(page: Page, filename: str) -> str:
    path = SCREENSHOT_DIR / filename
    page.screenshot(path=str(path), full_page=True)
    return f"docs/screenshots/{filename}"


def assert_with_bug_evidence(condition: bool, page: Page, filename: str, message: str) -> None:
    if not condition:
        save_screenshot(page, filename)
    assert condition, message


def test_tc_s01_search_page_loads_with_empty_results(page: Page, search_server):
    """TC-S01: Initial GET shows the form and no results area."""
    open_search(page, search_server)

    assert page.title() == "Search Patients | HMS"
    assert page.locator("#patient_id").is_visible()
    assert page.locator("#name").is_visible()
    assert page.get_by_role("button", name="Search").is_visible()
    assert page.locator(".search-results").count() == 0
    save_screenshot(page, "TC-S-UI-1_search-page-loads.png")


def test_tc_s02_search_by_existing_id(page: Page, search_server):
    """TC-S02: An existing valid Patient ID returns its patient."""
    submit_search(page, search_server, patient_id="1")

    assert result_names(page) == ["Ravi Kumar"]
    assert page.locator("tbody tr").count() == 1
    save_screenshot(page, "TC-S-UI-2_successful-result-table.png")


def test_tc_s03_search_by_full_name(page: Page, search_server):
    """TC-S03: A full name returns the matching patient."""
    submit_search(page, search_server, name="Priya Sharma")

    assert result_names(page) == ["Priya Sharma"]


def test_tc_s04_search_by_partial_name(page: Page, search_server):
    """TC-S04: A partial name returns every matching patient."""
    submit_search(page, search_server, name="Kum")

    assert result_names(page) == ["Ravi Kumar", "Anil Kumar"]


def test_tc_s05_search_by_both_matching_fields(page: Page, search_server):
    """TC-S05: ID and name together return only a patient matching both."""
    submit_search(page, search_server, patient_id="1", name="Kumar")

    assert result_names(page) == ["Ravi Kumar"]


def test_tc_s06_search_by_both_nonmatching_fields(page: Page, search_server):
    """TC-S06: Valid ID and name that do not match the same row return no patients."""
    submit_search(page, search_server, patient_id="1", name="Priya")

    assert page.get_by_text("No patients found.", exact=True).is_visible()
    assert page.locator("tbody tr").count() == 0


def test_tc_s07_no_match_message(page: Page, search_server):
    """TC-S07: A valid search with no match shows the required message."""
    submit_search(page, search_server, name="ZzNotFound")

    assert page.get_by_text("No patients found.", exact=True).is_visible()
    save_screenshot(page, "TC-S-UI-3_no-patients-found.png")


def test_tc_s08_valid_id_equivalence_class(page: Page, search_server):
    """TC-S08: A positive whole-number ID is accepted."""
    submit_search(page, search_server, patient_id="5")

    assert result_names(page) == ["Sneha Patil"]
    assert page.locator(".field-error").count() == 0


def test_tc_s09_text_id_is_rejected(page: Page, search_server):
    """TC-S09: Text Patient ID is rejected with a clear error and retained input."""
    open_query(page, search_server, patient_id="abc")

    assert page.get_by_text("Patient ID must be a whole number.", exact=True).is_visible()
    assert page.locator("#patient_id").get_attribute("value") == "abc"
    assert page.locator("table").count() == 0


def test_tc_s10_decimal_id_is_rejected(page: Page, search_server):
    """TC-S10: Decimal Patient ID is rejected with a clear error and retained input."""
    open_query(page, search_server, patient_id="1.5")

    assert page.get_by_text("Patient ID must be a whole number.", exact=True).is_visible()
    assert page.locator("#patient_id").get_attribute("value") == "1.5"


def test_tc_s11_negative_id_boundary_is_rejected(page: Page, search_server):
    """TC-S11: Patient ID -1 is rejected at the lower boundary."""
    open_query(page, search_server, patient_id="-1")

    assert page.get_by_text("Patient ID must be 1 or greater.", exact=True).is_visible()
    assert page.locator("#patient_id").get_attribute("value") == "-1"
    save_screenshot(page, "TC-S-UI-4_working-validation-error.png")


def test_tc_s12_zero_id_boundary_is_rejected(page: Page, search_server):
    """TC-S12: Patient ID 0 is rejected at the lower boundary."""
    open_query(page, search_server, patient_id="0")

    has_error = page.get_by_text("Patient ID must be 1 or greater.", exact=True).count() == 1
    assert_with_bug_evidence(
        has_error,
        page,
        "BUG_TC-S12_zero-id-accepted.png",
        "Patient ID 0 was accepted instead of producing a validation error.",
    )


def test_tc_s13_id_one_boundary_is_accepted(page: Page, search_server):
    """TC-S13: Patient ID 1 is accepted at the valid lower boundary."""
    submit_search(page, search_server, patient_id="1")

    assert result_names(page) == ["Ravi Kumar"]
    assert page.locator(".field-error").count() == 0


def test_tc_s14_very_large_id_is_valid_but_has_no_match(page: Page, search_server):
    """TC-S14: A very large positive whole-number ID is valid and returns no match."""
    submit_search(page, search_server, patient_id="999999999999999999")

    assert page.get_by_text("No patients found.", exact=True).is_visible()
    assert page.locator(".field-error").count() == 0


def test_tc_s15_one_character_name_is_rejected(page: Page, search_server):
    """TC-S15: A one-character name is rejected below the minimum boundary."""
    open_query(page, search_server, name="R")

    assert page.get_by_text("Name must be between 2 and 50 characters.", exact=True).is_visible()
    assert page.locator("#name").input_value() == "R"


def test_tc_s16_two_character_name_is_accepted(page: Page, search_server):
    """TC-S16: A two-character name is accepted at the minimum boundary."""
    submit_search(page, search_server, name="An")

    assert result_names(page) == ["Anil Kumar"]
    assert page.locator(".field-error").count() == 0


def test_tc_s17_fifty_character_name_is_accepted(page: Page, search_server):
    """TC-S17: A 50-character name is accepted at the maximum boundary."""
    submit_search(page, search_server, name=LONG_NAME)

    assert result_names(page) == [LONG_NAME]
    assert page.locator(".field-error").count() == 0


def test_tc_s18_fifty_one_character_name_is_rejected(page: Page, search_server):
    """TC-S18: A 51-character name is rejected above the maximum boundary."""
    invalid_name = "A" * 51
    open_query(page, search_server, name=invalid_name)

    has_error = page.get_by_text("Name must be between 2 and 50 characters.", exact=True).count() == 1
    assert_with_bug_evidence(
        has_error,
        page,
        "BUG_TC-S18_name-51-accepted.png",
        "A 51-character name was accepted instead of producing a validation error.",
    )


def test_tc_s19_both_fields_empty_are_rejected(page: Page, search_server):
    """TC-S19: Submitting both fields empty shows an at-least-one-field error."""
    submit_search(page, search_server)

    has_error = page.locator(".field-error").count() > 0
    assert_with_bug_evidence(
        has_error,
        page,
        "BUG_TC-S19_empty-search-returns-all.png",
        "An empty search returned patient records instead of a validation error.",
    )


def test_tc_s20_whitespace_only_name_is_rejected(page: Page, search_server):
    """TC-S20: Whitespace-only name is empty after trimming and requires a criterion."""
    open_query(page, search_server, name="   ")

    has_error = page.locator(".field-error").count() > 0
    assert_with_bug_evidence(
        has_error,
        page,
        "BUG_TC-S20_whitespace-search-returns-all.png",
        "A whitespace-only search returned patient records instead of a validation error.",
    )


def test_tc_s21_empty_id_with_valid_name_is_allowed(page: Page, search_server):
    """TC-S21: Empty ID is allowed when a valid name criterion is supplied."""
    submit_search(page, search_server, name="Sneha")

    assert result_names(page) == ["Sneha Patil"]
    assert page.locator(".field-error").count() == 0


def test_tc_s22_lowercase_name_search_is_case_insensitive(page: Page, search_server):
    """TC-S22: Lowercase 'ravi' finds names regardless of stored case."""
    submit_search(page, search_server, name="ravi")

    names = result_names(page)
    correct = names == ["Ravi Kumar", "ravi singh"]
    assert_with_bug_evidence(
        correct,
        page,
        "BUG_TC-S22_lowercase-search-case-sensitive.png",
        f"Expected both Ravi records, but displayed {names}.",
    )


def test_tc_s23_uppercase_name_search_is_case_insensitive(page: Page, search_server):
    """TC-S23: Uppercase 'RAVI' finds names regardless of stored case."""
    submit_search(page, search_server, name="RAVI")

    names = result_names(page)
    correct = names == ["Ravi Kumar", "ravi singh"]
    assert_with_bug_evidence(
        correct,
        page,
        "BUG_TC-S23_uppercase-search-case-sensitive.png",
        f"Expected both Ravi records, but displayed {names}.",
    )


def test_tc_s24_titlecase_name_search_is_case_insensitive(page: Page, search_server):
    """TC-S24: Title-case 'Ravi' finds names regardless of stored case."""
    submit_search(page, search_server, name="Ravi")

    names = result_names(page)
    correct = names == ["Ravi Kumar", "ravi singh"]
    assert_with_bug_evidence(
        correct,
        page,
        "BUG_TC-S24_titlecase-search-case-sensitive.png",
        f"Expected both Ravi records, but displayed {names}.",
    )


def test_tc_s25_percent_is_treated_as_literal_text(page: Page, search_server):
    """TC-S25: SQL percent wildcard input is safely treated as literal text."""
    open_query(page, search_server, name="%")

    assert page.get_by_text("Name must be between 2 and 50 characters.", exact=True).is_visible()
    assert page.locator("table").count() == 0


def test_tc_s26_underscore_is_treated_as_literal_text(page: Page, search_server):
    """TC-S26: SQL underscore wildcard input is safely treated as literal text."""
    open_query(page, search_server, name="__")

    assert page.get_by_text("No patients found.", exact=True).is_visible()
    assert page.locator("tbody tr").count() == 0


def test_tc_s27_sql_injection_text_does_not_break_database(page: Page, search_server):
    """TC-S27: SQL injection-like name input causes no crash or database damage."""
    attack = "Robert'); DROP TABLE patients;--"
    open_query(page, search_server, name=attack)

    assert page.get_by_text("No patients found.", exact=True).is_visible()
    assert page.locator("#name").input_value() == attack
    with closing(sqlite3.connect(search_server["database_path"])) as connection:
        count = connection.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
    assert count == 6


def test_tc_s28_displayed_result_matches_database(page: Page, search_server):
    """TC-S28: Every displayed field exactly matches the stored database row."""
    submit_search(page, search_server, patient_id="2")

    displayed = page.locator("tbody tr").first.locator("td").all_inner_texts()
    with closing(sqlite3.connect(search_server["database_path"])) as connection:
        stored = connection.execute(
            """
            SELECT patient_id, name, age, gender, phone, email, address
            FROM patients WHERE patient_id = 2
            """
        ).fetchone()
    expected = [str(value) for value in stored]
    assert displayed == expected
