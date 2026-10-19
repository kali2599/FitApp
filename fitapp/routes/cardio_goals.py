from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    url_for,
)
import datetime as dt

from ..auth import login_required
from ..db import get_db
from ..utils import goal_progress, to_date, to_float, to_int

bp = Blueprint("cardio_goals", __name__, url_prefix="/cardio-goals")

STATUSES = ["active", "achieved", "abandoned"]


def _library_cardio_exercises(db):
    return db.execute(
        "SELECT name FROM library_exercises "
        "WHERE user_id = ? AND label = 'cardio' ORDER BY name COLLATE NOCASE",
        (g.user["id"],),
    ).fetchall()


def _with_progress(db, goals):
    rows = []
    for goal in goals:
        current, source = _current_value(db, goal)
        rows.append(
            {
                "goal": goal,
                "current": current,
                "source": source,
                "percent": _percent(goal, current),
            }
        )
    return rows


def _current_value(db, goal):
    manual = db.execute(
        "SELECT value FROM cardio_goal_logs WHERE cardio_goal_id = ? AND user_id = ? "
        "ORDER BY logged_date DESC, id DESC LIMIT 1",
        (goal["id"], g.user["id"]),
    ).fetchone()
    if manual is not None and manual["value"] is not None:
        value = to_float(manual["value"])
        if value is not None:
            return (value, "logged progress")
    return (None, None)


def _percent(goal, current):
    if current is None or goal["distance_m"] is None:
        return None
    target = goal["distance_m"]
    if target <= 0:
        return None
    return round(max(0.0, min(150.0, current / target * 100)), 1)


