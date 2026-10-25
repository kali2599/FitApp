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
from ..utils import to_int

bp = Blueprint("library", __name__, url_prefix="/library")

MUSCLES = [
    "Chest",
    "Back",
    "Lats",
    "Traps",
    "Shoulders",
    "Biceps",
    "Triceps",
    "Forearms",
    "Abs",
    "Obliques",
    "Lower back",
    "Glutes",
    "Quads",
    "Hamstrings",
    "Calves",
    "Hip flexors",
    "Adductors",
    "Abductors",
    "Neck",
    "Full body",
]
LABELS = ["strength", "skill", "cardio"]


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _get_exercise(exercise_id):
    row = get_db().execute(
        "SELECT * FROM library_exercises WHERE id = ? AND user_id = ?",
        (exercise_id, g.user["id"]),
    ).fetchone()
    if row is None:
        abort(404)
    return row


def _get_circuit(circuit_id):
    row = get_db().execute(
        "SELECT * FROM library_circuits WHERE id = ? AND user_id = ?",
        (circuit_id, g.user["id"]),
    ).fetchone()
    if row is None:
        abort(404)
    return row


def _get_module(module_id):
    row = get_db().execute(
        "SELECT * FROM workout_modules WHERE id = ? AND user_id = ?",
        (module_id, g.user["id"]),
    ).fetchone()
    if row is None:
        abort(404)
    return row


def _next_position(db, table, user_id):
    return db.execute(
        f"SELECT COALESCE(MAX(position), -1) + 1 FROM {table} WHERE user_id = ?",
        (user_id,),
    ).fetchone()[0]


def _parse_num(value, conv, label, errors, **kwargs):
    try:
        return conv(value, **kwargs)
    except ValueError as exc:
        errors.append(f"{label} {exc}.")
        return None


def _one_library(db, user_id):
    """Everything the library page needs, scoped to one user."""
    modules = db.execute(
        """SELECT m.id, m.name, m.notes,
                  (SELECT COUNT(*) FROM module_items i WHERE i.module_id = m.id) AS item_count,
                  (SELECT COUNT(*) FROM day_entries e WHERE e.module_id = m.id) AS day_count
           FROM workout_modules m
           WHERE m.user_id = ?
           ORDER BY m.position, m.id""",
        (user_id,),
    ).fetchall()
    exercises = db.execute(
        """SELECT e.*,
                  (SELECT COUNT(*) FROM module_items i WHERE i.exercise_id = e.id) AS module_count,
                  (SELECT COUNT(*) FROM library_circuit_members c WHERE c.exercise_id = e.id) AS circuit_count,
                  (SELECT COUNT(*) FROM day_entry_sets s WHERE s.exercise_id = e.id) AS day_count
           FROM library_exercises e
           WHERE e.user_id = ?
           ORDER BY e.position, e.id""",
        (user_id,),
    ).fetchall()
    circuits = db.execute(
        """SELECT c.*,
                  (SELECT COUNT(*) FROM library_circuit_members m WHERE m.circuit_id = c.id) AS member_count,
                  (SELECT COUNT(*) FROM module_items i WHERE i.circuit_id = c.id) AS module_count,
                  (SELECT COUNT(*) FROM day_entries e WHERE e.circuit_id = c.id) AS day_count
           FROM library_circuits c
           WHERE c.user_id = ?
           ORDER BY c.position, c.id""",
        (user_id,),
    ).fetchall()
    return modules, exercises, circuits


def _circuit_members(db, circuit_id):
    return db.execute(
        """SELECT e.id, e.name FROM library_circuit_members m
           JOIN library_exercises e ON e.id = m.exercise_id
           WHERE m.circuit_id = ?
           ORDER BY m.position, m.id""",
        (circuit_id,),
    ).fetchall()


def _module_items(db, module_id):
    return db.execute(
        """SELECT i.position, i.exercise_id, i.circuit_id,
                  e.name AS exercise_name, c.name AS circuit_name
           FROM module_items i
           LEFT JOIN library_exercises e ON e.id = i.exercise_id
           LEFT JOIN library_circuits c ON c.id = i.circuit_id
           WHERE i.module_id = ?
           ORDER BY i.position, i.id""",
        (module_id,),
    ).fetchall()


