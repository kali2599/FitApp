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

from .. import insights
from ..auth import login_required
from ..db import get_db
from ..utils import to_date, to_float, to_int

bp = Blueprint("stats", __name__, url_prefix="/stats")

FIELDS = [
    ("weight_kg", "Weight", 20, 400),
    ("body_fat_pct", "Body fat", 1, 80),
    ("chest_cm", "Chest", 30, 250),
    ("waist_cm", "Waist", 30, 250),
    ("hip_cm", "Hip", 30, 250),
    ("arm_cm", "Arm", 10, 100),
]

INTENSITY_CHOICES = ["low", "moderate", "high"]
ACTIVITY_CHOICES = ["sedentary", "light", "moderate", "active", "very_active"]
GOAL_CHOICES = ["lose", "maintain", "gain"]
STRESS_CHOICES = ["low", "moderate", "high"]

LIFESTYLE_FIELDS = [
    ("sessions_per_week", "Training sessions per week", to_int, 0, 21),
    ("intensity", "Training intensity", None, None, None),
    ("session_duration_min", "Session length (minutes)", to_int, 5, 600),
    ("activity_level", "Daily activity level", None, None, None),
    ("sleep_hours", "Sleep per night (hours)", to_float, 0.5, 24),
    ("daily_calories", "Daily calorie intake", to_float, 500, 10000),
    ("goal_direction", "Goal direction", None, None, None),
    ("water_cups", "Water intake (cups/day)", to_float, 0, 30),
    ("stress_level", "Stress level", None, None, None),
]

CHOICE_FIELDS = {
    "intensity": INTENSITY_CHOICES,
    "activity_level": ACTIVITY_CHOICES,
    "goal_direction": GOAL_CHOICES,
    "stress_level": STRESS_CHOICES,
}


def _lifestyle_form(data=None):
    defaults = {
        "sessions_per_week": "",
        "intensity": "",
        "session_duration_min": "",
        "activity_level": "",
        "sleep_hours": "",
        "daily_calories": "",
        "goal_direction": "",
        "water_cups": "",
        "stress_level": "",
    }
    data = dict(data) if data else None
    if data is None:
        return defaults
    for key in defaults:
        if data.get(key) is not None and str(data.get(key)) != "":
            defaults[key] = data[key]
    return defaults


def _parse_lifestyle():
    values = _lifestyle_form(request.form)
    errors = []
    for field, label, converter, minimum, maximum in LIFESTYLE_FIELDS:
        raw = request.form.get(field, "").strip()
        if field in CHOICE_FIELDS:
            if raw and raw not in CHOICE_FIELDS[field]:
                errors.append(f"Pick a valid option for {label.lower()}.")
                continue
            values[field] = raw
            continue
        if not raw:
            values[field] = None
            continue
        try:
            values[field] = converter(raw, minimum=minimum, maximum=maximum)
        except ValueError as exc:
            errors.append(f"{label} {exc}.")
            values[field] = None
    return values, errors


def _latest_stat():
    db = get_db()
    return db.execute(
        """SELECT * FROM body_stats WHERE user_id = ?
           ORDER BY stat_date DESC, id DESC LIMIT 1""",
        (g.user["id"],),
    ).fetchone()


def _lifestyle_row():
    db = get_db()
    return db.execute(
        "SELECT * FROM user_lifestyle WHERE user_id = ?", (g.user["id"],)
    ).fetchone()


def _parse_form():
    data = {"stat_date": None, "notes": request.form.get("notes", "").strip()}
    errors = []
    try:
        data["stat_date"] = to_date(request.form.get("stat_date"))
    except ValueError as exc:
        errors.append(f"Date {exc}.")
    if data["stat_date"] is None:
        errors.append("Date is required.")

    for field, label, minimum, maximum in FIELDS:
        try:
            data[field] = to_float(request.form.get(field), minimum=minimum, maximum=maximum)
        except ValueError as exc:
            errors.append(f"{label} {exc}.")
            data[field] = None

    if all(data[field] is None for field, *_ in FIELDS):
        errors.append("Enter at least one measurement.")
    return data, errors


@bp.route("/")
@login_required
def index():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM body_stats WHERE user_id = ? ORDER BY stat_date DESC, id DESC",
        (g.user["id"],),
    ).fetchall()
    stat = rows[0] if rows else None
    lifestyle = _lifestyle_row()
    return render_template(
        "stats/list.html",
        rows=rows,
        fields=FIELDS,
        lifestyle=lifestyle,
        insight=insights.compute(g.user, stat, lifestyle),
        habits=bool(lifestyle),
    )