def _parse_form():
    data = {
        "category": request.form.get("category", "").strip(),
        "distance_m": None,
        "time_s": None,
        "pace_km_per_min": None,
        "rounds": None,
        "rest_s": None,
        "target_date": None,
        "status": request.form.get("status", "active").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    errors = []
    if not data["category"]:
        errors.append("Goal category is required.")
    if data["status"] not in STATUSES:
        errors.append("Choose a valid status.")

    try:
        data["distance_m"] = to_float(request.form.get("distance_m"), minimum=0)
    except ValueError as exc:
        errors.append(f"Distance {exc}.")
    if data["distance_m"] is None:
        errors.append("Distance (meters) is required.")

    # Time can be entered in seconds or minutes; store seconds.
    raw_sec = (request.form.get("time_s") or "").strip()
    raw_min = (request.form.get("time_min") or "").strip()
    if raw_sec and raw_min:
        errors.append("Enter time in seconds OR minutes, not both.")
    elif raw_min:
        try:
            minutes = to_float(raw_min, minimum=0)
            if minutes is not None:
                data["time_s"] = int(round(minutes * 60))
        except ValueError as exc:
            errors.append(f"Time {exc}.")
    elif raw_sec:
        try:
            data["time_s"] = to_int(raw_sec, minimum=0)
        except ValueError as exc:
            errors.append(f"Time {exc}.")

    try:
        data["pace_km_per_min"] = to_float(
            request.form.get("pace_km_per_min"), minimum=0
        )
    except ValueError as exc:
        errors.append(f"Pace {exc}.")
    try:
        data["rounds"] = to_int(request.form.get("rounds"), minimum=0)
    except ValueError as exc:
        errors.append(f"Rounds {exc}.")
    try:
        data["rest_s"] = to_int(request.form.get("rest_s"), minimum=0)
    except ValueError as exc:
        errors.append(f"Rest {exc}.")
    try:
        data["target_date"] = to_date(request.form.get("target_date"))
    except ValueError as exc:
        errors.append(f"Target date {exc}.")

    return data, errors


def _form_context(goal, editing, goal_id=None):
    db = get_db()
    return {
        "goal": goal,
        "statuses": STATUSES,
        "editing": editing,
        "goal_id": goal_id,
        "cardio_exercises": _library_cardio_exercises(db),
    }


@bp.route("/")
@login_required
def index():
    db = get_db()
    status = request.args.get("status", "active")
    if status not in STATUSES:
        status = "active"
    goals = db.execute(
        """SELECT * FROM cardio_goals WHERE user_id = ? AND status = ?
           ORDER BY (target_date IS NULL), target_date, id DESC""",
        (g.user["id"], status),
    ).fetchall()
    return render_template(
        "cardio_goals/list.html",
        goals=_with_progress(db, goals),
        statuses=STATUSES,
        active_status=status,
    )


@bp.route("/new", methods=("GET", "POST"))
@login_required
def new():
    db = get_db()
    if request.method == "POST":
        data, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "cardio_goals/form.html",
                **_form_context(data, editing=False),
            ), 400

        db.execute(
            """INSERT INTO cardio_goals (user_id, category, distance_m, time_s,
                                         pace_km_per_min, rounds, rest_s,
                                         target_date, status, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user["id"],
                data["category"],
                data["distance_m"],
                data["time_s"],
                data["pace_km_per_min"],
                data["rounds"],
                data["rest_s"],
                data["target_date"],
                data["status"],
                data["notes"],
            ),
        )
        db.commit()
        flash("Cardio goal added.", "success")
        return redirect(url_for("cardio_goals.index"))

    return render_template(
        "cardio_goals/form.html",
        **_form_context(
            {
                "category": "",
                "distance_m": "",
                "time_s": "",
                "time_min": "",
                "pace_km_per_min": "",
                "rounds": "",
                "rest_s": "",
                "target_date": "",
                "status": "active",
                "notes": "",
            },
            editing=False,
        ),
    )


@bp.route("/<int:goal_id>/edit", methods=("GET", "POST"))
@login_required
def edit(goal_id):
    db = get_db()
    goal = db.execute(
        "SELECT * FROM cardio_goals WHERE id = ? AND user_id = ?",
        (goal_id, g.user["id"]),
    ).fetchone()
    if goal is None:
        abort(404)

    if request.method == "POST":
        data, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "cardio_goals/form.html",
                **_form_context(data, editing=True, goal_id=goal_id),
            ), 400

        db.execute(
            """UPDATE cardio_goals SET category = ?, distance_m = ?, time_s = ?,
                                        pace_km_per_min = ?, rounds = ?, rest_s = ?,
                                        target_date = ?, status = ?, notes = ?
               WHERE id = ? AND user_id = ?""",
            (
                data["category"],
                data["distance_m"],
                data["time_s"],
                data["pace_km_per_min"],
                data["rounds"],
                data["rest_s"],
                data["target_date"],
                data["status"],
                data["notes"],
                goal_id,
                g.user["id"],
            ),
        )
        db.commit()
        flash("Cardio goal updated.", "success")
        return redirect(url_for("cardio_goals.index"))

    return render_template(
        "cardio_goals/form.html",
        **_form_context(goal, editing=True, goal_id=goal_id),
    )


@bp.route("/<int:goal_id>/delete", methods=("POST",))
@login_required
def delete(goal_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM cardio_goals WHERE id = ? AND user_id = ?",
        (goal_id, g.user["id"]),
    )
    db.commit()
    if cursor.rowcount:
        flash("Cardio goal deleted.", "info")
    else:
        flash("Cardio goal not found.", "warning")
    return redirect(url_for("cardio_goals.index"))


@bp.route("/<int:goal_id>/log", methods=("GET", "POST"))
@login_required
def log(goal_id):
    db = get_db()
    goal = db.execute(
        "SELECT * FROM cardio_goals WHERE id = ? AND user_id = ?",
        (goal_id, g.user["id"]),
    ).fetchone()
    if goal is None:
        abort(404)

    logs = db.execute(
        "SELECT * FROM cardio_goal_logs WHERE cardio_goal_id = ? "
        "ORDER BY logged_date DESC, id DESC",
        (goal_id,),
    ).fetchall()
    form = {"value": "", "logged_date": dt.date.today().isoformat(), "notes": ""}

    if request.method == "POST":
        errors = []
        try:
            form["value"] = to_float(request.form.get("value"), minimum=0)
        except ValueError as exc:
            errors.append(f"Value {exc}.")
        if form["value"] is None:
            errors.append("Value (meters) is required.")
        try:
            form["logged_date"] = to_date(request.form.get("logged_date"))
        except ValueError as exc:
            errors.append(f"Date {exc}.")
        if form["logged_date"] is None:
            errors.append("Date is required.")
        form["notes"] = request.form.get("notes", "").strip()

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "cardio_goals/log.html", goal=goal, logs=logs, form=form
            ), 400

        db.execute(
            "INSERT INTO cardio_goal_logs (user_id, cardio_goal_id, value, logged_date, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (g.user["id"], goal_id, form["value"], form["logged_date"], form["notes"]),
        )
        db.commit()
        flash("Progress logged.", "success")
        return redirect(url_for("cardio_goals.index"))

    return render_template("cardio_goals/log.html", goal=goal, logs=logs, form=form)


@bp.route("/<int:goal_id>/logs/<int:log_id>/delete", methods=("POST",))
@login_required
def delete_log(goal_id, log_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM cardio_goal_logs WHERE id = ? AND cardio_goal_id = ? AND user_id = ?",
        (log_id, goal_id, g.user["id"]),
    )
    db.commit()
    if cursor.rowcount:
        flash("Progress entry deleted.", "info")
    else:
        flash("Entry not found.", "warning")
    return redirect(url_for("cardio_goals.log", goal_id=goal_id))
