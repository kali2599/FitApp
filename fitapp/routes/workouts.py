import datetime as dt

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

WORKOUT_TYPES = ["strength", "cardio", "hybrid"]
CARDIO_ACTIVITIES = ["run", "swimming", "spinning"]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _get_workout(workout_id):
    workout = get_db().execute(
        "SELECT * FROM workouts WHERE id = ? AND user_id = ?",
        (workout_id, g.user["id"]),
    ).fetchone()
    if workout is None:
        abort(404)
    return workout


def _get_day(workout_id, day_id):
    day = get_db().execute(
        "SELECT * FROM workout_days WHERE id = ? AND workout_id = ?",
        (day_id, workout_id),
    ).fetchone()
    if day is None:
        abort(404)
    return day


def _parse_num(value, conv, label, errors, **kwargs):
    try:
        return conv(value, **kwargs)
    except ValueError as exc:
        errors.append(f"{label} {exc}.")
        return None


def _parse_maxable(value, conv, label, errors, **kwargs):
    raw = (value or "").strip()
    if raw.lower() == "max":
        return "max"
    return _parse_num(value, conv, label, errors, **kwargs)


def _parse_reps(value, label, errors):
    return _parse_maxable(value, to_int, f"{label}: reps", errors, minimum=1, maximum=100000)