def _sync_module_days(db, module_id):
    """Re-expand every day placement of a module after its item list changed.

    Existing prescriptions are carried over by (circuit, exercise) so editing a
    module never wipes the numbers a user already entered for that day.
    """
    entries = [
        row["id"]
        for row in db.execute(
            "SELECT id FROM day_entries WHERE module_id = ?", (module_id,)
        ).fetchall()
    ]
    if not entries:
        return

    items = db.execute(
        "SELECT * FROM module_items WHERE module_id = ? ORDER BY position, id",
        (module_id,),
    ).fetchall()

    planned = []
    for item in items:
        if item["exercise_id"] is not None:
            planned.append((None, item["exercise_id"]))
            continue
        for member in _circuit_members(db, item["circuit_id"]):
            planned.append((item["circuit_id"], member["id"]))

    for entry in entries:
        existing = {}
        for row in db.execute(
            "SELECT * FROM day_entry_sets WHERE day_entry_id = ? ORDER BY position, id",
            (entry,),
        ).fetchall():
            existing.setdefault((row["circuit_id"], row["exercise_id"]), []).append(row)
        db.execute("DELETE FROM day_entry_sets WHERE day_entry_id = ?", (entry,))
        for position, (circuit_id, exercise_id) in enumerate(planned):
            source = existing.get((circuit_id, exercise_id))
            src = source.pop(0) if source else None
            db.execute(
                "INSERT INTO day_entry_sets "
                "(day_entry_id, position, exercise_id, circuit_id, sets, reps, weight_kg, "
                " duration_sec, duration_min, distance_km, rest_sec, distance_m, "
                " pace_km_per_min, rounds, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    entry,
                    position,
                    exercise_id,
                    circuit_id,
                    src["sets"] if src else None,
                    src["reps"] if src else None,
                    src["weight_kg"] if src else None,
                    src["duration_sec"] if src else None,
                    src["duration_min"] if src else None,
                    src["distance_km"] if src else None,
                    src["rest_sec"] if src else None,
                    src["distance_m"] if src else None,
                    src["pace_km_per_min"] if src else None,
                    src["rounds"] if src else None,
                    src["notes"] if src else None,
                ),
            )


# --------------------------------------------------------------------------- #
# index (two tabs)
# --------------------------------------------------------------------------- #
@bp.route("/", strict_slashes=False)
@login_required
def index():
    db = get_db()
    tab = request.args.get("tab", "modules")
    if tab not in ("modules", "exercises"):
        tab = "modules"
    modules, exercises, circuits = _one_library(db, g.user["id"])
    return render_template(
        "library/index.html",
        tab=tab,
        modules=modules,
        exercises=exercises,
        circuits=circuits,
        muscle_count=len(MUSCLES),
    )


# --------------------------------------------------------------------------- #
# exercises
# --------------------------------------------------------------------------- #
def _parse_exercise_form():
    data = {
        "name": request.form.get("name", "").strip(),
        "label": request.form.get("label", "").strip().lower() or None,
        "notes": request.form.get("notes", "").strip(),
        "muscles": [m for m in request.form.getlist("muscles") if m in MUSCLES],
    }
    errors = []
    if not data["name"]:
        errors.append("Exercise name is required.")
    if data["label"] is not None and data["label"] not in LABELS:
        errors.append("Choose a valid label.")
    submitted = [m for m in request.form.getlist("muscles") if m]
    if len(submitted) != len(data["muscles"]):
        errors.append("Unknown muscle group.")
    return data, errors


def _exercise_form_context(data, editing, exercise_id=None):
    return {
        "exercise": data,
        "muscles": MUSCLES,
        "labels": LABELS,
        "editing": editing,
        "exercise_id": exercise_id,
    }


def _duplicate_exercise(db, name, exercise_id=None):
    row = db.execute(
        "SELECT id FROM library_exercises WHERE user_id = ? AND lower(name) = lower(?)",
        (g.user["id"], name),
    ).fetchone()
    return row is not None and row["id"] != exercise_id


@bp.route("/exercises/new", methods=("GET", "POST"))
@login_required
def exercise_new():
    if request.method == "POST":
        data, errors = _parse_exercise_form()
        db = get_db()
        if not errors and _duplicate_exercise(db, data["name"]):
            errors.append(f"You already have an exercise named \"{data['name']}\".")
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "library/exercise_form.html", **_exercise_form_context(data, editing=False)
            ), 400

        db.execute(
            "INSERT INTO library_exercises (user_id, position, name, muscles, label, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                g.user["id"],
                _next_position(db, "library_exercises", g.user["id"]),
                data["name"],
                ",".join(data["muscles"]),
                data["label"],
                data["notes"],
            ),
        )
        db.commit()
        flash("Exercise added to your library.", "success")
        return redirect(url_for("library.index", tab="exercises"))

    return render_template(
        "library/exercise_form.html",
        **_exercise_form_context({"name": "", "label": "", "notes": "", "muscles": []}, editing=False),
    )


