import os
import hmac
import secrets
import sqlite3
import csv
import io
from datetime import date, datetime, timedelta
from pathlib import Path

from flask import Flask, Response, abort, g, redirect, render_template, request, session, url_for


BASE_DIR = Path(__file__).resolve().parent
DATABASE = Path(os.environ.get("SFLOGS_DATABASE", BASE_DIR / "data" / "sflogs.sqlite3"))
TASK_STATUSES = ("Backlog", "Ready", "In Progress", "Blocked", "Review", "Done")
TASK_PRIORITIES = ("Low", "Medium", "High", "Urgent")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SFLOGS_SECRET_KEY") or None,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("SFLOGS_COOKIE_SECURE", "false").lower() == "true",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
)


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


def auth_is_configured():
    return bool(
        app.config["SECRET_KEY"] and len(app.config["SECRET_KEY"]) >= 32
        and os.environ.get("SFLOGS_USERNAME")
        and os.environ.get("SFLOGS_PASSWORD") and len(os.environ["SFLOGS_PASSWORD"]) >= 12
    )


@app.before_request
def protect_app():
    if request.endpoint in ("static", "healthz"):
        return None
    if not auth_is_configured():
        if request.endpoint == "login":
            return None
        return render_template("login.html", setup_required=True, error=None), 503
    if request.method == "POST":
        submitted_token = request.form.get("csrf_token", "")
        session_token = session.get("csrf_token", "")
        if not submitted_token or not session_token or not hmac.compare_digest(submitted_token, session_token):
            abort(400, "درخواست معتبر نیست؛ صفحه را تازه‌سازی و دوباره تلاش کن")
    if request.endpoint == "login":
        if session.get("authenticated"):
            return redirect(url_for("index"))
        return None
    if not session.get("authenticated"):
        return redirect(url_for("login"))


@app.context_processor
def inject_csrf_token():
    def csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token
    return {"csrf_token": csrf_token}


@app.get("/healthz")
def healthz():
    return "ok", 200


@app.route("/login", methods=["GET", "POST"])
def login():
    if not auth_is_configured():
        return render_template("login.html", setup_required=True, error=None), 503
    error = None
    if request.method == "POST":
        username_ok = hmac.compare_digest(request.form.get("username", ""), os.environ["SFLOGS_USERNAME"])
        password_ok = hmac.compare_digest(request.form.get("password", ""), os.environ["SFLOGS_PASSWORD"])
        if username_ok and password_ok:
            session.clear()
            session["authenticated"] = True
            session.permanent = True
            return redirect(url_for("index"))
        error = "نام کاربری یا گذرواژه درست نیست."
    return render_template("login.html", setup_required=False, error=error)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


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


def report_filters(args):
    today = date.today()
    period = args.get("period", "week")
    if period not in ("week", "month"):
        period = "week"
    default_from = today - timedelta(days=today.weekday()) if period == "week" else today.replace(day=1)
    try:
        date_from = date.fromisoformat(args.get("date_from") or default_from.isoformat())
        date_to = date.fromisoformat(args.get("date_to") or today.isoformat())
    except ValueError:
        abort(400, "فرمت تاریخ معتبر نیست")
    if date_from > date_to:
        abort(400, "تاریخ شروع نباید بعد از تاریخ پایان باشد")
    return {
        "period": period,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "service": args.get("service", "").strip(),
        "environment": args.get("environment", "").strip(),
    }


def filtered_records(db, filters):
    log_conditions = ["work_date >= ?", "work_date <= ?"]
    incident_conditions = ["substr(started_at, 1, 10) >= ?", "substr(started_at, 1, 10) <= ?"]
    log_params = [filters["date_from"], filters["date_to"]]
    incident_params = [filters["date_from"], filters["date_to"]]
    for field in ("service", "environment"):
        if filters[field]:
            log_conditions.append(f"{field} = ?")
            incident_conditions.append(f"{field} = ?")
            log_params.append(filters[field])
            incident_params.append(filters[field])
    logs = db.execute(
        f"SELECT * FROM work_logs WHERE {' AND '.join(log_conditions)} ORDER BY work_date DESC, id DESC",
        log_params,
    ).fetchall()
    incidents = db.execute(
        f"SELECT * FROM incidents WHERE {' AND '.join(incident_conditions)} ORDER BY started_at DESC, id DESC",
        incident_params,
    ).fetchall()
    return logs, incidents


