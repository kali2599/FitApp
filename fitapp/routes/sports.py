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
from ..utils import to_float, to_int

bp = Blueprint("sports", __name__, url_prefix="/sports")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _get_sport(sport_id):
    sport = get_db().execute(
        "SELECT * FROM sports WHERE id = ? AND user_id = ?",
        (sport_id, g.user["id"]),
    ).fetchone()
    if sport is None:
        abort(404)
    return sport


def _get_workout(sport_id, workout_id):
    workout = get_db().execute(
        "SELECT * FROM workouts WHERE id = ? AND sport_id = ?",
        (workout_id, sport_id),
    ).fetchone()
    if workout is None:
        abort(404)
    return workout


def _get_day(sport_id, workout_id, day_id):
    _get_workout(sport_id, workout_id)
    day = get_db().execute(
        "SELECT * FROM workout_days WHERE id = ? AND workout_id = ?",
        (day_id, workout_id),
    ).fetchone()
    if day is None:
        abort(404)
    return day


def _parse_sport_form():
    data = {
        "name": request.form.get("name", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    errors = []
    if not data["name"]:
        errors.append("Sport name is required.")
    return data, errors


def _parse_workout_form():
    data = {
        "name": request.form.get("name", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    errors = []
    if not data["name"]:
        errors.append("Workout name is required.")
    return data, errors


def _parse_day_form():
    day = {"name": request.form.get("day_name", "").strip()}
    errors = []
    if not day["name"]:
        errors.append("Workout-day name is required.")
    return day, errors


def _workout_stats(db, sport_id):
    return db.execute(
        """SELECT w.*,
                  (SELECT COUNT(*) FROM workout_days d WHERE d.workout_id = w.id) AS day_count,
                  (SELECT COUNT(*) FROM day_entries e
                     JOIN workout_days d ON d.id = e.workout_day_id
                    WHERE d.workout_id = w.id) AS entry_count
           FROM workouts w
           WHERE w.sport_id = ?
           ORDER BY w.position, w.id""",
        (sport_id,),
    ).fetchall()


def _user_library(db, user_id):
    return db.execute(
        """SELECT m.id, m.position, m.name, m.notes,
                  (SELECT COUNT(*) FROM module_items i WHERE i.module_id = m.id) AS item_count,
                  (SELECT COUNT(*) FROM day_entries e WHERE e.module_id = m.id) AS day_count
           FROM workout_modules m
           WHERE m.user_id = ?
           ORDER BY m.position, m.id""",
        (user_id,),
    ).fetchall()


# --------------------------------------------------------------------------- #
# sports
# --------------------------------------------------------------------------- #
@bp.route("/")
@login_required
def index():
    db = get_db()
    rows = db.execute(
        """SELECT s.*,
                  (SELECT COUNT(*) FROM workouts w WHERE w.sport_id = s.id) AS workout_count,
                  (SELECT COUNT(*) FROM workout_days d
                     JOIN workouts w ON w.id = d.workout_id
                    WHERE w.sport_id = s.id) AS day_count
           FROM sports s
           WHERE s.user_id = ?
           ORDER BY s.created_at DESC, s.id DESC""",
        (g.user["id"],),
    ).fetchall()
    return render_template("sports/index.html", sports=rows)


@bp.route("/new", methods=("GET", "POST"))
@login_required
def new():
    if request.method == "POST":
        data, errors = _parse_sport_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/sport_form.html", sport=data, editing=False
            ), 400
        db = get_db()
        cursor = db.execute(
            "INSERT INTO sports (user_id, name, notes) VALUES (?, ?, ?)",
            (g.user["id"], data["name"], data["notes"]),
        )
        db.commit()
        flash("Sport created. Now add your workouts.", "success")
        return redirect(url_for("sports.detail", sport_id=cursor.lastrowid))

    return render_template(
        "sports/sport_form.html",
        sport={"name": "", "notes": ""},
        editing=False,
    )


@bp.route("/<int:sport_id>")
@login_required
def detail(sport_id):
    sport = _get_sport(sport_id)
    db = get_db()
    workouts = _workout_stats(db, sport_id)
    return render_template("sports/detail.html", sport=sport, workouts=workouts)


@bp.route("/<int:sport_id>/edit", methods=("GET", "POST"))
@login_required
def edit(sport_id):
    sport = _get_sport(sport_id)
    if request.method == "POST":
        data, errors = _parse_sport_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/sport_form.html", sport=data,
                editing=True, sport_id=sport_id,
            ), 400
        db = get_db()
        db.execute(
            "UPDATE sports SET name = ?, notes = ? WHERE id = ? AND user_id = ?",
            (data["name"], data["notes"], sport_id, g.user["id"]),
        )
        db.commit()
        flash("Sport updated.", "success")
        return redirect(url_for("sports.detail", sport_id=sport_id))

    return render_template(
        "sports/sport_form.html", sport=sport,
        editing=True, sport_id=sport_id,
    )


@bp.route("/<int:sport_id>/delete", methods=("POST",))
@login_required
def delete(sport_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM sports WHERE id = ? AND user_id = ?", (sport_id, g.user["id"])
    )
    db.commit()
    flash("Sport deleted." if cursor.rowcount else "Sport not found.",
          "info" if cursor.rowcount else "warning")
    return redirect(url_for("sports.index"))


# --------------------------------------------------------------------------- #
# workouts (inside a sport)
# --------------------------------------------------------------------------- #
@bp.route("/<int:sport_id>/workouts/new", methods=("GET", "POST"))
@login_required
def workout_new(sport_id):
    sport = _get_sport(sport_id)
    if request.method == "POST":
        data, errors = _parse_workout_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/workout_form.html", sport=sport, workout=data, editing=False
            ), 400
        db = get_db()
        position = db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM workouts WHERE sport_id = ?",
            (sport_id,),
        ).fetchone()[0]
        cursor = db.execute(
            "INSERT INTO workouts (sport_id, position, name, notes) VALUES (?, ?, ?, ?)",
            (sport_id, position, data["name"], data["notes"]),
        )
        db.commit()
        flash("Workout created. Now add your workout days.", "success")
        return redirect(url_for("sports.workout_detail", sport_id=sport_id, workout_id=cursor.lastrowid))

    return render_template(
        "sports/workout_form.html", sport=sport,
        workout={"name": "", "notes": ""}, editing=False,
    )