@bp.route("/exercises/<int:exercise_id>/edit", methods=("GET", "POST"))
@login_required
def exercise_edit(exercise_id):
    exercise = _get_exercise(exercise_id)
    if request.method == "POST":
        data, errors = _parse_exercise_form()
        db = get_db()
        if not errors and _duplicate_exercise(db, data["name"], exercise_id):
            errors.append(f"You already have an exercise named \"{data['name']}\".")
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "library/exercise_form.html",
                **_exercise_form_context(data, editing=True, exercise_id=exercise_id),
            ), 400

        db.execute(
            "UPDATE library_exercises SET name = ?, muscles = ?, label = ?, notes = ? "
            "WHERE id = ? AND user_id = ?",
            (
                data["name"],
                ",".join(data["muscles"]),
                data["label"],
                data["notes"],
                exercise_id,
                g.user["id"],
            ),
        )
        db.commit()
        flash("Exercise updated.", "success")
        return redirect(url_for("library.index", tab="exercises"))

    data = {
        "name": exercise["name"],
        "label": exercise["label"] or "",
        "notes": exercise["notes"] or "",
        "muscles": [m for m in (exercise["muscles"] or "").split(",") if m],
    }
    return render_template(
        "library/exercise_form.html",
        **_exercise_form_context(data, editing=True, exercise_id=exercise_id),
    )


@bp.route("/exercises/<int:exercise_id>/delete", methods=("POST",))
@login_required
def exercise_delete(exercise_id):
    _get_exercise(exercise_id)
    db = get_db()
    cursor = db.execute(
        "DELETE FROM library_exercises WHERE id = ? AND user_id = ?",
        (exercise_id, g.user["id"]),
    )
    db.commit()
    flash(
        "Exercise deleted." if cursor.rowcount else "Exercise not found.",
        "info" if cursor.rowcount else "warning",
    )
    return redirect(url_for("library.index", tab="exercises"))


# --------------------------------------------------------------------------- #
# mini-circuits
# --------------------------------------------------------------------------- #
def _parse_circuit_form():
    errors = []
    data = {
        "name": request.form.get("name", "").strip(),
        "notes": request.form.get("notes", "").strip(),
        "rounds": _parse_num(
            request.form.get("rounds"), to_int, "Rounds", errors, minimum=1, maximum=100
        )
        or 3,
        "rest_sec": _parse_num(
            request.form.get("rest_sec"), to_int, "Rest", errors, minimum=0, maximum=3600
        )
        or 0,
        "members": [],
    }
    if not data["name"]:
        errors.append("Circuit name is required.")

    db = get_db()
    valid = {
        row["id"]
        for row in db.execute(
            "SELECT id FROM library_exercises WHERE user_id = ?", (g.user["id"],)
        ).fetchall()
    }
    seen = set()
    for raw in request.form.getlist("member_id"):
        if not raw.strip():
            continue
        try:
            member_id = int(raw)
        except ValueError:
            errors.append("Invalid exercise in the circuit.")
            continue
        if member_id not in valid:
            errors.append("An exercise in this circuit is no longer in your library.")
            continue
        if member_id in seen:
            errors.append("The same exercise appears twice in this circuit.")
            continue
        seen.add(member_id)
        data["members"].append(member_id)

    if len(data["members"]) < 2:
        errors.append("A mini-circuit needs at least 2 exercises.")
    return data, errors


def _circuit_form_context(data, editing, circuit_id=None):
    db = get_db()
    options = [
        {"id": row["id"], "name": row["name"]}
        for row in db.execute(
            "SELECT id, name FROM library_exercises WHERE user_id = ? ORDER BY position, id",
            (g.user["id"],),
        ).fetchall()
    ]
    names = {row["id"]: row["name"] for row in options}
    members = [{"id": mid, "name": names.get(mid, "?")} for mid in data["members"]]
    return {
        "circuit": data,
        "options": options,
        "members_json": members,
        "editing": editing,
        "circuit_id": circuit_id,
    }


