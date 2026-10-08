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
from ..utils import to_date, to_float

bp = Blueprint("diets", __name__, url_prefix="/diets")

MEAL_TYPES = ["Breakfast", "Lunch", "Dinner", "Snack", "Drink", "Other"]

MACRO_FIELDS = [
    ("calories", "Calories", 0, 10000),
    ("protein_g", "Protein", 0, 1000),
    ("carbs_g", "Carbs", 0, 2000),
    ("fat_g", "Fat", 0, 500),
]


def _parse_form():
    data = {
        "diet_date": None,
        "meal_type": request.form.get("meal_type", "").strip(),
        "description": request.form.get("description", "").strip(),
        "notes": request.form.get("notes", "").strip(),
    }
    errors = []
    try:
        data["diet_date"] = to_date(request.form.get("diet_date"))
    except ValueError as exc:
        errors.append(f"Date {exc}.")
    if data["diet_date"] is None:
        errors.append("Date is required.")
    if data["meal_type"] not in MEAL_TYPES:
        errors.append("Choose a valid meal type.")
    if not data["description"]:
        errors.append("Description is required.")

    for field, label, minimum, maximum in MACRO_FIELDS:
        try:
            data[field] = to_float(request.form.get(field), minimum=minimum, maximum=maximum)
        except ValueError as exc:
            errors.append(f"{label} {exc}.")
            data[field] = None
    return data, errors


@bp.route("/")
@login_required
def index():
    db = get_db()
    entries = db.execute(
        "SELECT * FROM diets WHERE user_id = ? ORDER BY diet_date DESC, id DESC",
        (g.user["id"],),
    ).fetchall()

    totals = db.execute(
        """SELECT COALESCE(SUM(calories), 0) AS calories,
                  COALESCE(SUM(protein_g), 0) AS protein,
                  COALESCE(SUM(carbs_g), 0) AS carbs,
                  COALESCE(SUM(fat_g), 0) AS fat,
                  COUNT(*) AS entries
           FROM diets WHERE user_id = ? AND diet_date = date('now', 'localtime')""",
        (g.user["id"],),
    ).fetchone()

    return render_template(
        "diets/list.html", entries=entries, totals=totals, meal_types=MEAL_TYPES
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
                "diets/form.html",
                entry=data,
                meal_types=MEAL_TYPES,
                editing=False,
            ), 400

        db = get_db()
        db.execute(
            """INSERT INTO diets (user_id, diet_date, meal_type, description,
                                  calories, protein_g, carbs_g, fat_g, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                g.user["id"],
                data["diet_date"],
                data["meal_type"],
                data["description"],
                data["calories"],
                data["protein_g"],
                data["carbs_g"],
                data["fat_g"],
                data["notes"],
            ),
        )
        db.commit()
        flash("Meal entry added.", "success")
        return redirect(url_for("diets.index"))

    return render_template(
        "diets/form.html",
        entry={
            "diet_date": request.args.get("date", ""),
            "meal_type": "",
            "description": "",
            "calories": "",
            "protein_g": "",
            "carbs_g": "",
            "fat_g": "",
            "notes": "",
        },
        meal_types=MEAL_TYPES,
        editing=False,
    )


@bp.route("/<int:entry_id>/edit", methods=("GET", "POST"))
@login_required
def edit(entry_id):
    db = get_db()
    entry = db.execute(
        "SELECT * FROM diets WHERE id = ? AND user_id = ?", (entry_id, g.user["id"])
    ).fetchone()
    if entry is None:
        abort(404)

    if request.method == "POST":
        data, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "diets/form.html",
                entry=data,
                meal_types=MEAL_TYPES,
                editing=True,
                entry_id=entry_id,
            ), 400

        db.execute(
            """UPDATE diets SET diet_date = ?, meal_type = ?, description = ?,
                                 calories = ?, protein_g = ?, carbs_g = ?,
                                 fat_g = ?, notes = ?
               WHERE id = ? AND user_id = ?""",
            (
                data["diet_date"],
                data["meal_type"],
                data["description"],
                data["calories"],
                data["protein_g"],
                data["carbs_g"],
                data["fat_g"],
                data["notes"],
                entry_id,
                g.user["id"],
            ),
        )
        db.commit()
        flash("Meal entry updated.", "success")
        return redirect(url_for("diets.index"))

    return render_template(
        "diets/form.html",
        entry=entry,
        meal_types=MEAL_TYPES,
        editing=True,
        entry_id=entry_id,
    )


@bp.route("/<int:entry_id>/delete", methods=("POST",))
@login_required
def delete(entry_id):
    db = get_db()
    cursor = db.execute(
        "DELETE FROM diets WHERE id = ? AND user_id = ?", (entry_id, g.user["id"])
    )
    db.commit()
    if cursor.rowcount:
        flash("Meal entry deleted.", "info")
    else:
        flash("Entry not found.", "warning")
    return redirect(url_for("diets.index"))
