"""Flask application entry point for the Hospital Management System."""

from flask import Flask, render_template

from .db import init_db


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "development-only-secret"

    @app.route("/")
    def index() -> str:
        return "Hospital Management System"

    @app.get("/patients/register")
    def register_patient():
        return render_template("register_patient.html")

    return app


if __name__ == "__main__":
    init_db()
    create_app().run(debug=True)