@bp.route("/circuits/new", methods=("GET", "POST"))
@login_required
def circuit_new():
    if request.method == "POST":
        data, errors = _parse_circuit_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "library/circuit_form.html", **_circuit_form_context(data, editing=False)
            ), 400

        db = get_db()
        cursor = db.execute(
            "INSERT INTO library_circuits (user_id, position, name, rounds, rest_sec, notes) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                g.user["id"],
                _next_position(db, "library_circuits", g.user["id"]),
                data["name"],
                data["rounds"],
                data["rest_sec"],
                data["notes"],
            ),
        )
        for position, member_id in enumerate(data["members"]):
            db.execute(
                "INSERT INTO library_circuit_members (circuit_id, exercise_id, position) "
                "VALUES (?, ?, ?)",
                (cursor.lastrowid, member_id, position),
            )
        db.commit()
        flash("Mini-circuit added to your library.", "success")
        return redirect(url_for("library.index", tab="exercises"))

    return render_template(
        "library/circuit_form.html",
        **_circuit_form_context(
            {"name": "", "rounds": 3, "rest_sec": 60, "notes": "", "members": []},
            editing=False,
        ),
    )


@bp.route("/circuits/<int:circuit_id>/edit", methods=("GET", "POST"))
@login_required
def circuit_edit(circuit_id):
    circuit = _get_circuit(circuit_id)
    if request.method == "POST":
        data, errors = _parse_circuit_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "library/circuit_form.html",
                **_circuit_form_context(data, editing=True, circuit_id=circuit_id),
            ), 400

        db = get_db()
        db.execute(
            "UPDATE library_circuits SET name = ?, rounds = ?, rest_sec = ?, notes = ? "
            "WHERE id = ? AND user_id = ?",
            (data["name"], data["rounds"], data["rest_sec"], data["notes"],
             circuit_id, g.user["id"]),
        )
        db.execute("DELETE FROM library_circuit_members WHERE circuit_id = ?", (circuit_id,))
        for position, member_id in enumerate(data["members"]):
            db.execute(
                "INSERT INTO library_circuit_members (circuit_id, exercise_id, position) "
                "VALUES (?, ?, ?)",
                (circuit_id, member_id, position),
            )
        db.commit()
        flash("Mini-circuit updated.", "success")
        return redirect(url_for("library.index", tab="exercises"))

    data = {
        "name": circuit["name"],
        "rounds": circuit["rounds"],
        "rest_sec": circuit["rest_sec"],
        "notes": circuit["notes"] or "",
        "members": [row["id"] for row in _circuit_members(get_db(), circuit_id)],
    }
    return render_template(
        "library/circuit_form.html",
        **_circuit_form_context(data, editing=True, circuit_id=circuit_id),
    )


@bp.route("/circuits/<int:circuit_id>/delete", methods=("POST",))
@login_required
def circuit_delete(circuit_id):
    _get_circuit(circuit_id)
    db = get_db()
    cursor = db.execute(
        "DELETE FROM library_circuits WHERE id = ? AND user_id = ?",
        (circuit_id, g.user["id"]),
    )
    db.commit()
    flash(
        "Mini-circuit deleted." if cursor.rowcount else "Mini-circuit not found.",
        "info" if cursor.rowcount else "warning",
    )
    return redirect(url_for("library.index", tab="exercises"))


# --------------------------------------------------------------------------- #
# modules
# --------------------------------------------------------------------------- #
def _parse_module_form(db):
    data = {
        "name": request.form.get("name", "").strip(),
        "notes": request.form.get("notes", "").strip(),
        "items": [],
    }
    errors = []
    if not data["name"]:
        errors.append("Module name is required.")

    exercises = {
        row["id"]
        for row in db.execute(
            "SELECT id FROM library_exercises WHERE user_id = ?", (g.user["id"],)
        ).fetchall()
    }
    circuits = {
        row["id"]
        for row in db.execute(
            "SELECT id FROM library_circuits WHERE user_id = ?", (g.user["id"],)
        ).fetchall()
    }

    types = request.form.getlist("item_type")
    ids = request.form.getlist("item_id")
    for i in range(max(len(types), len(ids))):
        kind = types[i] if i < len(types) else ""
        raw = ids[i] if i < len(ids) else ""
        if not kind and not raw.strip():
            continue
        if kind not in ("exercise", "circuit") or not raw.strip():
            errors.append("That library item could not be read. Reload the page.")
            continue
        try:
            item_id = int(raw)
        except ValueError:
            errors.append("That library item could not be read. Reload the page.")
            continue
        valid = exercises if kind == "exercise" else circuits
        if item_id not in valid:
            errors.append("That library item is no longer in your library.")
            continue
        data["items"].append((kind, item_id))
    return data, errors


