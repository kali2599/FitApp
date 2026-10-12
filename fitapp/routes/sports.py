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

SPORT_TYPES = ["gym", "cardio", "hybrid"]
CARDIO_ACTIVITIES = ["run", "swimming", "spinning"]


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


def _get_module(sport_id, module_id):
    module = get_db().execute(
        "SELECT * FROM workout_modules WHERE id = ? AND sport_id = ?",
        (module_id, sport_id),
    ).fetchone()
    if module is None:
        abort(404)
    return module


def _placement(day_id, module_id):
    return get_db().execute(
        "SELECT * FROM day_modules WHERE workout_day_id = ? AND module_id = ?",
        (day_id, module_id),
    ).fetchone()


def _catalog(db):
    return db.execute(
        "SELECT name, category, subcategory FROM exercises "
        "ORDER BY category, name COLLATE NOCASE"
    ).fetchall()


def _catalog_split(db):
    entries = _catalog(db)
    gym = [
        {"name": e["name"], "subcategory": e["subcategory"]}
        for e in entries if e["category"] == "gym"
    ]
    cardio = [e["name"] for e in entries if e["category"] == "cardio"]
    return {"gym": gym, "cardio": cardio}


def _catalog_cardio_names():
    db = get_db()
    return {row["name"].lower() for row in _catalog(db) if row["category"] == "cardio"}


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


