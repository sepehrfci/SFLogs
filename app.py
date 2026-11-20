import os
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, abort, g, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("SFLOGS_DATABASE", BASE_DIR / "data" / "sflogs.sqlite3"))
TASK_STATUSES = ("Backlog", "Ready", "In Progress", "Blocked", "Review", "Done")
TASK_PRIORITIES = ("Low", "Medium", "High", "Urgent")

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SFLOGS_SECRET_KEY", "development-only-change-me")


def get_db():
    if "db" not in g:
        DATABASE.parent.mkdir(parents=True, exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    get_db().executescript(
        """
        CREATE TABLE IF NOT EXISTS work_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT 'Operations',
            service TEXT NOT NULL DEFAULT '',
            environment TEXT NOT NULL DEFAULT '',
            duration_minutes INTEGER,
            work_date TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'SEV3',
            status TEXT NOT NULL DEFAULT 'Open',
            service TEXT NOT NULL DEFAULT '',
            environment TEXT NOT NULL DEFAULT '',
            started_at TEXT NOT NULL,
            resolved_at TEXT,
            impact TEXT NOT NULL DEFAULT '',
            root_cause TEXT NOT NULL DEFAULT '',
            resolution TEXT NOT NULL DEFAULT '',
            follow_up TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            details TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'Backlog',
            priority TEXT NOT NULL DEFAULT 'Medium',
            due_date TEXT,
            category TEXT NOT NULL DEFAULT 'Operations',
            service TEXT NOT NULL DEFAULT '',
            environment TEXT NOT NULL DEFAULT '',
            incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    get_db().commit()


@app.before_request
def ensure_schema():
    init_db()


@app.get("/")
def index():
    db = get_db()
    logs = db.execute("SELECT * FROM work_logs ORDER BY work_date DESC, id DESC LIMIT 8").fetchall()
    incidents = db.execute("SELECT * FROM incidents ORDER BY started_at DESC, id DESC LIMIT 8").fetchall()
    counts = {
        "logs": db.execute("SELECT count(*) FROM work_logs").fetchone()[0],
        "open_incidents": db.execute("SELECT count(*) FROM incidents WHERE status != 'Resolved'").fetchone()[0],
        "minutes": db.execute("SELECT coalesce(sum(duration_minutes), 0) FROM work_logs").fetchone()[0],
        "open_tasks": db.execute("SELECT count(*) FROM tasks WHERE status != 'Done'").fetchone()[0],
    }
    tasks = db.execute("SELECT * FROM tasks WHERE status != 'Done' ORDER BY CASE priority WHEN 'Urgent' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, due_date LIMIT 5").fetchall()
    return render_template("index.html", logs=logs, incidents=incidents, tasks=tasks, counts=counts)


@app.route("/tasks", methods=["GET", "POST"])
def tasks():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            abort(400, "عنوان کار الزامی است")
        status = request.form.get("status", "Backlog")
        priority = request.form.get("priority", "Medium")
        if status not in TASK_STATUSES or priority not in TASK_PRIORITIES:
            abort(400, "وضعیت یا اولویت نامعتبر است")
        incident_id = request.form.get("incident_id", "").strip() or None
        if incident_id:
            exists = db.execute("SELECT 1 FROM incidents WHERE id = ?", (incident_id,)).fetchone()
            if exists is None:
                abort(400, "اینسیدنت انتخاب‌شده وجود ندارد")
        db.execute(
            """INSERT INTO tasks (title, details, status, priority, due_date, category,
               service, environment, incident_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (title, request.form.get("details", "").strip(), status, priority,
             request.form.get("due_date", "").strip() or None,
             request.form.get("category", "Operations"), request.form.get("service", "").strip(),
             request.form.get("environment", "").strip(), incident_id),
        )
        db.commit()
        return redirect(url_for("tasks"))
    all_incidents = db.execute("SELECT id, title FROM incidents ORDER BY started_at DESC").fetchall()
    cards = db.execute("SELECT * FROM tasks ORDER BY CASE priority WHEN 'Urgent' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, due_date, id").fetchall()
    prefill_incident = request.args.get("incident_id", "")
    incident = None
    prefill_title = request.args.get("title", "")
    if prefill_incident:
        incident = db.execute("SELECT id, title, follow_up, service, environment FROM incidents WHERE id = ?", (prefill_incident,)).fetchone()
        if incident and not prefill_title:
            prefill_title = incident["follow_up"] or f"پیگیری اینسیدنت: {incident['title']}"
    return render_template("tasks.html", tasks=cards, incidents=all_incidents,
                           statuses=TASK_STATUSES, priorities=TASK_PRIORITIES,
                           prefill_incident=prefill_incident if incident else "",
                           prefill_title=prefill_title,
                           prefill_service=incident["service"] if incident else "",
                           prefill_environment=incident["environment"] if incident else "")


@app.post("/tasks/<int:task_id>/update")
def update_task(task_id):
    db = get_db()
    task = db.execute("SELECT id FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        abort(404)
    status = request.form.get("status", "")
    if status not in TASK_STATUSES:
        abort(400, "وضعیت نامعتبر است")
    db.execute("UPDATE tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (status, task_id))
    db.commit()
    return redirect(url_for("tasks"))


@app.route("/logs", methods=["GET", "POST"])
def logs():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            abort(400, "عنوان کار الزامی است")
        duration = request.form.get("duration_minutes", "").strip()
        db.execute(
            """INSERT INTO work_logs (title, details, category, service, environment,
               duration_minutes, work_date) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, request.form.get("details", "").strip(), request.form.get("category", "Operations"),
             request.form.get("service", "").strip(), request.form.get("environment", "").strip(),
             int(duration) if duration else None, request.form.get("work_date") or datetime.now().date().isoformat()),
        )
        db.commit()
        return redirect(url_for("logs"))
    rows = db.execute("SELECT * FROM work_logs ORDER BY work_date DESC, id DESC").fetchall()
    return render_template("logs.html", logs=rows, today=datetime.now().date().isoformat())


@app.route("/incidents", methods=["GET", "POST"])
def incidents():
    db = get_db()
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            abort(400, "عنوان اینسیدنت الزامی است")
        db.execute(
            """INSERT INTO incidents (title, severity, service, environment, started_at, impact)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, request.form.get("severity", "SEV3"), request.form.get("service", "").strip(),
             request.form.get("environment", "").strip(), request.form.get("started_at") or datetime.now().strftime("%Y-%m-%dT%H:%M"),
             request.form.get("impact", "").strip()),
        )
        db.commit()
        return redirect(url_for("incidents"))
    rows = db.execute("SELECT * FROM incidents ORDER BY started_at DESC, id DESC").fetchall()
    return render_template("incidents.html", incidents=rows, now=datetime.now().strftime("%Y-%m-%dT%H:%M"))


@app.route("/incidents/<int:incident_id>/update", methods=["POST"])
def update_incident(incident_id):
    db = get_db()
    incident = db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,)).fetchone()
    if incident is None:
        abort(404)
    status = request.form.get("status", incident["status"])
    resolved_at = request.form.get("resolved_at", "").strip() or None
    if status == "Resolved" and not resolved_at:
        resolved_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
    if status != "Resolved":
        resolved_at = None
    db.execute(
        """UPDATE incidents SET status=?, resolved_at=?, root_cause=?, resolution=?, follow_up=? WHERE id=?""",
        (status, resolved_at, request.form.get("root_cause", "").strip(), request.form.get("resolution", "").strip(),
         request.form.get("follow_up", "").strip(), incident_id),
    )
    db.commit()
    return redirect(url_for("incidents"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