def _save_module(db, data, module_id=None):
    if module_id is None:
        module_id = db.execute(
        "INSERT INTO workout_modules (user_id, position, name, notes) "
        "VALUES (?, ?, ?, ?)",
            (g.user["id"], _next_position(db, "workout_modules", g.user["id"]),
             data["name"], data["notes"]),
        ).lastrowid
    else:
        db.execute(
            "UPDATE workout_modules SET name = ?, notes = ? WHERE id = ? AND user_id = ?",
            (data["name"], data["notes"], module_id, g.user["id"]),
        )

    db.execute("DELETE FROM module_items WHERE module_id = ?", (module_id,))
    for position, (kind, item_id) in enumerate(data["items"]):
        db.execute(
            "INSERT INTO module_items (module_id, position, exercise_id, circuit_id) "
            "VALUES (?, ?, ?, ?)",
            (module_id, position, item_id if kind == "exercise" else None,
             item_id if kind == "circuit" else None),
        )
    _sync_module_days(db, module_id)
    db.commit()
    return module_id


def _module_form_context(db, data, editing, module_id=None):
    exercises = [
        {"id": row["id"], "name": row["name"]}
        for row in db.execute(
            "SELECT id, name FROM library_exercises WHERE user_id = ? ORDER BY position, id",
            (g.user["id"],),
        ).fetchall()
    ]
    circuits = [
        {"id": row["id"], "name": row["name"]}
        for row in db.execute(
            "SELECT id, name FROM library_circuits WHERE user_id = ? ORDER BY position, id",
            (g.user["id"],),
        ).fetchall()
    ]
    # Exercise and circuit ids live in separate sequences, so each kind needs
    # its own name lookup: a single merged map would show the wrong name
    # whenever an exercise and a circuit share a numeric id.
    exercise_names = {row["id"]: row["name"] for row in exercises}
    circuit_names = {row["id"]: row["name"] for row in circuits}
    items = [
        {
            "type": kind,
            "id": item_id,
            "name": (exercise_names if kind == "exercise" else circuit_names).get(item_id, "?"),
        }
        for kind, item_id in data["items"]
    ]
    return {
        "module": data,
        "exercise_options": exercises,
        "circuit_options": circuits,
        "items_json": items,
        "editing": editing,
        "module_id": module_id,
    }


@bp.route("/modules/new", methods=("GET", "POST"))
@login_required
def module_new():
    db = get_db()
    if request.method == "POST":
        data, errors = _parse_module_form(db)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "library/module_form.html",
                **_module_form_context(db, data, editing=False),
            ), 400
        _save_module(db, data)
        flash("Module added to your library.", "success")
        return redirect(url_for("library.index", tab="modules"))

    return render_template(
        "library/module_form.html",
        **_module_form_context(db, {"name": "", "notes": "", "items": []}, editing=False),
    )


@bp.route("/modules/<int:module_id>/edit", methods=("GET", "POST"))
@login_required
def module_edit(module_id):
    module = _get_module(module_id)
    db = get_db()
    if request.method == "POST":
        data, errors = _parse_module_form(db)
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "library/module_form.html",
                **_module_form_context(db, data, editing=True, module_id=module_id),
            ), 400
        _save_module(db, data, module_id=module_id)
        flash("Module updated.", "success")
        return redirect(url_for("library.index", tab="modules"))

    data = {
        "name": module["name"],
        "notes": module["notes"] or "",
        "items": [
            (
                "exercise" if row["exercise_id"] is not None else "circuit",
                row["exercise_id"] if row["exercise_id"] is not None else row["circuit_id"],
            )
            for row in db.execute(
                "SELECT * FROM module_items WHERE module_id = ? ORDER BY position, id",
                (module_id,),
            ).fetchall()
        ],
    }
    return render_template(
        "library/module_form.html",
        **_module_form_context(db, data, editing=True, module_id=module_id),
    )


@bp.route("/modules/<int:module_id>/delete", methods=("POST",))
@login_required
def module_delete(module_id):
    _get_module(module_id)
    db = get_db()
    cursor = db.execute(
        "DELETE FROM workout_modules WHERE id = ? AND user_id = ?",
        (module_id, g.user["id"]),
    )
    db.commit()
    flash(
        "Module deleted from the library." if cursor.rowcount else "Module not found.",
        "info" if cursor.rowcount else "warning",
    )
    return redirect(url_for("library.index", tab="modules"))
