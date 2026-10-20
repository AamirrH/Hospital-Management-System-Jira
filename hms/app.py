"""Flask application entry point for the Hospital Management System."""

import sqlite3

from flask import Flask, render_template, request

from .db import get_db, init_db
from .validators import normalize_patient_data, validate_patient


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
        return render_template(
            "search_patient.html", form_data={"patient_id": "", "name": ""}
        )

    return app


if __name__ == "__main__":
    init_db()
    create_app().run(debug=True)
