import re

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from ..auth import login_required
from ..db import get_db
from ..utils import to_date, to_float

bp = Blueprint("profile", __name__, url_prefix="/profile")

SEXES = ["male", "female", "other", ""]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _context():
    db = get_db()
    stats = db.execute(
        """SELECT * FROM body_stats WHERE user_id = ?
           ORDER BY stat_date DESC, id DESC LIMIT 1""",
        (g.user["id"],),
    ).fetchone()

    totals = db.execute(
        """SELECT
             (SELECT COUNT(*) FROM workout_sessions WHERE user_id = ?) AS workouts,
             (SELECT COALESCE(SUM(duration_min), 0) FROM workout_sessions WHERE user_id = ?) AS minutes,
             (SELECT COALESCE(SUM(calories), 0) FROM workout_sessions WHERE user_id = ?) AS burned,
             (SELECT COUNT(*) FROM diets WHERE user_id = ?) AS meals,
             (SELECT COUNT(*) FROM goals WHERE user_id = ? AND status = 'active') AS active_goals,
             (SELECT COUNT(*) FROM body_stats WHERE user_id = ?) AS stat_entries""",
        (g.user["id"],) * 6,
    ).fetchone()

    records = db.execute(
        """SELECT e.name,
                  MAX(CASE WHEN e.weight_kg GLOB '*[a-zA-Z]*' THEN NULL ELSE e.weight_kg END) AS best_weight,
                  MAX(CASE WHEN e.reps GLOB '*[a-zA-Z]*' THEN NULL ELSE e.reps END) AS best_reps,
                  MAX(e.sets) AS best_sets,
                  MAX(s.performed_date) AS last_date
           FROM session_entries e
           JOIN workout_sessions s ON s.id = e.session_id
           WHERE s.user_id = ? AND e.kind = 'gym'
           GROUP BY LOWER(TRIM(e.name))
           HAVING best_weight IS NOT NULL OR best_reps IS NOT NULL
           ORDER BY best_weight DESC NULLS LAST, best_reps DESC
           LIMIT 8""",
        (g.user["id"],),
    ).fetchall()

    return {"stats": stats, "totals": totals, "records": records, "sexes": SEXES}


@bp.route("/", methods=("GET", "POST"))
@login_required
def index():
    db = get_db()

    if request.method == "POST":
        errors = []
        email = request.form.get("email", "").strip().lower()
        username = request.form.get("username", "").strip()

        if not EMAIL_RE.match(email):
            errors.append("Enter a valid email address.")
        if len(username) < 3:
            errors.append("Username must be at least 3 characters.")

        try:
            height_cm = to_float(request.form.get("height_cm"), minimum=50, maximum=260)
        except ValueError as exc:
            errors.append(f"Height {exc}.")
            height_cm = None

        try:
            birth_date = to_date(request.form.get("birth_date"))
        except ValueError as exc:
            errors.append(f"Birth date {exc}.")
            birth_date = None

        sex = request.form.get("sex", "").strip()
        if sex not in SEXES:
            sex = ""

        if email != g.user["email"]:
            if db.execute(
                "SELECT id FROM users WHERE email = ? AND id != ?", (email, g.user["id"])
            ).fetchone():
                errors.append("Email is already in use.")
        if username != g.user["username"]:
            if db.execute(
                "SELECT id FROM users WHERE username = ? AND id != ?",
                (username, g.user["id"]),
            ).fetchone():
                errors.append("Username is already taken.")

        new_password = request.form.get("new_password", "")
        current_password = request.form.get("current_password", "")
        if new_password:
            if not check_password_hash(g.user["password_hash"], current_password):
                errors.append("Current password is incorrect.")
            elif len(new_password) < 6:
                errors.append("New password must be at least 6 characters.")

        if errors:
            for error in errors:
                flash(error, "danger")
            return (
                render_template(
                    "profile.html", editing_profile=True, **_context()
                ),
                400,
            )

        password_hash = g.user["password_hash"]
        if new_password:
            password_hash = generate_password_hash(new_password)

        db.execute(
            """UPDATE users SET username = ?, email = ?, height_cm = ?, birth_date = ?,
                                sex = ?, password_hash = ?
               WHERE id = ?""",
            (username, email, height_cm, birth_date, sex, password_hash, g.user["id"]),
        )
        db.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("profile.index"))

    return render_template(
        "profile.html",
        editing_profile=False,
        **_context(),
    )
