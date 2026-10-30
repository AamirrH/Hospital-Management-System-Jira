"""Flask application entry point for the Hospital Management System."""

import sqlite3
from datetime import date

from flask import Flask, render_template, request

from .db import (
    appointment_slot_taken,
    create_appointment,
    get_appointment_confirmation,
    get_db,
    get_doctors,
    init_db,
    search_patients,
)
from .validators import (
    normalize_appointment_data,
    normalize_patient_data,
    validate_appointment,
    validate_patient,
    validate_search,
)


TIME_SLOTS = [
    f"{hour:02d}:{minute:02d}"
    for hour in range(9, 17)
    for minute in (0, 30)
]


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "development-only-secret"

    @app.route("/")
    def index() -> str:
        return "Hospital Management System"

    @app.route("/patients/register", methods=["GET", "POST"])
    def register_patient():
        form_data = {
            "name": "",
            "age": "",
            "gender": "",
            "phone": "",
            "email": "",
            "address": "",
        }

        if request.method == "POST":
            form_data = normalize_patient_data(request.form)
            with get_db() as connection:
                phone_exists = connection.execute(
                    "SELECT 1 FROM patients WHERE phone = ?", (form_data["phone"],)
                ).fetchone() is not None

            errors = validate_patient(form_data, phone_exists=phone_exists)
            if errors:
                return render_template(
                    "register_patient.html", form_data=form_data, errors=errors
                )

            try:
                with get_db() as connection:
                    cursor = connection.execute(
                        """
                        INSERT INTO patients (name, age, gender, phone, email, address)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            form_data["name"],
                            form_data["age"],
                            form_data["gender"],
                            form_data["phone"],
                            form_data["email"],
                            form_data["address"],
                        ),
                    )
                return render_template(
                    "register_patient.html",
                    form_data=form_data,
                    success_message=f"Patient registered successfully. Patient ID: {cursor.lastrowid}",
                )
            except sqlite3.IntegrityError:
                return render_template(
                    "register_patient.html",
                    form_data=form_data,
                    errors={"phone": "This phone number is already registered."},
                )

        return render_template("register_patient.html", form_data=form_data)

    @app.route("/patients/search")
    def search_patient():
        form_data = {
            "patient_id": request.args.get("patient_id", "").strip(),
            "name": request.args.get("name", "").strip(),
        }
        search_performed = "patient_id" in request.args or "name" in request.args
        results = []
        errors = {}
        if search_performed:
            errors = validate_search(form_data["patient_id"], form_data["name"])
            if not errors:
                results = search_patients(form_data["patient_id"], form_data["name"])

        return render_template(
            "search_patient.html",
            form_data=form_data,
            results=results,
            errors=errors,
            search_performed=search_performed,
        )

    @app.route("/appointments/book", methods=["GET", "POST"])
    def book_appointment():
        doctors = get_doctors()
        form_data = {
            "patient_id": "",
            "doctor_id": "",
            "appointment_date": "",
            "time_slot": "",
            "reason": "",
        }
        errors = {}
        confirmation = None

        if request.method == "POST":
            form_data = normalize_appointment_data(request.form)
            errors = validate_appointment(
                form_data,
                valid_doctor_ids={str(doctor["doctor_id"]) for doctor in doctors},
                valid_time_slots=set(TIME_SLOTS),
                today=date.today(),
            )
            if not errors and appointment_slot_taken(
                form_data["doctor_id"],
                form_data["time_slot"],
                appointment_date=form_data["appointment_date"],
            ):
                errors["time_slot"] = (
                    "This doctor is already booked for the selected date and time."
                )

            if not errors:
                try:
                    appointment_id = create_appointment(
                        form_data["patient_id"],
                        form_data["doctor_id"],
                        form_data["appointment_date"],
                        form_data["time_slot"],
                        form_data["reason"],
                    )
                    confirmation = get_appointment_confirmation(appointment_id)
                except ValueError as error:
                    errors["patient_id"] = str(error)
                except sqlite3.DatabaseError:
                    errors["form"] = (
                        "Unable to book the appointment. Please try again."
                    )

        return render_template(
            "book_appointment.html",
            form_data=form_data,
            doctors=doctors,
            time_slots=TIME_SLOTS,
            min_date=date.today().isoformat(),
            errors=errors,
            confirmation=confirmation,
        )

    return app


if __name__ == "__main__":
    init_db()
    create_app().run(debug=True)
