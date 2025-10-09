"""Simple Flask-based web interface for the personal project manager."""
from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for

from .app import ProjectManager, REMINDER_OFFSETS, iter_pending_emails


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(Path(__file__).parent / "templates"),
        static_folder=None,
    )
    app.config["SECRET_KEY"] = os.environ.get("PROJECT_MANAGER_WEB_SECRET", "dev-key")

    manager = ProjectManager()

    @app.context_processor
    def inject_constants():
        return {"REMINDER_OFFSETS": REMINDER_OFFSETS}

    @app.template_filter("parse_iso")
    def parse_iso(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @app.route("/")
    def index():
        emails = iter_pending_emails(manager)
        projects = manager.list_projects()
        return render_template(
            "index.html",
            emails=emails,
            projects=projects,
            now=datetime.utcnow(),
        )

    @app.post("/ingest")
    def ingest_email():
        upload = request.files.get("email_file")
        if upload is None or not upload.filename:
            flash("Please choose an .eml file to upload.", "error")
            return redirect(url_for("index"))

        with tempfile.NamedTemporaryFile(
            delete=False, suffix=Path(upload.filename).suffix or ".eml"
        ) as tmp:
            temp_path = Path(tmp.name)

        upload.save(temp_path)

        try:
            entry = manager.ingest_email_file(temp_path)
        finally:
            temp_path.unlink(missing_ok=True)

        if entry is None:
            flash("Sender is ignored, email was skipped.", "info")
        else:
            flash("Email stored and ready for triage.", "success")
        return redirect(url_for("index"))

    @app.post("/emails/<int:email_id>/assign")
    def assign_email(email_id: int):
        entry = manager.get_email(email_id)
        if entry is None:
            flash("Email could not be found.", "error")
            return redirect(url_for("index"))

        project_id = request.form.get("project_id")
        if not project_id:
            flash("Pick a project to assign the email.", "error")
            return redirect(url_for("index"))

        try:
            project_id_int = int(project_id)
        except ValueError:
            flash("Invalid project selection.", "error")
            return redirect(url_for("index"))

        projects = {project.id: project for project in manager.list_projects()}
        if project_id_int not in projects:
            flash("Selected project no longer exists.", "error")
            return redirect(url_for("index"))

        manager.set_email_project(email_id, project_id_int)
        flash(f"Email assigned to {projects[project_id_int].name}.", "success")
        return redirect(url_for("index"))

    @app.post("/emails/<int:email_id>/create-project")
    def create_project_for_email(email_id: int):
        entry = manager.get_email(email_id)
        if entry is None:
            flash("Email could not be found.", "error")
            return redirect(url_for("index"))

        name = request.form.get("name", "").strip()
        if not name:
            flash("Project name cannot be empty.", "error")
            return redirect(url_for("index"))

        try:
            project = manager.create_project(name)
        except sqlite3.IntegrityError:
            flash("A project with that name already exists.", "error")
            return redirect(url_for("index"))

        manager.set_email_project(email_id, project.id)
        flash(f"Created project '{project.name}' and assigned the email.", "success")
        return redirect(url_for("index"))

    @app.post("/emails/<int:email_id>/snooze")
    def snooze_email(email_id: int):
        entry = manager.get_email(email_id)
        if entry is None:
            flash("Email could not be found.", "error")
            return redirect(url_for("index"))

        interval = request.form.get("interval")
        if interval not in REMINDER_OFFSETS:
            flash("Select how long to snooze the email.", "error")
            return redirect(url_for("index"))

        label, delta = REMINDER_OFFSETS[interval]
        remind_at = datetime.utcnow() + delta
        manager.set_email_snooze(email_id, remind_at)
        flash(
            f"Email snoozed until {remind_at.strftime('%Y-%m-%d %H:%M')} ({label}).",
            "success",
        )
        return redirect(url_for("index"))

    @app.post("/emails/<int:email_id>/ignore")
    def ignore_email(email_id: int):
        entry = manager.get_email(email_id)
        if entry is None:
            flash("Email could not be found.", "error")
            return redirect(url_for("index"))

        if entry.sender:
            manager.ignore_sender(entry.sender)
        manager.set_email_ignored(email_id)
        flash("Sender ignored and email removed from triage.", "success")
        return redirect(url_for("index"))

    @app.get("/projects")
    def list_projects():
        projects = manager.list_projects()
        return render_template("projects.html", projects=projects)

    @app.post("/projects")
    def create_project():
        name = request.form.get("name", "").strip()
        if not name:
            flash("Project name cannot be empty.", "error")
            return redirect(url_for("list_projects"))

        try:
            project = manager.create_project(name)
        except sqlite3.IntegrityError:
            flash("A project with that name already exists.", "error")
            return redirect(url_for("list_projects"))

        flash(f"Project '{project.name}' created.", "success")
        return redirect(url_for("list_projects"))

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