@bp.route("/lifestyle", methods=("GET", "POST"))
@login_required
def lifestyle():
    if request.method == "POST":
        values, errors = _parse_lifestyle()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "stats/lifestyle.html", values=_lifestyle_form(values), editing=bool(_lifestyle_row()),
                intensity_choices=INTENSITY_CHOICES, activity_choices=ACTIVITY_CHOICES,
                goal_choices=GOAL_CHOICES, stress_choices=STRESS_CHOICES,
            ), 400

        db = get_db()
        db.execute(
            """INSERT INTO user_lifestyle (user_id, sessions_per_week, intensity,
                                          session_duration_min, activity_level,
                                          sleep_hours, daily_calories, goal_direction,
                                          water_cups, stress_level)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 sessions_per_week = excluded.sessions_per_week,
                 intensity = excluded.intensity,
                 session_duration_min = excluded.session_duration_min,
                 activity_level = excluded.activity_level,
                 sleep_hours = excluded.sleep_hours,
                 daily_calories = excluded.daily_calories,
                 goal_direction = excluded.goal_direction,
                 water_cups = excluded.water_cups,
                 stress_level = excluded.stress_level""",
            (
                g.user["id"],
                values["sessions_per_week"],
                values["intensity"] or None,
                values["session_duration_min"],
                values["activity_level"] or None,
                values["sleep_hours"],
                values["daily_calories"],
                values["goal_direction"] or None,
                values["water_cups"],
                values["stress_level"] or None,
            ),
        )
        db.commit()
        flash("Lifestyle profile saved.", "success")
        return redirect(url_for("stats.index"))

    return render_template(
        "stats/lifestyle.html", values=_lifestyle_form(_lifestyle_row()), editing=bool(_lifestyle_row()),
        intensity_choices=INTENSITY_CHOICES, activity_choices=ACTIVITY_CHOICES,
        goal_choices=GOAL_CHOICES, stress_choices=STRESS_CHOICES,
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
                "stats/form.html", stat=data, fields=FIELDS, editing=False
            ), 400

        db = get_db()
        db.execute(
            """INSERT INTO body_stats (user_id, stat_date, weight_kg, body_fat_pct,
                                       chest_cm, waist_cm, hip_cm, arm_cm, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user["id"],
                data["stat_date"],
                data["weight_kg"],
                data["body_fat_pct"],
                data["chest_cm"],
                data["waist_cm"],
                data["hip_cm"],
                data["arm_cm"],
                data["notes"],
            ),
        )
        db.commit()
        flash("Body statistics saved.", "success")
        return redirect(url_for("stats.index"))

    return render_template(
        "stats/form.html",
        stat={"stat_date": request.args.get("date", ""), "notes": ""},
        fields=FIELDS,
        editing=False,
    )


@bp.route("/<int:stat_id>/edit", methods=("GET", "POST"))
@login_required
def edit(stat_id):
    db = get_db()
    stat = db.execute(
        "SELECT * FROM body_stats WHERE id = ? AND user_id = ?", (stat_id, g.user["id"])
    ).fetchone()
    if stat is None:
        abort(404)

    if request.method == "POST":
        data, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "stats/form.html", stat=data, fields=FIELDS, editing=True, stat_id=stat_id
            ), 400

        db.execute(
            """UPDATE body_stats SET stat_date = ?, weight_kg = ?, body_fat_pct = ?,
                                      chest_cm = ?, waist_cm = ?, hip_cm = ?,
                                      arm_cm = ?, notes = ?
               WHERE id = ? AND user_id = ?""",
            (
                data["stat_date"],
                data["weight_kg"],
                data["body_fat_pct"],
                data["chest_cm"],
                data["waist_cm"],
                data["hip_cm"],
                data["arm_cm"],
                data["notes"],
                stat_id,
                g.user["id"],
            ),
        )
        db.commit()
        flash("Body statistics updated.", "success")
        return redirect(url_for("stats.index"))

    return render_template(
        "stats/form.html", stat=stat, fields=FIELDS, editing=True, stat_id=stat_id
    )


@bp.route("/<int:stat_id>/delete", methods=("POST",))
@login_required
def delete(stat_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM body_stats WHERE id = ? AND user_id = ?", (stat_id, g.user["id"])
    )
    db.commit()
    if cursor.rowcount:
        flash("Body statistics deleted.", "info")
    else:
        flash("Entry not found.", "warning")
    return redirect(url_for("stats.index"))
