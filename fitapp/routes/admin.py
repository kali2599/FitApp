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
from werkzeug.security import generate_password_hash

from .. import progress
from ..auth import admin_required
from ..db import get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")

EXERCISE_CATEGORIES = ["gym", "cardio"]
EXERCISE_SUBCATEGORIES = ["strength", "skill"]


def _counts(db, user_id):
    return db.execute(
        """SELECT
             (SELECT COUNT(*) FROM sports WHERE user_id = ?) AS sports,
             (SELECT COUNT(*) FROM workouts w
                JOIN sports s ON s.id = w.sport_id WHERE s.user_id = ?) AS workouts,
             (SELECT COUNT(*) FROM workout_days d
                JOIN workouts w ON w.id = d.workout_id
                JOIN sports s ON s.id = w.sport_id WHERE s.user_id = ?) AS days,
             (SELECT COUNT(*) FROM workout_modules m
                JOIN sports s ON s.id = m.sport_id WHERE s.user_id = ?) AS modules,
             (SELECT COUNT(*) FROM goals WHERE user_id = ?) AS goals,
             (SELECT COUNT(*) FROM diets WHERE user_id = ?) AS meals,
             (SELECT COUNT(*) FROM body_stats WHERE user_id = ?) AS measurements""",
        (user_id,) * 7,
    ).fetchone()


def _get_user(db, user_id):
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    return user


@bp.route("/")
@admin_required
def index():
    db = get_db()
    users = db.execute(
        "SELECT * FROM users ORDER BY created_at DESC, id DESC"
    ).fetchall()
    rows = []
    for user in users:
        row = {"user": user, "counts": _counts(db, user["id"])}
        rows.append(row)
    return render_template("admin/index.html", users=rows)


@bp.route("/users/<int:user_id>")
@admin_required
def user_detail(user_id):
    db = get_db()
    user = _get_user(db, user_id)
    counts = _counts(db, user_id)

    sports = db.execute(
        """SELECT s.*,
                  (SELECT COUNT(*) FROM workouts w WHERE w.sport_id = s.id) AS workout_count,
                  (SELECT COUNT(*) FROM workout_days d
                     JOIN workouts w ON w.id = d.workout_id
                    WHERE w.sport_id = s.id) AS day_count,
                  (SELECT COUNT(*) FROM workout_modules m
                    WHERE m.sport_id = s.id) AS module_count,
                  (SELECT COUNT(*) FROM day_exercises e
                     JOIN workout_modules m ON m.id = e.workout_module_id
                    WHERE m.sport_id = s.id) AS exercise_count
           FROM sports s WHERE s.user_id = ? ORDER BY s.created_at DESC, s.id DESC""",
        (user_id,),
    ).fetchall()

    any_goal = db.execute(
        "SELECT id FROM goals WHERE user_id = ? LIMIT 1", (user_id,)
    ).fetchone()
    goals = []
    if any_goal is not None:
        rows = db.execute(
            """SELECT * FROM goals WHERE user_id = ? AND status = 'active'
               ORDER BY (target_date IS NULL), target_date, id DESC""",
            (user_id,),
        ).fetchall()
        for goal in rows:
            current, source = progress.current_value(db, user_id, goal)
            goals.append(
                {
                    "goal": goal,
                    "current": current,
                    "source": source,
                    "percent": progress.percent(db, goal, current),
                }
            )

    stats = db.execute(
        """SELECT * FROM body_stats WHERE user_id = ?
           ORDER BY stat_date DESC, id DESC LIMIT 10""",
        (user_id,),
    ).fetchall()

    meals = db.execute(
        """SELECT * FROM diets WHERE user_id = ?
           ORDER BY diet_date DESC, id DESC LIMIT 10""",
        (user_id,),
    ).fetchall()

    return render_template(
        "admin/user_detail.html",
        user=user,
        counts=counts,
        sports=sports,
        goals=goals,
        stats=stats,
        meals=meals,
    )