@bp.route("/<int:sport_id>/workouts/<int:workout_id>")
@login_required
def workout_detail(sport_id, workout_id):
    sport = _get_sport(sport_id)
    workout = _get_workout(sport_id, workout_id)
    db = get_db()
    days = db.execute(
        """SELECT d.id, d.position, d.name,
                  (SELECT COUNT(*) FROM day_entries e WHERE e.workout_day_id = d.id) AS entry_count
           FROM workout_days d
           WHERE d.workout_id = ? ORDER BY d.position, d.id""",
        (workout_id,),
    ).fetchall()
    days_data = [dict(day) for day in days]

    return render_template(
        "sports/workout_detail.html",
        sport=sport,
        workout=workout,
        days=days_data,
    )


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/days/<int:day_id>")
@login_required
def day_detail(sport_id, workout_id, day_id):
    sport = _get_sport(sport_id)
    workout = _get_workout(sport_id, workout_id)
    day = _get_day(sport_id, workout_id, day_id)
    db = get_db()
    entries = _day_entries(db, day_id)
    return render_template(
        "sports/day_detail.html",
        sport=sport,
        workout=workout,
        day=day,
        entries=entries,
    )


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/edit", methods=("GET", "POST"))
@login_required
def workout_edit(sport_id, workout_id):
    sport = _get_sport(sport_id)
    workout = _get_workout(sport_id, workout_id)
    if request.method == "POST":
        data, errors = _parse_workout_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/workout_form.html", sport=sport, workout=data,
                editing=True, workout_id=workout_id,
            ), 400
        db = get_db()
        db.execute(
            "UPDATE workouts SET name = ?, notes = ? WHERE id = ? AND sport_id = ?",
            (data["name"], data["notes"], workout_id, sport_id),
        )
        db.commit()
        flash("Workout updated.", "success")
        return redirect(url_for("sports.workout_detail", sport_id=sport_id, workout_id=workout_id))

    return render_template(
        "sports/workout_form.html", sport=sport, workout=workout,
        editing=True, workout_id=workout_id,
    )


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/delete", methods=("POST",))
@login_required
def workout_delete(sport_id, workout_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM workouts WHERE id = ? AND sport_id = ?", (workout_id, sport_id)
    )
    db.commit()
    flash("Workout deleted." if cursor.rowcount else "Workout not found.",
          "info" if cursor.rowcount else "warning")
    return redirect(url_for("sports.detail", sport_id=sport_id))


