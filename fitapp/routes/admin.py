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
from .goals import _cardio_as_goal, _cardio_current, _cardio_percent

bp = Blueprint("admin", __name__, url_prefix="/admin")

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
                WHERE m.user_id = ?) AS modules,
             (SELECT COUNT(*) FROM goals WHERE user_id = ?) AS goals,
             (SELECT COUNT(*) FROM cardio_goals WHERE user_id = ?) AS cardio_goals,
             (SELECT COUNT(*) FROM diet_plans WHERE user_id = ?) AS diet_plans,
             (SELECT COUNT(*) FROM body_stats WHERE user_id = ?) AS measurements""",
        (user_id,) * 8,
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
        "SELECT * FROM users WHERE role != 'admin' ORDER BY created_at DESC, id DESC"
    ).fetchall()
    rows = []
    for user in users:
        row = {"user": user, "counts": _counts(db, user["id"])}
        rows.append(row)
    return render_template("admin/index.html", users=rows)


@bp.route("/settings")
@admin_required
def settings():
    return render_template("admin/settings.html")


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
                  (SELECT COUNT(*) FROM day_entry_sets ses
                     JOIN day_entries e ON e.id = ses.day_entry_id
                     JOIN workout_days d ON d.id = e.workout_day_id
                     JOIN workouts w ON w.id = d.workout_id
                    WHERE w.sport_id = s.id) AS exercise_count
           FROM sports s WHERE s.user_id = ? ORDER BY s.created_at DESC, s.id DESC""",
        (user_id,),
    ).fetchall()

    any_goal = db.execute(
        "SELECT id FROM goals WHERE user_id = ? LIMIT 1", (user_id,)
    ).fetchone()
    any_cardio = db.execute(
        "SELECT id FROM cardio_goals WHERE user_id = ? LIMIT 1", (user_id,)
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
                    "goal": dict(goal, is_cardio=False),
                    "current": current,
                    "source": source,
                    "percent": progress.percent(db, goal, current),
                }
            )
    if any_cardio is not None:
        rows = db.execute(
            """SELECT * FROM cardio_goals WHERE user_id = ? AND status = 'active'
               ORDER BY (target_date IS NULL), target_date, id DESC""",
            (user_id,),
        ).fetchall()
        for row in rows:
            goal = _cardio_as_goal(row)
            current, source = _cardio_current(db, goal)
            goals.append(
                {
                    "goal": goal,
                    "current": current,
                    "source": source,
                    "percent": _cardio_percent(goal, current),
                }
            )

    stats = db.execute(
        """SELECT * FROM body_stats WHERE user_id = ?
           ORDER BY stat_date DESC, id DESC LIMIT 10""",
        (user_id,),
    ).fetchall()

    diet_plans = db.execute(
        """SELECT * FROM diet_plans WHERE user_id = ?
           ORDER BY created_at DESC, id DESC LIMIT 10""",
        (user_id,),
    ).fetchall()

    return render_template(
        "admin/user_detail.html",
        user=user,
        counts=counts,
        sports=sports,
        goals=goals,
        stats=stats,
        diet_plans=diet_plans,
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
