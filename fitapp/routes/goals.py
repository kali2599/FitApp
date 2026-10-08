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

from .. import progress
from ..auth import login_required
from ..db import get_db
from ..utils import goal_progress, to_date, to_float

bp = Blueprint("goals", __name__, url_prefix="/goals")

GOAL_TYPES = ["performance", "body"]
STATUSES = ["active", "achieved", "abandoned"]

CATEGORY_SUGGESTIONS = {
    "performance": [
        "Bench press",
        "Squat",
        "Deadlift",
        "Overhead press",
        "Pull-up",
        "Push-up",
        "Plank hold",
        "Running distance",
        "Running time",
    ],
    "body": ["Weight", "Body fat", "Waist", "Chest", "Hip", "Arm"],
}


def _parse_form():
    data = {
        "goal_type": request.form.get("goal_type", "").strip(),
        "category": request.form.get("category", "").strip(),
        "unit": request.form.get("unit", "").strip(),
        "status": request.form.get("status", "active").strip(),
        "notes": request.form.get("notes", "").strip(),
        "target_value": None,
        "start_value": None,
        "target_date": None,
    }
    errors = []
    if data["goal_type"] not in GOAL_TYPES:
        errors.append("Choose a valid goal type.")
    if not data["category"]:
        errors.append("Goal category is required.")
    if not data["unit"]:
        errors.append("Unit is required (e.g. kg, %, cm, reps, min).")
    if data["status"] not in STATUSES:
        errors.append("Choose a valid status.")
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
    try:
        data["target_date"] = to_date(request.form.get("target_date"))
    except ValueError as exc:
        errors.append(f"Target date {exc}.")
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
                "percent": goal_progress(goal, current),
            }
        )
    return rows


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
    if request.method == "POST":
        data, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "goals/form.html",
                goal=data,
                goal_types=GOAL_TYPES,
                statuses=STATUSES,
                suggestions=CATEGORY_SUGGESTIONS,
                editing=False,
            ), 400

        db = get_db()
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
        goal={
            "goal_type": "performance",
            "category": "",
            "unit": "",
            "target_value": "",
            "start_value": "",
            "target_date": "",
            "status": "active",
            "notes": "",
        },
        goal_types=GOAL_TYPES,
        statuses=STATUSES,
        suggestions=CATEGORY_SUGGESTIONS,
        editing=False,
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
        data, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "goals/form.html",
                goal=data,
                goal_types=GOAL_TYPES,
                statuses=STATUSES,
                suggestions=CATEGORY_SUGGESTIONS,
                editing=True,
                goal_id=goal_id,
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
        goal=goal,
        goal_types=GOAL_TYPES,
        statuses=STATUSES,
        suggestions=CATEGORY_SUGGESTIONS,
        editing=True,
        goal_id=goal_id,
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