# --------------------------------------------------------------------------- #
# workout days
# --------------------------------------------------------------------------- #
@bp.route("/<int:sport_id>/workouts/<int:workout_id>/days/new", methods=("GET", "POST"))
@login_required
def day_new(sport_id, workout_id):
    _get_sport(sport_id)
    _get_workout(sport_id, workout_id)
    if request.method == "POST":
        day, errors = _parse_day_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/day_form.html", editing=False,
                back_url=url_for("sports.workout_detail", sport_id=sport_id, workout_id=workout_id),
            ), 400
        db = get_db()
        position = db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM workout_days WHERE workout_id = ?",
            (workout_id,),
        ).fetchone()[0]
        db.execute(
            "INSERT INTO workout_days (workout_id, position, name) VALUES (?, ?, ?)",
            (workout_id, position, day["name"]),
        )
        db.commit()
        flash("Workout-day added.", "success")
        return redirect(url_for("sports.workout_detail", sport_id=sport_id, workout_id=workout_id))

    return render_template(
        "sports/day_form.html", editing=False,
        back_url=url_for("sports.workout_detail", sport_id=sport_id, workout_id=workout_id),
    )


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/days/<int:day_id>/edit", methods=("GET", "POST"))
@login_required
def day_edit(sport_id, workout_id, day_id):
    _get_workout(sport_id, workout_id)
    day = _get_day(sport_id, workout_id, day_id)
    back_url = url_for("sports.workout_detail", sport_id=sport_id, workout_id=workout_id)
    if request.method == "POST":
        data, errors = _parse_day_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/day_form.html", editing=True, day_name=day["name"], back_url=back_url
            ), 400
        db = get_db()
        db.execute(
            "UPDATE workout_days SET name = ? WHERE id = ? AND workout_id = ?",
            (data["name"], day_id, workout_id),
        )
        db.commit()
        flash("Workout-day updated.", "success")
        return redirect(url_for("sports.workout_detail", sport_id=sport_id, workout_id=workout_id))

    return render_template("sports/day_form.html", editing=True, day_name=day["name"], back_url=back_url)


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/days/<int:day_id>/delete", methods=("POST",))
@login_required
def day_delete(sport_id, workout_id, day_id):
    _get_sport(sport_id)
    db = get_db()
    cursor = db.execute(
        "DELETE FROM workout_days WHERE id = ? AND workout_id = ?", (day_id, workout_id)
    )
    db.commit()
    flash("Workout-day deleted." if cursor.rowcount else "Day not found.",
          "info" if cursor.rowcount else "warning")
    return redirect(url_for("sports.workout_detail", sport_id=sport_id, workout_id=workout_id))


# --------------------------------------------------------------------------- #
# day builder
# --------------------------------------------------------------------------- #
def _next_day_position(db, day_id):
    return db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM day_entries WHERE workout_day_id = ?",
        (day_id,),
    ).fetchone()[0]


def _library_item(db, prefix, item_id):
    """Resolve a builder selection to (entry_column, item_row), user-scoped."""
    tables = {
        "m": ("module_id", "workout_modules"),
        "c": ("circuit_id", "library_circuits"),
        "e": ("exercise_id", "library_exercises"),
    }
    if prefix not in tables:
        return None, None
    column, table = tables[prefix]
    row = db.execute(
        f"SELECT id FROM {table} WHERE id = ? AND user_id = ?",
        (item_id, g.user["id"]),
    ).fetchone()
    return column, row


