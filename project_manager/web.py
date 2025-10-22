"""Simple Flask-based web interface for the personal project manager."""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, UTC
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
            now=datetime.now(UTC),
        )

    @app.post("/fetch")
    def fetch_emails():
        """Fetch emails from all configured email sources."""
        max_per_source = int(request.form.get("max", 10))

        try:
            ingested = manager.fetch_from_all_sources(max_per_source=max_per_source)

            if not ingested:
                flash("No new emails found from configured sources.", "info")
            else:
                flash(f"Fetched {len(ingested)} new email(s) ready for triage.", "success")

        except Exception as e:
            flash(f"Error fetching emails: {e}", "error")

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

        remind_at = datetime.now(UTC) + delta
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

    @app.get("/projects/<int:project_id>")
    def project_detail(project_id: int):
        project = manager.get_project(project_id)
        if project is None:
            flash("Project not found.", "error")
            return redirect(url_for("list_projects"))

        emails = manager.get_emails_by_project(project_id)

        # Get email content if an email_id is specified
        selected_email_id = request.args.get("email_id", type=int)
        email_content = None
        content_type = "text"
        if selected_email_id:
            result = manager.get_email_content(selected_email_id)
            if result:
                email_content, content_type = result

        return render_template(
            "project_detail.html",
            project=project,
            emails=emails,
            selected_email_id=selected_email_id,
            email_content=email_content,
            content_type=content_type
        )

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

    @app.get("/contacts")
    def list_contacts():
        """List all contacts."""
        contacts = manager.list_contacts()
        return render_template("contacts.html", contacts=contacts)

    @app.get("/contacts/<int:contact_id>")
    def contact_detail(contact_id: int):
        """Show contact detail with communications grouped by project."""
        contact = manager.get_contact(contact_id)
        if contact is None:
            flash("Contact not found.", "error")
            return redirect(url_for("list_contacts"))

        # Get communications grouped by project
        grouped_comms = manager.get_contact_communications(contact_id, group_by_project=True)

        # Get email content if specified
        selected_comm_id = request.args.get("comm_id", type=int)
        comm_content = None
        content_type = "text"
        if selected_comm_id:
            # Find the communication in grouped_comms
            for project_data in grouped_comms.values():
                for comm in project_data["communications"]:
                    if comm.id == selected_comm_id and comm.type == "email" and comm.raw_path:
                        result = manager.get_email_content(selected_comm_id)
                        if result:
                            comm_content, content_type = result
                        break

        return render_template(
            "contact_detail.html",
            contact=contact,
            grouped_communications=grouped_comms,
            selected_comm_id=selected_comm_id,
            comm_content=comm_content,
            content_type=content_type
        )

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