@app.get("/reports")
def reports():
    db = get_db()
    filters = report_filters(request.args)
    logs, incidents = filtered_records(db, filters)
    total_minutes = sum(log["duration_minutes"] or 0 for log in logs)
    resolved_durations = []
    resolution_times = []
    for incident in incidents:
        if incident["resolved_at"]:
            try:
                started = datetime.fromisoformat(incident["started_at"])
                resolved = datetime.fromisoformat(incident["resolved_at"])
                duration = (resolved - started).total_seconds() / 60
                if duration >= 0:
                    resolved_durations.append(duration)
                    resolution_times.append((incident["title"], incident["started_at"][:10], round(duration)))
            except ValueError:
                continue
    by_category = {}
    for log in logs:
        key = log["category"] or "بدون دسته‌بندی"
        current = by_category.setdefault(key, {"count": 0, "minutes": 0})
        current["count"] += 1
        current["minutes"] += log["duration_minutes"] or 0
    by_service = {}
    for incident in incidents:
        key = incident["service"] or "بدون سرویس"
        by_service[key] = by_service.get(key, 0) + 1
    daily_incidents = {}
    for incident in incidents:
        day = incident["started_at"][:10]
        daily_incidents[day] = daily_incidents.get(day, 0) + 1
    max_daily = max(daily_incidents.values(), default=1)
    services = [row[0] for row in db.execute(
        "SELECT service FROM (SELECT service FROM work_logs UNION SELECT service FROM incidents) "
        "WHERE service != '' ORDER BY service"
    ).fetchall()]
    environments = [row[0] for row in db.execute(
        "SELECT environment FROM (SELECT environment FROM work_logs UNION SELECT environment FROM incidents) "
        "WHERE environment != '' ORDER BY environment"
    ).fetchall()]
    return render_template(
        "reports.html", filters=filters, logs=logs, incidents=incidents,
        total_minutes=total_minutes, avg_resolution=sum(resolved_durations) / len(resolved_durations) if resolved_durations else None,
        resolved_count=len(resolved_durations), by_category=by_category, by_service=by_service,
        daily_incidents=sorted(daily_incidents.items()), max_daily=max_daily,
        resolution_times=resolution_times, max_resolution=max(resolved_durations, default=1),
        services=services, environments=environments,
    )


@app.get("/reports/export.csv")
def export_report():
    filters = report_filters(request.args)
    logs, incidents = filtered_records(get_db(), filters)
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["type", "date", "title", "category", "service", "environment", "duration_minutes", "status", "severity", "impact", "root_cause", "resolution", "follow_up"])
    for log in logs:
        writer.writerow(["work_log", log["work_date"], log["title"], log["category"], log["service"], log["environment"], log["duration_minutes"], "", "", "", "", "", ""])
    for incident in incidents:
        duration = ""
        if incident["resolved_at"]:
            try:
                duration = round((datetime.fromisoformat(incident["resolved_at"]) - datetime.fromisoformat(incident["started_at"])).total_seconds() / 60)
            except ValueError:
                pass
        writer.writerow(["incident", incident["started_at"], incident["title"], "", incident["service"], incident["environment"], duration, incident["status"], incident["severity"], incident["impact"], incident["root_cause"], incident["resolution"], incident["follow_up"]])
    content = "\ufeff" + output.getvalue()
    filename = f"sflogs-report-{filters['date_from']}-to-{filters['date_to']}.csv"
    return Response(content, content_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


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