def _expand_entry_sets(db, entry_id, module_id=None, circuit_id=None, exercise_id=None):
    """Populate day_entry_sets for a freshly added entry."""
    planned = []
    if module_id is not None:
        items = db.execute(
            "SELECT exercise_id, circuit_id FROM module_items WHERE module_id = ? "
            "ORDER BY position, id",
            (module_id,),
        ).fetchall()
        for item in items:
            if item["exercise_id"] is not None:
                planned.append((item["exercise_id"], None))
            else:
                members = db.execute(
                    "SELECT exercise_id FROM library_circuit_members WHERE circuit_id = ? "
                    "ORDER BY position, id",
                    (item["circuit_id"],),
                ).fetchall()
                planned.extend((m["exercise_id"], item["circuit_id"]) for m in members)
    elif circuit_id is not None:
        members = db.execute(
            "SELECT exercise_id FROM library_circuit_members WHERE circuit_id = ? "
            "ORDER BY position, id",
            (circuit_id,),
        ).fetchall()
        planned.extend((m["exercise_id"], circuit_id) for m in members)
    elif exercise_id is not None:
        planned.append((exercise_id, None))

    for position, (ex_id, circ_id) in enumerate(planned):
        db.execute(
            "INSERT INTO day_entry_sets (day_entry_id, position, exercise_id, circuit_id) "
            "VALUES (?, ?, ?, ?)",
            (entry_id, position, ex_id, circ_id),
        )


def _parse_metric(raw, conv, label, errors, **kwargs):
    raw = (raw or "").strip()
    if raw == "":
        return None
    if raw.lower() == "max":
        return "max"
    try:
        return conv(raw, **kwargs)
    except ValueError as exc:
        errors.append(f"{label} {exc}.")
        return None


def _entry_sets(db, entry_id):
    return db.execute(
        """SELECT s.*, e.name AS exercise_name, e.label AS exercise_label
           FROM day_entry_sets s
           JOIN library_exercises e ON e.id = s.exercise_id
           WHERE s.day_entry_id = ?
           ORDER BY s.position, s.id""",
        (entry_id,),
    ).fetchall()


def _entry_groups(db, sets):
    """Group a day entry's sets into standalone + circuit blocks, in order."""
    groups = []
    index = {}
    for row in sets:
        key = row["circuit_id"]
        if key not in index:
            index[key] = len(groups)
            groups.append({"circuit": None, "sets": []})
        groups[index[key]]["sets"].append(row)
    for group in groups:
        circuit_id = group["sets"][0]["circuit_id"]
        if circuit_id is not None:
            group["circuit"] = db.execute(
                "SELECT * FROM library_circuits WHERE id = ?", (circuit_id,)
            ).fetchone()
    return groups


def _day_entries(db, day_id):
    entries = db.execute(
        """SELECT de.*, m.name AS module_name, c.name AS circuit_name, e.name AS exercise_name
           FROM day_entries de
           LEFT JOIN workout_modules m ON m.id = de.module_id
           LEFT JOIN library_circuits c ON c.id = de.circuit_id
           LEFT JOIN library_exercises e ON e.id = de.exercise_id
           WHERE de.workout_day_id = ?
           ORDER BY de.position, de.id""",
        (day_id,),
    ).fetchall()
    out = []
    for entry in entries:
        sets = _entry_sets(db, entry["id"])
        out.append({"entry": entry, "groups": _entry_groups(db, sets), "sets": sets})
    return out


