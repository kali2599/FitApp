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

from ..auth import login_required
from ..db import get_db
from ..utils import to_date, to_float, to_int

bp = Blueprint("workouts", __name__, url_prefix="/workouts")

WORKOUT_TYPES = ["Strength", "Cardio", "HIIT", "Flexibility", "Sports", "Other"]


def _parse_exercises():
    names = request.form.getlist("ex_name")
    sets = request.form.getlist("ex_sets")
    reps = request.form.getlist("ex_reps")
    weights = request.form.getlist("ex_weight")
    exercises = []
    errors = []
    for i, raw_name in enumerate(names):
        name = raw_name.strip()
        if not name:
            continue
        row = {"name": name, "sets": None, "reps": None, "weight_kg": None}
        try:
            if i < len(sets):
                row["sets"] = to_int(sets[i], minimum=1, maximum=500)
            if i < len(reps):
                row["reps"] = to_int(reps[i], minimum=1, maximum=1000)
            if i < len(weights):
                row["weight_kg"] = to_float(weights[i], minimum=0, maximum=2000)
        except ValueError as exc:
            errors.append(f'Exercise "{name}": {exc}.')
            continue
        exercises.append(row)
    return exercises, errors


def _parse_form():
    data = {
        "name": request.form.get("name", "").strip(),
        "workout_type": request.form.get("workout_type", "").strip(),
        "workout_date": None,
        "duration_min": None,
        "calories": None,
        "notes": request.form.get("notes", "").strip(),
    }
    errors = []
    if not data["name"]:
        errors.append("Workout name is required.")
    if data["workout_type"] not in WORKOUT_TYPES:
        errors.append("Choose a valid workout type.")
    try:
        data["workout_date"] = to_date(request.form.get("workout_date"))
    except ValueError as exc:
        errors.append(f"Workout date {exc}.")
    if data["workout_date"] is None:
        errors.append("Workout date is required.")
    try:
        data["duration_min"] = to_int(request.form.get("duration_min"), minimum=0, maximum=1440)
    except ValueError as exc:
        errors.append(f"Duration {exc}.")
    try:
        data["calories"] = to_float(request.form.get("calories"), minimum=0, maximum=20000)
    except ValueError as exc:
        errors.append(f"Calories {exc}.")

    exercises, exercise_errors = _parse_exercises()
    errors.extend(exercise_errors)
    return data, exercises, errors


@bp.route("/")
@login_required
def index():
    db = get_db()
    workouts = db.execute(
        """SELECT w.*,
                  (SELECT COUNT(*) FROM exercises e WHERE e.workout_id = w.id) AS exercise_count,
                  (SELECT COUNT(*) FROM exercises e WHERE e.workout_id = w.id AND e.weight_kg IS NOT NULL) AS weighted_count
           FROM workouts w
           WHERE w.user_id = ?
           ORDER BY w.workout_date DESC, w.id DESC""",
        (g.user["id"],),
    ).fetchall()

    exercise_rows = db.execute(
        """SELECT e.* FROM exercises e
           JOIN workouts w ON w.id = e.workout_id
           WHERE w.user_id = ?
           ORDER BY w.workout_date DESC, w.id DESC, e.position, e.id""",
        (g.user["id"],),
    ).fetchall()
    by_workout = {}
    for row in exercise_rows:
        by_workout.setdefault(row["workout_id"], []).append(row)

    return render_template(
        "workouts/list.html",
        workouts=workouts,
        exercises_by_workout=by_workout,
        types=WORKOUT_TYPES,
    )


@bp.route("/new", methods=("GET", "POST"))
@login_required
def new():
    if request.method == "POST":
        data, exercises, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "workouts/form.html",
                workout=data,
                exercises=exercises,
                types=WORKOUT_TYPES,
                editing=False,
            ), 400

        db = get_db()
        cursor = db.execute(
            """INSERT INTO workouts (user_id, name, workout_type, workout_date,
                                     duration_min, calories, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user["id"],
                data["name"],
                data["workout_type"],
                data["workout_date"],
                data["duration_min"],
                data["calories"],
                data["notes"],
            ),
        )
        for position, exercise in enumerate(exercises):
            db.execute(
                """INSERT INTO exercises (workout_id, name, sets, reps, weight_kg, position)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    cursor.lastrowid,
                    exercise["name"],
                    exercise["sets"],
                    exercise["reps"],
                    exercise["weight_kg"],
                    position,
                ),
            )
        db.commit()
        flash("Workout added.", "success")
        return redirect(url_for("workouts.index"))

    return render_template(
        "workouts/form.html",
        workout={
            "name": "",
            "workout_type": "",
            "workout_date": request.args.get("date", ""),
            "duration_min": "",
            "calories": "",
            "notes": "",
        },
        exercises=[],
        types=WORKOUT_TYPES,
        editing=False,
    )


@bp.route("/<int:workout_id>/edit", methods=("GET", "POST"))
@login_required
def edit(workout_id):
    db = get_db()
    workout = db.execute(
        "SELECT * FROM workouts WHERE id = ? AND user_id = ?",
        (workout_id, g.user["id"]),
    ).fetchone()
    if workout is None:
        abort(404)

    exercises = db.execute(
        "SELECT * FROM exercises WHERE workout_id = ? ORDER BY position, id",
        (workout_id,),
    ).fetchall()

    if request.method == "POST":
        data, parsed_exercises, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "workouts/form.html",
                workout=data,
                exercises=parsed_exercises,
                types=WORKOUT_TYPES,
                editing=True,
                workout_id=workout_id,
            ), 400

        db.execute(
            """UPDATE workouts SET name = ?, workout_type = ?, workout_date = ?,
                                    duration_min = ?, calories = ?, notes = ?
               WHERE id = ? AND user_id = ?""",
            (
                data["name"],
                data["workout_type"],
                data["workout_date"],
                data["duration_min"],
                data["calories"],
                data["notes"],
                workout_id,
                g.user["id"],
            ),
        )
        db.execute("DELETE FROM exercises WHERE workout_id = ?", (workout_id,))
        for position, exercise in enumerate(parsed_exercises):
            db.execute(
                """INSERT INTO exercises (workout_id, name, sets, reps, weight_kg, position)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    workout_id,
                    exercise["name"],
                    exercise["sets"],
                    exercise["reps"],
                    exercise["weight_kg"],
                    position,
                ),
            )
        db.commit()
        flash("Workout updated.", "success")
        return redirect(url_for("workouts.index"))

    return render_template(
        "workouts/form.html",
        workout=workout,
        exercises=exercises,
        types=WORKOUT_TYPES,
        editing=True,
        workout_id=workout_id,
    )


@bp.route("/<int:workout_id>/delete", methods=("POST",))
@login_required
def delete(workout_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM workouts WHERE id = ? AND user_id = ?",
        (workout_id, g.user["id"]),
    )
    db.commit()
    if cursor.rowcount:
        flash("Workout deleted.", "info")
    else:
        flash("Workout not found.", "warning")
    return redirect(url_for("workouts.index"))