def _parse_sport_form():
    data = {
        "name": request.form.get("name", "").strip(),
        "sport_type": request.form.get("sport_type", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    errors = []
    if not data["name"]:
        errors.append("Sport name is required.")
    if data["sport_type"] not in SPORT_TYPES:
        errors.append("Choose a sport type (gym, cardio or hybrid).")
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


def _parse_module_form(sport_type):
    errors = []
    module = {
        "name": request.form.get("module_name", "").strip(),
        "focus": request.form.get("module_focus", "").strip(),
        "notes": request.form.get("module_notes", "").strip(),
    }
    if not module["name"]:
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
        if kind not in ("gym", "cardio"):
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

        if kind == "gym":
            if sport_type == "cardio":
                errors.append(f"'{name or 'Gym exercise'}': cardio workouts cannot contain gym exercises.")
            if not name:
                errors.append("Every gym exercise needs a name.")
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
            if sport_type == "gym":
                errors.append(f"'{name or 'Cardio activity'}': gym workouts cannot contain cardio.")
            if name not in CARDIO_ACTIVITIES and name.lower() not in _catalog_cardio_names():
                errors.append("Cardio activity must be run, swimming, spinning or a stored cardio exercise.")
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

    return module, circuits, exercises, errors


def _save_module(sport_id, module, circuits, exercises, module_id=None):
    db = get_db()
    if module_id is not None:
        db.execute(
            "UPDATE workout_modules SET name = ?, focus = ?, notes = ? WHERE id = ? AND sport_id = ?",
            (module["name"], module["focus"], module["notes"], module_id, sport_id),
        )
        db.execute("DELETE FROM day_exercises WHERE workout_module_id = ?", (module_id,))
        db.execute("DELETE FROM circuits WHERE workout_module_id = ?", (module_id,))
    else:
        position = db.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM workout_modules WHERE sport_id = ?",
            (sport_id,),
        ).fetchone()[0]
        cursor = db.execute(
            "INSERT INTO workout_modules (sport_id, position, name, focus, notes) VALUES (?, ?, ?, ?, ?)",
            (sport_id, position, module["name"], module["focus"], module["notes"]),
        )
        module_id = cursor.lastrowid

    circuit_ids = []
    for position, circuit in enumerate(circuits):
        cursor = db.execute(
            "INSERT INTO circuits (workout_module_id, position, label, rounds, rest_sec) VALUES (?, ?, ?, ?, ?)",
            (module_id, position, circuit["label"], circuit["rounds"], circuit["rest_sec"]),
        )
        circuit_ids.append(cursor.lastrowid)

    for position, ex in enumerate(exercises):
        circuit_id = circuit_ids[ex["circuit_index"]] if ex["circuit_index"] is not None else None
        db.execute(
            """INSERT INTO day_exercises
               (workout_module_id, circuit_id, position, kind, name, sets, reps, metric,
                weight_kg, duration_sec, duration_min, distance_km, rest_sec, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                module_id, circuit_id, position, ex["kind"], ex["name"], ex["sets"],
                ex["reps"], ex["metric"], ex["weight_kg"], ex["duration_sec"],
                ex["duration_min"], ex["distance_km"], ex["rest_sec"], ex.get("notes", ""),
            ),
        )
    db.commit()
    return module_id


def _module_form_data(module=None):
    if module is None:
        return {"name": "", "focus": "", "notes": "", "circuits": [], "exercises": []}
    db = get_db()
    circuits = db.execute(
        "SELECT * FROM circuits WHERE workout_module_id = ? ORDER BY position, id", (module["id"],)
    ).fetchall()
    exercises = db.execute(
        "SELECT * FROM day_exercises WHERE workout_module_id = ? ORDER BY position, id", (module["id"],)
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
        "name": module["name"],
        "focus": module["focus"] or "",
        "notes": module["notes"] or "",
        "circuits": [
            {"key": key_by_id[c["id"]], "label": c["label"], "rounds": c["rounds"], "rest": c["rest_sec"]}
            for c in circuits
        ],
        "exercises": ex_data,
    }


def _workout_stats(db, sport_id):
    return db.execute(
        """SELECT w.*,
                  (SELECT COUNT(*) FROM workout_days d WHERE d.workout_id = w.id) AS day_count,
                  (SELECT COUNT(*) FROM day_modules dm
                     JOIN workout_days d ON d.id = dm.workout_day_id
                    WHERE d.workout_id = w.id) AS module_count,
                  (SELECT COUNT(*) FROM day_exercises e
                     JOIN day_modules dm ON dm.module_id = e.workout_module_id
                     JOIN workout_days d ON d.id = dm.workout_day_id
                    WHERE d.workout_id = w.id) AS exercise_count
           FROM workouts w
           WHERE w.sport_id = ?
           ORDER BY w.position, w.id""",
        (sport_id,),
    ).fetchall()


def _sport_library(db, sport_id):
    return db.execute(
        """SELECT m.id, m.position, m.name, m.focus, m.notes,
                  (SELECT COUNT(*) FROM day_exercises e
                    WHERE e.workout_module_id = m.id) AS exercise_count,
                  (SELECT COUNT(*) FROM circuits c
                    WHERE c.workout_module_id = m.id) AS circuit_count,
                  (SELECT COUNT(*) FROM day_modules dm
                    WHERE dm.module_id = m.id) AS day_count
           FROM workout_modules m
           WHERE m.sport_id = ?
           ORDER BY m.position, m.id""",
        (sport_id,),
    ).fetchall()


# --------------------------------------------------------------------------- #
# sports
# --------------------------------------------------------------------------- #
@bp.route("/")
@login_required
def index():
    rows = get_db().execute(
        """SELECT s.*,
                  (SELECT COUNT(*) FROM workouts w WHERE w.sport_id = s.id) AS workout_count,
                  (SELECT COUNT(*) FROM workout_days d
                     JOIN workouts w ON w.id = d.workout_id
                    WHERE w.sport_id = s.id) AS day_count,
                  (SELECT COUNT(*) FROM workout_modules m
                    WHERE m.sport_id = s.id) AS module_count
           FROM sports s
           WHERE s.user_id = ?
           ORDER BY s.created_at DESC, s.id DESC""",
        (g.user["id"],),
    ).fetchall()
    return render_template("sports/index.html", sports=rows, types=SPORT_TYPES)


@bp.route("/new", methods=("GET", "POST"))
@login_required
def new():
    if request.method == "POST":
        data, errors = _parse_sport_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/sport_form.html", sport=data, types=SPORT_TYPES, editing=False
            ), 400
        db = get_db()
        cursor = db.execute(
            "INSERT INTO sports (user_id, name, sport_type, notes) VALUES (?, ?, ?, ?)",
            (g.user["id"], data["name"], data["sport_type"], data["notes"]),
        )
        db.commit()
        flash("Sport created. Now add your workouts.", "success")
        return redirect(url_for("sports.detail", sport_id=cursor.lastrowid))

    return render_template(
        "sports/sport_form.html",
        sport={"name": "", "sport_type": "", "notes": ""},
        types=SPORT_TYPES,
        editing=False,
    )


@bp.route("/<int:sport_id>")
@login_required
def detail(sport_id):
    sport = _get_sport(sport_id)
    db = get_db()
    workouts = _workout_stats(db, sport_id)
    modules = _sport_library(db, sport_id)
    return render_template(
        "sports/detail.html", sport=sport, workouts=workouts,
        modules=modules, module_count=len(modules),
    )


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
                "sports/sport_form.html", sport=data, types=SPORT_TYPES,
                editing=True, sport_id=sport_id,
            ), 400
        db = get_db()
        db.execute(
            "UPDATE sports SET name = ?, sport_type = ?, notes = ? WHERE id = ? AND user_id = ?",
            (data["name"], data["sport_type"], data["notes"], sport_id, g.user["id"]),
        )
        db.commit()
        flash("Sport updated.", "success")
        return redirect(url_for("sports.detail", sport_id=sport_id))

    return render_template(
        "sports/sport_form.html", sport=sport, types=SPORT_TYPES,
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


def _day_modules(db, day_id):
    modules = db.execute(
        """SELECT m.*, dm.position AS placement_position
           FROM day_modules dm
           JOIN workout_modules m ON m.id = dm.module_id
           WHERE dm.workout_day_id = ?
           ORDER BY dm.position, m.id""",
        (day_id,),
    ).fetchall()
    module_ids = [m["id"] for m in modules]

    circuits = []
    exercises = []
    if module_ids:
        circuits = db.execute(
            f"SELECT * FROM circuits WHERE workout_module_id IN ({','.join('?' * len(module_ids))}) "
            "ORDER BY position, id",
            module_ids,
        ).fetchall()
        exercises = db.execute(
            f"SELECT * FROM day_exercises WHERE workout_module_id IN ({','.join('?' * len(module_ids))}) "
            "ORDER BY position, id",
            module_ids,
        ).fetchall()

    members_by_circuit = {}
    for ex in exercises:
        if ex["circuit_id"] is not None:
            members_by_circuit.setdefault(ex["circuit_id"], []).append(ex)

    day_modules = []
    for m in modules:
        day_modules.append(
            {
                "module": m,
                "circuits": [
                    {
                        "circuit": c,
                        "members": members_by_circuit.get(c["id"], []),
                    }
                    for c in circuits if c["workout_module_id"] == m["id"]
                ],
                "standalone": [
                    ex for ex in exercises
                    if ex["circuit_id"] is None and ex["workout_module_id"] == m["id"]
                ],
            }
        )
    return day_modules


@bp.route("/<int:sport_id>/workouts/<int:workout_id>")
@login_required
def workout_detail(sport_id, workout_id):
    sport = _get_sport(sport_id)
    workout = _get_workout(sport_id, workout_id)
    db = get_db()
    days = db.execute(
        """SELECT d.id, d.position, d.name,
                  (SELECT COUNT(*) FROM day_modules dm
                    WHERE dm.workout_day_id = d.id) AS module_count,
                  (SELECT COUNT(*) FROM day_exercises e
                     JOIN day_modules dm ON dm.module_id = e.workout_module_id
                    WHERE dm.workout_day_id = d.id) AS exercise_count,
                  (SELECT COUNT(*) FROM circuits c
                     JOIN day_modules dm ON dm.module_id = c.workout_module_id
                    WHERE dm.workout_day_id = d.id) AS circuit_count
           FROM workout_days d
           WHERE d.workout_id = ? ORDER BY d.position, d.id""",
        (workout_id,),
    ).fetchall()

    module_names = db.execute(
        """SELECT d.id AS day_id, m.name
           FROM day_modules dm
           JOIN workout_modules m ON m.id = dm.module_id
           JOIN workout_days d ON d.id = dm.workout_day_id
           WHERE d.workout_id = ?
           ORDER BY d.position, dm.position, m.id""",
        (workout_id,),
    ).fetchall()
    names_by_day = {}
    for row in module_names:
        names_by_day.setdefault(row["day_id"], []).append(row["name"])

    days_data = []
    for day in days:
        row = dict(day)
        row["module_names"] = names_by_day.get(day["id"], [])
        days_data.append(row)

    modules = _sport_library(db, sport_id)

    return render_template(
        "sports/workout_detail.html",
        sport=sport,
        workout=workout,
        days=days_data,
        modules=modules,
        module_count=len(modules),
    )


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/days/<int:day_id>")
@login_required
def day_detail(sport_id, workout_id, day_id):
    sport = _get_sport(sport_id)
    workout = _get_workout(sport_id, workout_id)
    day = _get_day(sport_id, workout_id, day_id)
    db = get_db()
    day_modules = _day_modules(db, day_id)
    return render_template(
        "sports/day_detail.html",
        sport=sport,
        workout=workout,
        day=day,
        day_modules=day_modules,
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
# module library (sport level)
# --------------------------------------------------------------------------- #
@bp.route("/<int:sport_id>/modules/new", methods=("GET", "POST"))
@login_required
def module_new(sport_id):
    sport = _get_sport(sport_id)
    db = get_db()
    if request.method == "POST":
        module, circuits, exercises, errors = _parse_module_form(sport["sport_type"])
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/module_form.html", sport=sport, module_id=None,
                catalog=_catalog_split(db),
                data={"name": module["name"], "focus": module["focus"], "notes": module["notes"],
                      "circuits": circuits, "exercises": exercises},
            ), 400
        _save_module(sport_id, module, circuits, exercises)
        flash("Module added to the library.", "success")
        return redirect(url_for("sports.detail", sport_id=sport_id))

    return render_template(
        "sports/module_form.html", sport=sport, module_id=None,
        catalog=_catalog_split(db),
        data=_module_form_data(None),
    )


@bp.route("/<int:sport_id>/modules/<int:module_id>/edit", methods=("GET", "POST"))
@login_required
def module_edit(sport_id, module_id):
    sport = _get_sport(sport_id)
    module = _get_module(sport_id, module_id)
    db = get_db()
    if request.method == "POST":
        data, circuits, exercises, errors = _parse_module_form(sport["sport_type"])
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "sports/module_form.html", sport=sport, module_id=module_id,
                catalog=_catalog_split(db),
                data={"name": data["name"], "focus": data["focus"], "notes": data["notes"],
                      "circuits": circuits, "exercises": exercises},
            ), 400
        _save_module(sport_id, data, circuits, exercises, module_id=module_id)
        flash("Module updated.", "success")
        return redirect(url_for("sports.detail", sport_id=sport_id))

    return render_template(
        "sports/module_form.html", sport=sport, module_id=module_id,
        catalog=_catalog_split(db),
        data=_module_form_data(module),
    )


@bp.route("/<int:sport_id>/modules/<int:module_id>/delete", methods=("POST",))
@login_required
def module_delete(sport_id, module_id):
    _get_sport(sport_id)
    db = get_db()
    cursor = db.execute(
        "DELETE FROM workout_modules WHERE id = ? AND sport_id = ?", (module_id, sport_id)
    )
    db.commit()
    flash("Module deleted from the library." if cursor.rowcount else "Module not found.",
          "info" if cursor.rowcount else "warning")
    return redirect(url_for("sports.detail", sport_id=sport_id))


def _next_day_position(db, day_id):
    return db.execute(
        "SELECT COALESCE(MAX(position), -1) + 1 FROM day_modules WHERE workout_day_id = ?",
        (day_id,),
    ).fetchone()[0]


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/days/<int:day_id>/modules/add", methods=("GET", "POST"))
@login_required
def module_add_existing(sport_id, workout_id, day_id):
    sport = _get_sport(sport_id)
    day = _get_day(sport_id, workout_id, day_id)
    db = get_db()
    candidates = db.execute(
        """SELECT m.id AS module_id, m.name AS module_name, m.focus
           FROM workout_modules m
           WHERE m.sport_id = ?
             AND m.id NOT IN (SELECT dm.module_id FROM day_modules dm
                               WHERE dm.workout_day_id = ?)
           ORDER BY m.position, m.id""",
        (sport_id, day_id),
    ).fetchall()

    if request.method == "POST":
        module_id = request.form.get("module_id", "").strip()
        module = None
        if module_id:
            module = db.execute(
                "SELECT * FROM workout_modules WHERE id = ? AND sport_id = ?",
                (module_id, sport_id),
            ).fetchone()
        if module is None:
            flash("Choose a module from the library.", "danger")
            return render_template(
                "sports/module_existing_form.html", sport=sport, day=day, candidates=candidates
            ), 400
        if _placement(day_id, module["id"]) is not None:
            flash("This module is already in this day.", "warning")
            return redirect(url_for("sports.day_detail", sport_id=sport_id, workout_id=workout_id, day_id=day_id))
        db.execute(
            "INSERT INTO day_modules (workout_day_id, module_id, position) VALUES (?, ?, ?)",
            (day_id, module["id"], _next_day_position(db, day_id)),
        )
        db.commit()
        flash("Module added to the day.", "success")
        return redirect(url_for("sports.day_detail", sport_id=sport_id, workout_id=workout_id, day_id=day_id))

    return render_template(
        "sports/module_existing_form.html", sport=sport, day=day, candidates=candidates
    )


@bp.route("/<int:sport_id>/workouts/<int:workout_id>/days/<int:day_id>/modules/<int:module_id>/remove", methods=("POST",))
@login_required
def module_remove_from_day(sport_id, workout_id, day_id, module_id):
    _get_sport(sport_id)
    _get_day(sport_id, workout_id, day_id)
    db = get_db()
    cursor = db.execute(
        "DELETE FROM day_modules WHERE workout_day_id = ? AND module_id = ?", (day_id, module_id)
    )
    db.commit()
    flash("Module removed from the day." if cursor.rowcount else "Module not in this day.",
          "info" if cursor.rowcount else "warning")
    return redirect(url_for("sports.day_detail", sport_id=sport_id, workout_id=workout_id, day_id=day_id))