def _build_context(db, sport_id, workout_id, day):
    return {
        "sport": _get_sport(sport_id),
        "workout": _get_workout(sport_id, workout_id),
        "day": day,
        "modules": _user_library(db, g.user["id"]),
        "exercises": db.execute(
            "SELECT id, name FROM library_exercises WHERE user_id = ? ORDER BY position, id",
            (g.user["id"],),
        ).fetchall(),
        "circuits": db.execute(
            "SELECT id, name FROM library_circuits WHERE user_id = ? ORDER BY position, id",
            (g.user["id"],),
        ).fetchall(),
        "entries": _day_entries(db, day["id"]),
    }


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/days/<int:day_id>/build", methods=("GET", "POST"))
@login_required
def day_build(sport_id, workout_id, day_id):
    _get_sport(sport_id)
    _get_workout(sport_id, workout_id)
    day = _get_day(sport_id, workout_id, day_id)
    db = get_db()

    if request.method == "POST":
        action = request.form.get("action", "add")
        if action == "add":
            target = (request.form.get("target") or "").strip()
            try:
                prefix, raw_id = target.split(":", 1)
                item_id = int(raw_id)
            except ValueError:
                prefix, item_id = "", 0
            column, item = _library_item(db, prefix, item_id)
            if item is None:
                flash("Choose an item from your library.", "danger")
                return render_template(
                    "sports/day_build.html", **_build_context(db, sport_id, workout_id, day)
                ), 400
            cursor = db.execute(
                "INSERT INTO day_entries (workout_day_id, position, module_id, circuit_id, exercise_id) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    day_id,
                    _next_day_position(db, day_id),
                    item["id"] if column == "module_id" else None,
                    item["id"] if column == "circuit_id" else None,
                    item["id"] if column == "exercise_id" else None,
                ),
            )
            _expand_entry_sets(db, cursor.lastrowid, **{column: item["id"]})
            db.commit()
            flash("Item added to the day.", "success")
            return redirect(url_for("sports.day_build", sport_id=sport_id,
                                    workout_id=workout_id, day_id=day_id))

        # action == save: persist prescriptions
        errors = []
        valid = {
            row["id"]
            for row in db.execute(
                "SELECT s.id FROM day_entry_sets s JOIN day_entries de ON de.id = s.day_entry_id "
                "WHERE de.workout_day_id = ?",
                (day_id,),
            ).fetchall()
        }
        for raw_id in request.form.getlist("set_id"):
            try:
                set_id = int(raw_id)
            except ValueError:
                continue
            if set_id not in valid:
                continue
            db.execute(
                "UPDATE day_entry_sets SET sets = ?, reps = ?, weight_kg = ?, duration_sec = ?, "
                "duration_min = ?, distance_km = ?, rest_sec = ?, "
                "distance_m = ?, pace_km_per_min = ?, rounds = ?, notes = ? WHERE id = ?",
                (
                    _parse_metric(request.form.get(f"sets_{set_id}"), to_int, "Sets", errors, minimum=0, maximum=100),
                    _parse_metric(request.form.get(f"reps_{set_id}"), to_int, "Reps", errors, minimum=0, maximum=10000),
                    _parse_metric(request.form.get(f"weight_{set_id}"), to_float, "Weight", errors, minimum=0, maximum=1000),
                    _parse_metric(request.form.get(f"duration_sec_{set_id}"), to_int, "Duration", errors, minimum=0, maximum=86400),
                    _parse_metric(request.form.get(f"duration_min_{set_id}"), to_float, "Duration", errors, minimum=0, maximum=1440),
                    _parse_metric(request.form.get(f"distance_{set_id}"), to_float, "Distance", errors, minimum=0, maximum=1000),
                    _parse_metric(request.form.get(f"rest_{set_id}"), to_int, "Rest", errors, minimum=0, maximum=3600),
                    _parse_metric(request.form.get(f"distance_m_{set_id}"), to_float, "Distance", errors, minimum=0, maximum=100000),
                    _parse_metric(request.form.get(f"pace_{set_id}"), to_float, "Pace", errors, minimum=0, maximum=100),
                    _parse_metric(request.form.get(f"rounds_{set_id}"), to_int, "Rounds", errors, minimum=0, maximum=1000),
                    request.form.get(f"notes_{set_id}", "").strip(),
                    set_id,
                ),
            )
        if errors:
            db.rollback()
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/day_build.html", **_build_context(db, sport_id, workout_id, day)
            ), 400
        db.commit()
        flash("Prescriptions saved.", "success")
        return redirect(url_for("sports.day_detail", sport_id=sport_id,
                                workout_id=workout_id, day_id=day_id))

    return render_template("sports/day_build.html", **_build_context(db, sport_id, workout_id, day))


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/days/<int:day_id>/entries/<int:entry_id>/remove", methods=("POST",))
@login_required
def day_entry_remove(sport_id, workout_id, day_id, entry_id):
    _get_sport(sport_id)
    _get_day(sport_id, workout_id, day_id)
    db = get_db()
    cursor = db.execute(
        "DELETE FROM day_entries WHERE id = ? AND workout_day_id = ?", (entry_id, day_id)
    )
    db.commit()
    flash("Item removed from the day." if cursor.rowcount else "Item not found.",
          "info" if cursor.rowcount else "warning")
    return redirect(url_for("sports.day_build", sport_id=sport_id,
                            workout_id=workout_id, day_id=day_id))
