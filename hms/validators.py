"""Pure input validation functions for HMS forms."""

from __future__ import annotations

import re
from collections.abc import Mapping


NAME_PATTERN = re.compile(r"^[A-Za-z ]+$")
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
VALID_GENDERS = {"Male", "Female", "Other"}
PATIENT_FIELDS = ("name", "age", "gender", "phone", "email", "address")


def normalize_patient_data(data: Mapping[str, str]) -> dict[str, str]:
    """Return patient form values with leading and trailing whitespace removed."""
    return {field: str(data.get(field, "")).strip() for field in PATIENT_FIELDS}


def validate_patient(data: Mapping[str, str], *, phone_exists: bool = False) -> dict[str, str]:
    """Validate patient details and return a mapping of field names to errors."""
    values = normalize_patient_data(data)
    errors: dict[str, str] = {}

    name = values["name"]
    if not name:
        errors["name"] = "Name is required."
    elif not 2 <= len(name) <= 50:
        errors["name"] = "Name must be between 2 and 50 characters."
    elif not NAME_PATTERN.fullmatch(name):
        errors["name"] = "Name may contain letters and spaces only."

    age = values["age"]
    if not age:
        errors["age"] = "Age is required."
    elif not re.fullmatch(r"[+-]?\d+", age):
        errors["age"] = "Age must be a whole number."
    elif not 0 <= int(age) <= 120:
        errors["age"] = "Age must be between 0 and 120."

    gender = values["gender"]
    if not gender:
        errors["gender"] = "Gender is required."
    elif gender not in VALID_GENDERS:
        errors["gender"] = "Gender must be Male, Female, or Other."

    phone = values["phone"]
    if not phone:
        errors["phone"] = "Phone number is required."
    elif not re.fullmatch(r"\d{10}", phone):
        errors["phone"] = "Phone number must contain exactly 10 digits."
    elif phone_exists:
        errors["phone"] = "This phone number is already registered."

    email = values["email"]
    if email and not EMAIL_PATTERN.fullmatch(email):
        errors["email"] = "Enter a valid email address."

    address = values["address"]
    if not address:
        errors["address"] = "Address is required."
    elif len(address) > 200:
        errors["address"] = "Address must be 200 characters or fewer."

    return errors


def validate_search(patient_id: str, name: str) -> dict[str, str]:
    """Validate patient search fields and return field-specific errors."""
    patient_id = str(patient_id).strip()
    name = str(name).strip()
    errors: dict[str, str] = {}

    if not patient_id and not name:
        errors["form"] = "Enter a Patient ID or name."

    if patient_id:
        if not re.fullmatch(r"[+-]?\d+", patient_id):
            errors["patient_id"] = "Patient ID must be a whole number."
        elif int(patient_id) < 1:
            errors["patient_id"] = "Patient ID must be 1 or greater."

    if name and not 2 <= len(name) <= 50:
        errors["name"] = "Name must be between 2 and 50 characters."

    return errors
