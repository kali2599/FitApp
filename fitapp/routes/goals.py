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
from ..utils import to_date, to_float

bp = Blueprint("goals", __name__, url_prefix="/goals")

GOAL_TYPES = ["body", "skill", "strength"]
STATUSES = ["active", "achieved", "abandoned"]

UNIT_BY_TYPE = {
    "body": ["kg", "%"],
    "skill": ["seconds", "levels"],
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


def _skill_catalog(db):
    skills = db.execute("SELECT DISTINCT skill FROM skill_levels ORDER BY skill").fetchall()
    catalog = {}
    for row in skills:
        levels = db.execute(
            "SELECT level, position, score FROM skill_levels "
            "WHERE skill = ? ORDER BY position",
            (row["skill"],),
        ).fetchall()
        catalog[row["skill"]] = [
            {"level": l["level"], "position": l["position"], "score": l["score"]}
            for l in levels
        ]
    return catalog


def _parse_form(db):
    data = {
        "goal_type": request.form.get("goal_type", "").strip().lower(),
        "category": request.form.get("category", "").strip(),
        "unit": request.form.get("unit", "").strip().lower(),
        "status": request.form.get("status", "active").strip(),
        "notes": request.form.get("notes", "").strip(),
        "target_value": None,
        "start_value": None,
        "target_date": None,
    }
    errors = []
    if data["goal_type"] not in GOAL_TYPES:
        errors.append("Choose a valid goal type.")
    allowed = UNIT_BY_TYPE.get(data["goal_type"], [])
    if data["unit"] not in allowed:
        errors.append(f"Unit must be one of: {', '.join(allowed) or '—'}.")
    if not data["category"]:
        errors.append("Goal category is required.")
    if data["status"] not in STATUSES:
        errors.append("Choose a valid status.")
    try:
        data["target_date"] = to_date(request.form.get("target_date"))
    except ValueError as exc:
        errors.append(f"Target date {exc}.")

    if data["goal_type"] == "skill":
        catalog = _skill_catalog(db)
        if data["category"].lower() not in catalog:
            errors.append("Pick a skill from the list.")

    if data["unit"] == "levels":
        catalog = _skill_catalog(db)
        skill = data["category"].lower()
        levels = [l["level"] for l in catalog.get(skill, [])]
        if skill not in catalog:
            errors.append("Pick a skill with defined levels.")
        else:
            data["start_value"] = request.form.get("start_value", "").strip()
            data["target_value"] = request.form.get("target_value", "").strip()
            if data["start_value"] not in levels:
                errors.append("Pick a valid start level.")
            if data["target_value"] not in levels:
                errors.append("Pick a valid target level.")
            if (
                data["start_value"]
                and data["target_value"]
                and data["start_value"] == data["target_value"]
            ):
                errors.append("Start and target levels must differ.")
    else:
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


def _with_progress(db, goals):
    rows = []
    for goal in goals:
        current, source = progress.current_value(db, g.user["id"], goal)
        rows.append(
            {
                "goal": goal,
                "current": current,
                "source": source,
                "percent": progress.percent(db, goal, current),
            }
        )
    return rows


def _form_context(db, goal, editing, goal_id=None):
    return {
        "goal": goal,
        "goal_types": GOAL_TYPES,
        "statuses": STATUSES,
        "unit_map": UNIT_BY_TYPE,
        "suggestions": CATEGORY_SUGGESTIONS,
        "skills": _skill_catalog(db),
        "editing": editing,
        "goal_id": goal_id,
    }


@bp.route("/")
@login_required
def index():
    db = get_db()
    status = request.args.get("status", "active")
    if status not in STATUSES:
        status = "active"
    goals = db.execute(
        """SELECT * FROM goals WHERE user_id = ? AND status = ?
           ORDER BY (target_date IS NULL), target_date, id DESC""",
        (g.user["id"], status),
    ).fetchall()
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
        data, errors = _parse_form(db)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "goals/form.html",
                **_form_context(db, data, editing=False),
            ), 400

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
            },
            editing=False,
        ),
    )


@bp.route("/<int:goal_id>/edit", methods=("GET", "POST"))
@login_required
def edit(goal_id):
    db = get_db()
    goal = db.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, g.user["id"])
    ).fetchone()
    if goal is None:
        abort(404)

    if request.method == "POST":
        data, errors = _parse_form(db)
        if errors:
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


def _goal_logs(db, goal_id):
    return db.execute(
        "SELECT * FROM goal_logs WHERE goal_id = ? ORDER BY logged_date DESC, id DESC",
        (goal_id,),
    ).fetchall()


@bp.route("/<int:goal_id>/log", methods=("GET", "POST"))
@login_required
def log(goal_id):
    db = get_db()
    goal = db.execute(
        "SELECT * FROM goals WHERE id = ? AND user_id = ?", (goal_id, g.user["id"])
    ).fetchone()
    if goal is None:
        abort(404)

    logs = _goal_logs(db, goal_id)
    levels = _skill_catalog(db).get((goal["category"] or "").lower(), [])
    form = {"value": "", "logged_date": dt.date.today().isoformat(), "notes": ""}

    if request.method == "POST":
        errors = []
        if goal["unit"] == "levels":
            choice = request.form.get("value", "").strip()
            valid = {l["level"] for l in levels}
            if choice not in valid:
                errors.append("Pick a valid level.")
            form["value"] = choice
        else:
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
                "goals/log.html", goal=goal, logs=logs, form=form, levels=levels
            ), 400

        db.execute(
            "INSERT INTO goal_logs (user_id, goal_id, value, logged_date, notes) "
            "VALUES (?, ?, ?, ?, ?)",
            (g.user["id"], goal_id, form["value"], form["logged_date"], form["notes"]),
        )
        db.commit()
        flash("Progress logged.", "success")
        return redirect(url_for("goals.index"))

    return render_template("goals/log.html", goal=goal, logs=logs, form=form, levels=levels)


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