def _parse_plan_form():
    data = {
        "name": request.form.get("name", "").strip(),
        "workout_type": request.form.get("workout_type", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    errors = []
    if not data["name"]:
        errors.append("Workout name is required.")
    if data["workout_type"] not in WORKOUT_TYPES:
        errors.append("Choose a workout type (strength, cardio or hybrid).")
    return data, errors


def _parse_day_form(workout_type):
    errors = []
    day = {
        "name": request.form.get("day_name", "").strip(),
        "focus": request.form.get("day_focus", "").strip(),
        "notes": request.form.get("day_notes", "").strip(),
    }
    if not day["name"]:
        errors.append("Workout-module name is required.")

    keys = request.form.getlist("circuit_key")
    labels = request.form.getlist("circuit_label")
    rounds_l = request.form.getlist("circuit_rounds")
    rests_l = request.form.getlist("circuit_rest")
    circuits = []
    key_to_index = {}
    for i in range(max(len(keys), len(labels))):
        label = (labels[i] if i < len(labels) else "").strip()
        if not label:
            continue
        rounds = _parse_num(
            rounds_l[i] if i < len(rounds_l) else "", to_int,
            f"Circuit '{label}': rounds", errors, minimum=1, maximum=100,
        )
        rest = _parse_num(
            rests_l[i] if i < len(rests_l) else "", to_int,
            f"Circuit '{label}': rest", errors, minimum=0, maximum=3600,
        )
        key = (keys[i] if i < len(keys) else "").strip() or f"c{i}"
        key_to_index[key] = len(circuits)
        circuits.append(
            {"key": key, "label": label, "rounds": rounds or 3, "rest_sec": rest or 0}
        )

    kinds = request.form.getlist("ex_kind")
    names = request.form.getlist("ex_name")
    sets_l = request.form.getlist("ex_sets")
    reps_l = request.form.getlist("ex_reps")
    weights = request.form.getlist("ex_weight")
    durs = request.form.getlist("ex_duration")
    dists = request.form.getlist("ex_distance")
    rests = request.form.getlist("ex_rest")
    circs = request.form.getlist("ex_circuit")

    exercises = []
    members = {}
    for i, kind in enumerate(kinds):
        if kind not in ("strength", "cardio"):
            continue
        name = (names[i] if i < len(names) else "").strip()
        row = {
            "kind": kind, "name": name, "sets": None, "reps": None,
            "metric": None, "weight_kg": None, "duration_sec": None,
            "duration_min": None, "distance_km": None, "rest_sec": None,
            "circuit_index": None,
        }
        circuit_key = circs[i] if i < len(circs) else ""
        if circuit_key and circuit_key in key_to_index:
            row["circuit_index"] = key_to_index[circuit_key]
            members[row["circuit_index"]] = members.get(row["circuit_index"], 0) + 1

        if kind == "strength":
            if workout_type == "cardio":
                errors.append(f"'{name or 'Strength exercise'}': cardio workouts cannot contain strength exercises.")
            if not name:
                errors.append("Every strength exercise needs a name.")
            row["reps"] = _parse_reps(
                reps_l[i] if i < len(reps_l) else "", f"'{name}'", errors,
            )
            if row["circuit_index"] is None:
                row["sets"] = _parse_num(
                    sets_l[i] if i < len(sets_l) else "", to_int,
                    f"'{name}': sets", errors, minimum=1, maximum=100,
                )
                row["rest_sec"] = _parse_num(
                    rests[i] if i < len(rests) else "", to_int,
                    f"'{name}': rest", errors, minimum=0, maximum=3600,
                )
            row["weight_kg"] = _parse_maxable(
                weights[i] if i < len(weights) else "", to_float,
                f"'{name}': weight", errors, minimum=0, maximum=2000,
            )
            row["duration_sec"] = _parse_maxable(
                durs[i] if i < len(durs) else "", to_int,
                f"'{name}': duration", errors, minimum=1, maximum=86400,
            )
            if row["weight_kg"] is not None and row["duration_sec"] is not None:
                errors.append(f"'{name}': use weight or duration, not both.")
            row["metric"] = "duration" if row["duration_sec"] is not None else "weight"
        else:  # cardio
            if workout_type == "strength":
                errors.append(f"'{name or 'Cardio activity'}': strength workouts cannot contain cardio.")
            if name not in CARDIO_ACTIVITIES:
                errors.append("Cardio activity must be run, swimming or spinning.")
            row["duration_min"] = _parse_maxable(
                durs[i] if i < len(durs) else "", to_float,
                f"'{name or 'activity'}': duration", errors, minimum=0.1, maximum=1440,
            )
            if row["duration_min"] is None:
                errors.append(f"Cardio activity '{name or 'activity'}' needs a duration.")
            row["distance_km"] = _parse_num(
                dists[i] if i < len(dists) else "", to_float,
                f"'{name or 'activity'}': distance", errors, minimum=0, maximum=1000,
            )
        exercises.append(row)

    for idx, circuit in enumerate(circuits):
        if members.get(idx, 0) < 2:
            errors.append(f"Mini-circuit '{circuit['label']}' needs at least 2 exercises.")

    return day, circuits, exercises, errors


def _save_day(workout_id, day, circuits, exercises, day_id=None):
    db = get_db()
    if day_id is not None:
        db.execute(
            "UPDATE workout_days SET name = ?, focus = ?, notes = ? WHERE id = ? AND workout_id = ?",
            (day["name"], day["focus"], day["notes"], day_id, workout_id),
        )
        db.execute("DELETE FROM day_exercises WHERE workout_day_id = ?", (day_id,))
        db.execute("DELETE FROM circuits WHERE workout_day_id = ?", (day_id,))
    else:
        position = db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM workout_days WHERE workout_id = ?",
            (workout_id,),
        ).fetchone()[0]
        cursor = db.execute(
            "INSERT INTO workout_days (workout_id, position, name, focus, notes) VALUES (?, ?, ?, ?, ?)",
            (workout_id, position, day["name"], day["focus"], day["notes"]),
        )
        day_id = cursor.lastrowid

    circuit_ids = []
    for position, circuit in enumerate(circuits):
        cursor = db.execute(
            "INSERT INTO circuits (workout_day_id, position, label, rounds, rest_sec) VALUES (?, ?, ?, ?, ?)",
            (day_id, position, circuit["label"], circuit["rounds"], circuit["rest_sec"]),
        )
        circuit_ids.append(cursor.lastrowid)

    for position, ex in enumerate(exercises):
        circuit_id = circuit_ids[ex["circuit_index"]] if ex["circuit_index"] is not None else None
        db.execute(
            """INSERT INTO day_exercises
               (workout_day_id, circuit_id, position, kind, name, sets, reps, metric,
                weight_kg, duration_sec, duration_min, distance_km, rest_sec, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                day_id, circuit_id, position, ex["kind"], ex["name"], ex["sets"],
                ex["reps"], ex["metric"], ex["weight_kg"], ex["duration_sec"],
                ex["duration_min"], ex["distance_km"], ex["rest_sec"], ex.get("notes", ""),
            ),
        )
    db.commit()
    return day_id


def _day_form_data(day=None):
    if day is None:
        return {"name": "", "focus": "", "notes": "", "circuits": [], "exercises": []}
    db = get_db()
    circuits = db.execute(
        "SELECT * FROM circuits WHERE workout_day_id = ? ORDER BY position, id", (day["id"],)
    ).fetchall()
    exercises = db.execute(
        "SELECT * FROM day_exercises WHERE workout_day_id = ? ORDER BY position, id", (day["id"],)
    ).fetchall()
    key_by_id = {c["id"]: f"c{c['id']}" for c in circuits}
    ex_data = []
    for e in exercises:
        duration = e["duration_min"] if e["kind"] == "cardio" else e["duration_sec"]
        ex_data.append(
            {
                "kind": e["kind"],
                "name": e["name"],
                "sets": e["sets"] if e["sets"] is not None else "",
                "reps": e["reps"] if e["reps"] is not None else "",
                "metric": e["metric"] or "weight",
                "weight": e["weight_kg"] if e["weight_kg"] is not None else "",
                "duration": duration if duration is not None else "",
                "distance": e["distance_km"] if e["distance_km"] is not None else "",
                "rest": e["rest_sec"] if e["rest_sec"] is not None else "",
                "circuit": key_by_id.get(e["circuit_id"], ""),
            }
        )
    return {
        "name": day["name"],
        "focus": day["focus"] or "",
        "notes": day["notes"] or "",
        "circuits": [
            {"key": key_by_id[c["id"]], "label": c["label"], "rounds": c["rounds"], "rest": c["rest_sec"]}
            for c in circuits
        ],
        "exercises": ex_data,
    }


# --------------------------------------------------------------------------- #
# plans
# --------------------------------------------------------------------------- #
@bp.route("/")
@login_required
def index():
    workouts = get_db().execute(
        """SELECT w.*,
                  (SELECT COUNT(*) FROM workout_days d WHERE d.workout_id = w.id) AS day_count,
                  (SELECT COUNT(*) FROM day_exercises e
                     JOIN workout_days d ON d.id = e.workout_day_id
                    WHERE d.workout_id = w.id) AS exercise_count,
                  (SELECT COUNT(*) FROM workout_sessions s
                     JOIN workout_days d ON d.id = s.workout_day_id
                    WHERE d.workout_id = w.id) AS session_count
           FROM workouts w
           WHERE w.user_id = ?
           ORDER BY w.created_at DESC, w.id DESC""",
        (g.user["id"],),
    ).fetchall()
    return render_template("workouts/list.html", workouts=workouts, types=WORKOUT_TYPES)


@bp.route("/new", methods=("GET", "POST"))
@login_required
def new():
    if request.method == "POST":
        data, errors = _parse_plan_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "workouts/form.html", workout=data, types=WORKOUT_TYPES, editing=False
            ), 400
        db = get_db()
        cursor = db.execute(
            "INSERT INTO workouts (user_id, name, workout_type, notes) VALUES (?, ?, ?, ?)",
            (g.user["id"], data["name"], data["workout_type"], data["notes"]),
        )
        db.commit()
        flash("Workout created. Now add your workout-modules.", "success")
        return redirect(url_for("workouts.detail", workout_id=cursor.lastrowid))

    return render_template(
        "workouts/form.html",
        workout={"name": "", "workout_type": "", "notes": ""},
        types=WORKOUT_TYPES,
        editing=False,
    )


@bp.route("/<int:workout_id>")
@login_required
def detail(workout_id):
    workout = _get_workout(workout_id)
    db = get_db()
    days = db.execute(
        "SELECT * FROM workout_days WHERE workout_id = ? ORDER BY position, id", (workout_id,)
    ).fetchall()
    circuits = db.execute(
        """SELECT c.* FROM circuits c
           JOIN workout_days d ON d.id = c.workout_day_id
           WHERE d.workout_id = ? ORDER BY c.position, c.id""",
        (workout_id,),
    ).fetchall()
    exercises = db.execute(
        """SELECT e.* FROM day_exercises e
           JOIN workout_days d ON d.id = e.workout_day_id
           WHERE d.workout_id = ? ORDER BY e.position, e.id""",
        (workout_id,),
    ).fetchall()
    last_performed = dict(
        db.execute(
            """SELECT s.workout_day_id, MAX(s.performed_date) FROM workout_sessions s
               JOIN workout_days d ON d.id = s.workout_day_id
               WHERE d.workout_id = ? GROUP BY s.workout_day_id""",
            (workout_id,),
        ).fetchall()
    )

    circuits_by_day, members_by_circuit, standalone_by_day = {}, {}, {}
    for circuit in circuits:
        circuits_by_day.setdefault(circuit["workout_day_id"], []).append(circuit)
    for ex in exercises:
        if ex["circuit_id"] is None:
            standalone_by_day.setdefault(ex["workout_day_id"], []).append(ex)
        else:
            members_by_circuit.setdefault(ex["circuit_id"], []).append(ex)

    return render_template(
        "workouts/detail.html",
        workout=workout,
        days=days,
        circuits_by_day=circuits_by_day,
        members_by_circuit=members_by_circuit,
        standalone_by_day=standalone_by_day,
        last_performed=last_performed,
    )


@bp.route("/<int:workout_id>/edit", methods=("GET", "POST"))
@login_required
def edit(workout_id):
    workout = _get_workout(workout_id)
    if request.method == "POST":
        data, errors = _parse_plan_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "workouts/form.html", workout=data, types=WORKOUT_TYPES,
                editing=True, workout_id=workout_id,
            ), 400
        db = get_db()
        db.execute(
            "UPDATE workouts SET name = ?, workout_type = ?, notes = ? WHERE id = ? AND user_id = ?",
            (data["name"], data["workout_type"], data["notes"], workout_id, g.user["id"]),
        )
        db.commit()
        flash("Workout updated.", "success")
        return redirect(url_for("workouts.detail", workout_id=workout_id))

    return render_template(
        "workouts/form.html", workout=workout, types=WORKOUT_TYPES,
        editing=True, workout_id=workout_id,
    )


@bp.route("/<int:workout_id>/delete", methods=("POST",))
@login_required
def delete(workout_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM workouts WHERE id = ? AND user_id = ?", (workout_id, g.user["id"])
    )
    db.commit()
    flash("Workout deleted." if cursor.rowcount else "Workout not found.",
          "info" if cursor.rowcount else "warning")
    return redirect(url_for("workouts.index"))


# --------------------------------------------------------------------------- #
# workout days
# --------------------------------------------------------------------------- #
@bp.route("/<int:workout_id>/days/new", methods=("GET", "POST"))
@login_required
def day_new(workout_id):
    workout = _get_workout(workout_id)
    if request.method == "POST":
        day, circuits, exercises, errors = _parse_day_form(workout["workout_type"])
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "workouts/day_form.html", workout=workout, day_id=None,
                data={"name": day["name"], "focus": day["focus"], "notes": day["notes"],
                      "circuits": circuits, "exercises": exercises},
            ), 400
        _save_day(workout_id, day, circuits, exercises)
        flash("Workout-module added.", "success")
        return redirect(url_for("workouts.detail", workout_id=workout_id))

    return render_template(
        "workouts/day_form.html", workout=workout, day_id=None,
        data=_day_form_data(None),
    )


@bp.route("/<int:workout_id>/days/<int:day_id>/edit", methods=("GET", "POST"))
@login_required
def day_edit(workout_id, day_id):
    workout = _get_workout(workout_id)
    day = _get_day(workout_id, day_id)
    if request.method == "POST":
        data, circuits, exercises, errors = _parse_day_form(workout["workout_type"])
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "workouts/day_form.html", workout=workout, day_id=day_id,
                data={"name": data["name"], "focus": data["focus"], "notes": data["notes"],
                      "circuits": circuits, "exercises": exercises},
            ), 400
        _save_day(workout_id, data, circuits, exercises, day_id=day_id)
        flash("Workout-module updated.", "success")
        return redirect(url_for("workouts.detail", workout_id=workout_id))

    return render_template(
        "workouts/day_form.html", workout=workout, day_id=day_id,
        data=_day_form_data(day),
    )


@bp.route("/<int:workout_id>/days/<int:day_id>/delete", methods=("POST",))
@login_required
def day_delete(workout_id, day_id):
    _get_workout(workout_id)
    db = get_db()
    cursor = db.execute(
        "DELETE FROM workout_days WHERE id = ? AND workout_id = ?", (day_id, workout_id)
    )
    db.commit()
    flash("Workout-module deleted." if cursor.rowcount else "Module not found.",
          "info" if cursor.rowcount else "warning")
    return redirect(url_for("workouts.detail", workout_id=workout_id))


# --------------------------------------------------------------------------- #
# sessions (performed workouts)
# --------------------------------------------------------------------------- #
def _get_session(session_id):
    session = get_db().execute(
        "SELECT * FROM workout_sessions WHERE id = ? AND user_id = ?",
        (session_id, g.user["id"]),
    ).fetchone()
    if session is None:
        abort(404)
    return session


@bp.route("/<int:workout_id>/days/<int:day_id>/log", methods=("GET", "POST"))
@login_required
def log_day(workout_id, day_id):
    workout = _get_workout(workout_id)
    day = _get_day(workout_id, day_id)
    db = get_db()

    entries = db.execute(
        "SELECT * FROM day_exercises WHERE workout_day_id = ? ORDER BY position, id", (day_id,)
    ).fetchall()

    if request.method == "POST":
        errors = []
        try:
            performed_date = to_date(request.form.get("performed_date")) or dt.date.today().isoformat()
        except ValueError as exc:
            errors.append(f"Date {exc}.")
            performed_date = dt.date.today().isoformat()
        duration = _parse_num(request.form.get("duration_min"), to_int, "Duration", errors,
                              minimum=0, maximum=1440)
        calories = _parse_num(request.form.get("calories"), to_float, "Calories", errors,
                              minimum=0, maximum=20000)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "workouts/log_day.html", workout=workout, day=day,
                form=request.form, today=dt.date.today().isoformat(),
            ), 400

        cursor = db.execute(
            """INSERT INTO workout_sessions (user_id, workout_day_id, performed_date, duration_min, calories, notes)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (g.user["id"], day_id, performed_date, duration,
             calories, request.form.get("notes", "").strip()),
        )
        session_id = cursor.lastrowid

        circuit_labels = dict(
            db.execute("SELECT id, label FROM circuits WHERE workout_day_id = ?", (day_id,)).fetchall()
        )
        for position, ex in enumerate(entries):
            is_circuit = ex["circuit_id"] is not None
            db.execute(
                """INSERT INTO session_entries
                   (session_id, kind, name, circuit_label, sets, reps, metric, weight_kg,
                    duration_sec, duration_min, distance_km, position)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, ex["kind"], ex["name"],
                    circuit_labels.get(ex["circuit_id"]) if is_circuit else None,
                    ex["sets"], ex["reps"], ex["metric"], ex["weight_kg"],
                    ex["duration_sec"], ex["duration_min"], ex["distance_km"], position,
                ),
            )
        db.commit()
        flash("Workout logged. Review your actual numbers.", "success")
        return redirect(url_for("workouts.session_edit", session_id=session_id))

    return render_template(
        "workouts/log_day.html", workout=workout, day=day,
        form={}, today=dt.date.today().isoformat(),
    )


@bp.route("/sessions")
@login_required
def sessions():
    rows = get_db().execute(
        """SELECT s.*, d.name AS day_name, w.name AS workout_name, w.workout_type,
                  (SELECT COUNT(*) FROM session_entries e WHERE e.session_id = s.id) AS entry_count
           FROM workout_sessions s
           LEFT JOIN workout_days d ON d.id = s.workout_day_id
           LEFT JOIN workouts w ON w.id = d.workout_id
           WHERE s.user_id = ?
           ORDER BY s.performed_date DESC, s.id DESC""",
        (g.user["id"],),
    ).fetchall()
    return render_template("workouts/sessions.html", sessions=rows)


@bp.route("/sessions/<int:session_id>/edit", methods=("GET", "POST"))
@login_required
def session_edit(session_id):
    session = _get_session(session_id)
    db = get_db()
    entries = db.execute(
        "SELECT * FROM session_entries WHERE session_id = ? ORDER BY position, id", (session_id,)
    ).fetchall()

    if request.method == "POST":
        errors = []
        try:
            performed_date = to_date(request.form.get("performed_date"))
        except ValueError as exc:
            errors.append(f"Date {exc}.")
            performed_date = None
        if performed_date is None:
            errors.append("Date is required.")
        duration = _parse_num(request.form.get("duration_min"), to_int, "Duration", errors,
                              minimum=0, maximum=1440)
        calories = _parse_num(request.form.get("calories"), to_float, "Calories", errors,
                              minimum=0, maximum=20000)

        entry_updates = []
        ids = request.form.getlist("entry_id")
        kinds_l = request.form.getlist("entry_kind")
        metrics = request.form.getlist("entry_metric")
        reps_l = request.form.getlist("entry_reps")
        sets_l = request.form.getlist("entry_sets")
        weights = request.form.getlist("entry_weight")
        durs = request.form.getlist("entry_duration")
        dists = request.form.getlist("entry_distance")
        for i, entry_id in enumerate(ids):
            entry_updates.append(
                {
                    "id": entry_id,
                    "kind": kinds_l[i] if i < len(kinds_l) else "strength",
                    "metric": metrics[i] if i < len(metrics) else "",
                    "sets": _parse_num(sets_l[i] if i < len(sets_l) else "", to_int,
                                       "Sets", errors, minimum=1, maximum=1000),
                    "reps": _parse_reps(reps_l[i] if i < len(reps_l) else "", "Session",
                                        errors),
                    "weight": _parse_maxable(weights[i] if i < len(weights) else "", to_float,
                                             "Weight", errors, minimum=0, maximum=2000),
                    "duration": _parse_maxable(durs[i] if i < len(durs) else "", to_float,
                                               "Duration", errors, minimum=0, maximum=86400),
                    "distance": _parse_num(dists[i] if i < len(dists) else "", to_float,
                                           "Distance", errors, minimum=0, maximum=1000),
                }
            )

        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "workouts/session_form.html", session=session, entries=entries
            ), 400

        db.execute(
            """UPDATE workout_sessions SET performed_date = ?, duration_min = ?, calories = ?, notes = ?
               WHERE id = ? AND user_id = ?""",
            (performed_date, duration, calories,
             request.form.get("notes", "").strip(), session_id, g.user["id"]),
        )
        for update in entry_updates:
            if update["kind"] == "cardio":
                db.execute(
                    """UPDATE session_entries SET duration_min = ?, distance_km = ?
                       WHERE id = ? AND session_id = ?""",
                    (update["duration"], update["distance"], update["id"], session_id),
                )
            elif update["metric"] == "duration":
                db.execute(
                    """UPDATE session_entries SET sets = ?, reps = ?, duration_sec = ?
                       WHERE id = ? AND session_id = ?""",
                    (update["sets"], update["reps"], update["duration"], update["id"], session_id),
                )
            else:
                db.execute(
                    """UPDATE session_entries SET sets = ?, reps = ?, weight_kg = ?
                       WHERE id = ? AND session_id = ?""",
                    (update["sets"], update["reps"], update["weight"], update["id"], session_id),
                )
        db.commit()
        flash("Session updated.", "success")
        return redirect(url_for("workouts.sessions"))

    return render_template("workouts/session_form.html", session=session, entries=entries)


@bp.route("/sessions/<int:session_id>/delete", methods=("POST",))
@login_required
def session_delete(session_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM workout_sessions WHERE id = ? AND user_id = ?", (session_id, g.user["id"])
    )
    db.commit()
    flash("Session deleted." if cursor.rowcount else "Session not found.",
          "info" if cursor.rowcount else "warning")
    return redirect(url_for("workouts.sessions"))