@bp.route("/users/<int:user_id>/reset-password", methods=("POST",))
@admin_required
def user_reset_password(user_id):
    db = get_db()
    user = _get_user(db, user_id)
    if user["role"] != "user":
        flash("Admins can only have their password reset from the CLI.", "danger")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    password = request.form.get("password", "")
    if len(password) < 6:
        flash("Password must be at least 6 characters.", "danger")
        return redirect(url_for("admin.user_detail", user_id=user_id))

    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), user_id),
    )
    db.commit()
    flash(f"Password reset for {user['username']}.", "success")
    return redirect(url_for("admin.user_detail", user_id=user_id))


def _catalog(db):
    return db.execute(
        "SELECT * FROM exercises ORDER BY category, name COLLATE NOCASE"
    ).fetchall()


def _parse_exercise_form(db, exclude_id=None):
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip().lower()
    subcategory = request.form.get("subcategory", "").strip().lower() or None
    notes = request.form.get("notes", "").strip()

    errors = []
    if not name:
        errors.append("Exercise name is required.")
    if category not in EXERCISE_CATEGORIES:
        errors.append("Choose a valid category.")
    if category == "gym" and subcategory not in EXERCISE_SUBCATEGORIES:
        errors.append("Gym exercises need a subcategory (strength or skill).")
    if category == "cardio" and subcategory is not None:
        errors.append("Cardio exercises cannot have a subcategory.")
    if not errors:
        query = "SELECT id FROM exercises WHERE name = ? COLLATE NOCASE"
        params = (name,)
        if exclude_id is not None:
            query += " AND id != ?"
            params = params + (exclude_id,)
        if db.execute(query, params).fetchone():
            errors.append("An exercise with that name already exists.")
    return {
        "name": name,
        "category": category,
        "subcategory": subcategory,
        "notes": notes,
    }, errors


@bp.route("/exercises")
@admin_required
def exercises():
    db = get_db()
    return render_template(
        "admin/exercises.html",
        exercises=_catalog(db),
        categories=EXERCISE_CATEGORIES,
        subcategories=EXERCISE_SUBCATEGORIES,
        form={},
    )


@bp.route("/exercises", methods=("POST",))
@admin_required
def exercises_create():
    db = get_db()
    data, errors = _parse_exercise_form(db)
    if errors:
        for error in errors:
            flash(error, "danger")
        return render_template(
            "admin/exercises.html",
            exercises=_catalog(db),
            categories=EXERCISE_CATEGORIES,
            subcategories=EXERCISE_SUBCATEGORIES,
            form=data,
        ), 400

    db.execute(
        "INSERT INTO exercises (category, subcategory, name, notes) VALUES (?, ?, ?, ?)",
        (data["category"], data["subcategory"], data["name"], data["notes"]),
    )
    db.commit()
    flash(f"Exercise '{data['name']}' added.", "success")
    return redirect(url_for("admin.exercises"))


@bp.route("/exercises/<int:exercise_id>/edit", methods=("GET", "POST"))
@admin_required
def exercises_edit(exercise_id):
    db = get_db()
    exercise = db.execute(
        "SELECT * FROM exercises WHERE id = ?", (exercise_id,)
    ).fetchone()
    if exercise is None:
        abort(404)

    if request.method == "POST":
        data, errors = _parse_exercise_form(db, exclude_id=exercise_id)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "admin/exercises_edit.html",
                exercise=dict(exercise, **data),
                categories=EXERCISE_CATEGORIES,
                subcategories=EXERCISE_SUBCATEGORIES,
            ), 400
        db.execute(
            """UPDATE exercises SET name = ?, category = ?, subcategory = ?, notes = ?
               WHERE id = ?""",
            (data["name"], data["category"], data["subcategory"], data["notes"], exercise_id),
        )
        db.commit()
        flash("Exercise updated.", "success")
        return redirect(url_for("admin.exercises"))

    return render_template(
        "admin/exercises_edit.html",
        exercise=exercise,
        categories=EXERCISE_CATEGORIES,
        subcategories=EXERCISE_SUBCATEGORIES,
    )


@bp.route("/exercises/<int:exercise_id>/delete", methods=("POST",))
@admin_required
def exercises_delete(exercise_id):
    db = get_db()
    cursor = db.execute("DELETE FROM exercises WHERE id = ?", (exercise_id,))
    db.commit()
    if cursor.rowcount:
        flash("Exercise deleted.", "info")
    else:
        flash("Exercise not found.", "warning")
    return redirect(url_for("admin.exercises"))