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

from .. import progress
from ..auth import login_required
from ..db import get_db
from ..utils import to_date, to_float, to_int

bp = Blueprint("goals", __name__, url_prefix="/goals")

GOAL_TYPES = ["body", "skill", "strength", "cardio"]
STATUSES = ["active", "achieved", "abandoned"]

UNIT_BY_TYPE = {
    "body": ["kg", "%"],
    "skill": ["seconds", "reps"],
    "strength": ["kg", "reps"],
}
NUMERIC_UNITS = {"kg", "%", "seconds", "reps"}

CATEGORY_SUGGESTIONS = {
    "body": ["Weight", "Body fat"],
    "skill": [
        "Front lever hold",
        "Back lever",
        "Planche",
        "Handstand hold",
        "L-sit",
        "Dragon flag",
        "Muscle-up",
    ],
    "strength": [
        "Bench press",
        "Squat",
        "Deadlift",
        "Overhead press",
        "Pull-up",
        "Push-up",
        "Barbell row",
    ],
}


def _library_exercises(db):
    return db.execute(
        "SELECT name, label FROM library_exercises WHERE user_id = ? "
        "ORDER BY name COLLATE NOCASE",
        (g.user["id"],),
    ).fetchall()


def _menu_catalog(db):
    menu = {
        "strength": [],
        "skill": [],
        "cardio": [],
    }
    for row in _library_exercises(db):
        label = row["label"]
        if label in menu and row["name"] not in menu[label]:
            menu[label].append(row["name"])
    return menu


def _goal_suggestions(db):
    suggestions = {key: list(values) for key, values in CATEGORY_SUGGESTIONS.items()}
    for row in _library_exercises(db):
        if row["label"] in suggestions:
            suggestions[row["label"]].append(row["name"])
    return suggestions


def _parse_form():
    data = {
        "goal_type": request.form.get("goal_type", "").strip().lower(),
        "category": request.form.get("category", "").strip(),
        "unit": request.form.get("unit", "").strip().lower(),
        "status": request.form.get("status", "active").strip(),
        "notes": request.form.get("notes", "").strip(),
        "target_value": None,
        "start_value": None,
        "target_date": None,
        "distance_m": None,
        "time_s": None,
        "time_min": None,
        "pace_km_per_min": None,
        "rounds": None,
        "rest_s": None,
    }
    errors = []
    if data["goal_type"] not in GOAL_TYPES:
        errors.append("Choose a valid goal type.")
    if not data["category"]:
        errors.append("Goal category is required.")
    if data["status"] not in STATUSES:
        errors.append("Choose a valid status.")
    try:
        data["target_date"] = to_date(request.form.get("target_date"))
    except ValueError as exc:
        errors.append(f"Target date {exc}.")

    if data["goal_type"] == "cardio":
        try:
            data["distance_m"] = to_float(request.form.get("distance_m"), minimum=0)
        except ValueError as exc:
            errors.append(f"Distance {exc}.")
        if data["distance_m"] is None:
            errors.append("Distance (meters) is required.")

        raw_sec = (request.form.get("time_s") or "").strip()
        raw_min = (request.form.get("time_min") or "").strip()
        if raw_sec and raw_min:
            errors.append("Enter time in seconds OR minutes, not both.")
        elif raw_min:
            try:
                minutes = to_float(raw_min, minimum=0)
                if minutes is not None:
                    data["time_min"] = minutes
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
    else:
        allowed = UNIT_BY_TYPE.get(data["goal_type"], [])
        if data["unit"] not in allowed:
            errors.append(f"Unit must be one of: {', '.join(allowed) or '—'}.")
        try:
            data["target_value"] = to_float(request.form.get("target_value"))
        except ValueError as exc:
            errors.append(f"Target value {exc}.")
        if data["target_value"] is None:
            errors.append("Target value is required.")
        try:
            data["start_value"] = to_float(request.form.get("start_value"))
        except ValueError as exc:
            errors.append(f"Start value {exc}.")
    return data, errors


def _cardio_current(db, goal):
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


def _cardio_percent(goal, current):
    target = goal.get("distance_m")
    if current is None or target is None or target <= 0:
        return None
    return round(max(0.0, min(150.0, current / target * 100)), 1)


def _with_progress(db, goals):
    rows = []
    for goal in goals:
        if goal.get("is_cardio"):
            current, source = _cardio_current(db, goal)
            percent = _cardio_percent(goal, current)
        else:
            current, source = progress.current_value(db, g.user["id"], goal)
            percent = progress.percent(db, goal, current)
        rows.append(
            {
                "goal": goal,
                "current": current,
                "source": source,
                "percent": percent,
            }
        )
    return rows


def _form_context(db, goal, editing, goal_id=None):
    return {
        "goal": goal,
        "goal_types": GOAL_TYPES,
        "statuses": STATUSES,
        "unit_map": UNIT_BY_TYPE,
        "suggestions": _goal_suggestions(db),
        "menu_catalog": _menu_catalog(db),
        "editing": editing,
        "goal_id": goal_id,
    }


def _cardio_as_goal(row):
    """Shape a cardio_goals row like a standard goal for templates/progress."""
    goal = dict(row)
    goal["is_cardio"] = True
    goal["goal_type"] = "cardio"
    goal["target_value"] = goal["distance_m"]
    goal["unit"] = "m"
    goal["start_value"] = None
    return goal


def _standard_as_goal(row):
    goal = dict(row)
    goal["is_cardio"] = False
    return goal


@bp.route("/")
@login_required
def index():
    db = get_db()
    status = request.args.get("status", "active")
    if status not in STATUSES:
        status = "active"
    standard = db.execute(
        """SELECT * FROM goals WHERE user_id = ? AND status = ?
           ORDER BY (target_date IS NULL), target_date, id DESC""",
        (g.user["id"], status),
    ).fetchall()
    cardio = db.execute(
        """SELECT * FROM cardio_goals WHERE user_id = ? AND status = ?
           ORDER BY (target_date IS NULL), target_date, id DESC""",
        (g.user["id"], status),
    ).fetchall()
    goals = [_standard_as_goal(r) for r in standard] + [_cardio_as_goal(r) for r in cardio]
    goals.sort(
        key=lambda g: (g["target_date"] is None, g["target_date"] or "", -(g["id"])),
    )
    return render_template(
        "goals/list.html",
        goals=_with_progress(db, goals),
        statuses=STATUSES,
        active_status=status,
        suggestions=CATEGORY_SUGGESTIONS,
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
                "goals/form.html",
                **_form_context(db, data, editing=False),
            ), 400

        if data["goal_type"] == "cardio":
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
        else:
            db.execute(
                """INSERT INTO goals (user_id, goal_type, category, target_value, unit,
                                      start_value, target_date, status, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    g.user["id"],
                    data["goal_type"],
                    data["category"],
                    data["target_value"],
                    data["unit"],
                    data["start_value"],
                    data["target_date"],
                    data["status"],
                    data["notes"],
                ),
            )
        db.commit()
        flash("Goal added.", "success")
        return redirect(url_for("goals.index"))

    return render_template(
        "goals/form.html",
        **_form_context(
            db,
            {
                "goal_type": "body",
                "category": "",
                "unit": "kg",
                "target_value": "",
                "start_value": "",
                "target_date": "",
                "status": "active",
                "notes": "",
                "distance_m": "",
                "time_s": "",
                "time_min": "",
                "pace_km_per_min": "",
                "rounds": "",
                "rest_s": "",
            },
            editing=False,
        ),
    )


@bp.route("/<int:goal_id>/edit", methods=("GET", "POST"))
@login_required
def edit(goal_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)
    goal = _standard_as_goal(row)

    if request.method == "POST":
        data, errors = _parse_form()
        if errors or data["goal_type"] == "cardio":
            if data["goal_type"] == "cardio":
                errors.append("A standard goal cannot become a cardio goal.")
            for error in errors:
                flash(error, "danger")
            return render_template(
                "goals/form.html",
                **_form_context(db, data, editing=True, goal_id=goal_id),
            ), 400

        db.execute(
            """UPDATE goals SET goal_type = ?, category = ?, target_value = ?, unit = ?,
                                 start_value = ?, target_date = ?, status = ?, notes = ?
               WHERE id = ? AND user_id = ?""",
            (
                data["goal_type"],
                data["category"],
                data["target_value"],
                data["unit"],
                data["start_value"],
                data["target_date"],
                data["status"],
                data["notes"],
                goal_id,
                g.user["id"],
            ),
        )
        db.commit()
        flash("Goal updated.", "success")
        return redirect(url_for("goals.index"))

    return render_template(
        "goals/form.html",
        **_form_context(db, goal, editing=True, goal_id=goal_id),
    )


@bp.route("/cardio/<int:goal_id>/edit", methods=("GET", "POST"))
@login_required
def edit_cardio(goal_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM cardio_goals WHERE id = ? AND user_id = ?", (goal_id, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)
    goal = _cardio_as_goal(row)

    if request.method == "POST":
        data, errors = _parse_form()
        if errors or data["goal_type"] != "cardio":
            if data["goal_type"] != "cardio":
                errors.append("A cardio goal cannot become a standard goal.")
            for error in errors:
                flash(error, "danger")
            return render_template(
                "goals/form.html",
                **_form_context(db, data, editing=True, goal_id=goal_id),
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
        flash("Goal updated.", "success")
        return redirect(url_for("goals.index"))

    return render_template(
        "goals/form.html",
        **_form_context(db, goal, editing=True, goal_id=goal_id),
    )


@bp.route("/<int:goal_id>/delete", methods=("POST",))
@login_required
def delete(goal_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM goals WHERE id = ? AND user_id = ?", (goal_id, g.user["id"])
    )
    db.commit()
    if cursor.rowcount:
        flash("Goal deleted.", "info")
    else:
        flash("Goal not found.", "warning")
    return redirect(url_for("goals.index"))


@bp.route("/cardio/<int:goal_id>/delete", methods=("POST",))
@login_required
def delete_cardio(goal_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM cardio_goals WHERE id = ? AND user_id = ?", (goal_id, g.user["id"])
    )
    db.commit()
    if cursor.rowcount:
        flash("Goal deleted.", "info")
    else:
        flash("Goal not found.", "warning")
    return redirect(url_for("goals.index"))


def _goal_logs(db, goal_id):
    return db.execute(
        "SELECT * FROM goal_logs WHERE goal_id = ? ORDER BY logged_date DESC, id DESC",
        (goal_id,),
    ).fetchall()


@bp.route("/<int:goal_id>/log", methods=("GET", "POST"))
@login_required
def log(goal_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)
    goal = _standard_as_goal(row)

    logs = _goal_logs(db, goal_id)
    form = {"value": "", "logged_date": dt.date.today().isoformat(), "notes": ""}

    if request.method == "POST":
        errors = []
        try:
            form["value"] = to_float(request.form.get("value"))
        except ValueError as exc:
            errors.append(f"Value {exc}.")
        if form["value"] is None:
            errors.append("Value is required.")
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
                "goals/log.html", goal=goal, logs=logs, form=form
            ), 400

        db.execute(
            "INSERT INTO goal_logs (user_id, goal_id, value, logged_date, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (g.user["id"], goal_id, form["value"], form["logged_date"], form["notes"]),
        )
        db.commit()
        flash("Progress logged.", "success")
        return redirect(url_for("goals.index"))

    return render_template("goals/log.html", goal=goal, logs=logs, form=form)


@bp.route("/cardio/<int:goal_id>/log", methods=("GET", "POST"))
@login_required
def log_cardio(goal_id):
    db = get_db()
    row = db.execute(
        "SELECT * FROM cardio_goals WHERE id = ? AND user_id = ?", (goal_id, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)
    goal = _cardio_as_goal(row)

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
                "goals/log.html", goal=goal, logs=logs, form=form
            ), 400

        db.execute(
            "INSERT INTO cardio_goal_logs (user_id, cardio_goal_id, value, logged_date, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (g.user["id"], goal_id, form["value"], form["logged_date"], form["notes"]),
        )
        db.commit()
        flash("Progress logged.", "success")
        return redirect(url_for("goals.index"))

    return render_template("goals/log.html", goal=goal, logs=logs, form=form)


@bp.route("/<int:goal_id>/logs/<int:log_id>/delete", methods=("POST",))
@login_required
def delete_log(goal_id, log_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM goal_logs WHERE id = ? AND goal_id = ? AND user_id = ?",
        (log_id, goal_id, g.user["id"]),
    )
    db.commit()
    if cursor.rowcount:
        flash("Progress entry deleted.", "info")
    else:
        flash("Entry not found.", "warning")
    return redirect(url_for("goals.log", goal_id=goal_id))


@bp.route("/cardio/<int:goal_id>/logs/<int:log_id>/delete", methods=("POST",))
@login_required
def delete_log_cardio(goal_id, log_id):
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
    return redirect(url_for("goals.log_cardio", goal_id=goal_id))
