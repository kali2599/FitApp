from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from ..auth import login_required
from ..db import get_db
from ..food_library import load_foods
from ..utils import to_float

bp = Blueprint("diets", __name__, url_prefix="/diets")

TARGET_FIELDS = [
    ("calories", "Calories", 0, 10000),
    ("protein_g", "Protein", 0, 1000),
    ("carbs_g", "Carbohydrates", 0, 2000),
    ("fat_g", "Fat", 0, 500),
]
def _macro_calories(protein, carbs, fat):
    return round(4 * protein + 4 * carbs + 9 * fat, 1)


def _calorie_mismatch(calories, protein, carbs, fat):
    """Return the macro-derived kcal value when the entered target disagrees."""
    if calories is None or any(value is None for value in (protein, carbs, fat)):
        return None
    derived = _macro_calories(protein, carbs, fat)
    # Allow for label rounding while still catching material discrepancies.
    tolerance = max(10, derived * 0.05)
    return derived if abs(calories - derived) > tolerance else None


def _load_meals(db, plan_id):
    meals = db.execute(
        "SELECT * FROM diet_plan_meals WHERE diet_plan_id = ? ORDER BY position, id",
        (plan_id,),
    ).fetchall()
    result = []
    totals = {"protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "calories": 0.0}
    for meal in meals:
        foods = [dict(row) for row in db.execute(
            "SELECT * FROM diet_plan_foods WHERE meal_id = ? ORDER BY position, id",
            (meal["id"],),
        ).fetchall()]
        meal_totals = {"protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0, "calories": 0.0}
        for food in foods:
            if food["calories"] is None:
                food["calories"] = _macro_calories(
                    food["protein_g"], food["carbs_g"], food["fat_g"]
                )
            for field in ("protein_g", "carbs_g", "fat_g"):
                meal_totals[field] += food[field]
            meal_totals["calories"] += food["calories"]
        meal_totals = {key: round(value, 1) for key, value in meal_totals.items()}
        for key, value in meal_totals.items():
            totals[key] += value
        result.append({"meal": dict(meal), "foods": foods, "totals": meal_totals})
    totals = {key: round(value, 1) for key, value in totals.items()}
    return result, totals


def _parse_form():
    data = {
        "name": request.form.get("name", "").strip(),
        "guidance": request.form.get("guidance", "").strip(),
        "calories": None,
        "protein_g": None,
        "carbs_g": None,
        "fat_g": None,
        "meals": [],
    }
    errors = []
    if not data["name"]:
        errors.append("Diet name is required.")
    for field, label, minimum, maximum in TARGET_FIELDS:
        try:
            data[field] = to_float(request.form.get(field), minimum=minimum, maximum=maximum)
        except ValueError as exc:
            errors.append(f"{label} {exc}.")

    meal_names = request.form.getlist("meal_name")
    meal_foods = [[] for _ in meal_names]
    food_meal_ids = request.form.getlist("food_meal")
    food_names = request.form.getlist("food_name")
    food_quantities = request.form.getlist("food_quantity")
    catalog = load_foods()
    catalog_by_name = {item["food"]: item for item in catalog}
    row_count = max(len(food_meal_ids), len(food_names), len(food_quantities))
    for index in range(row_count):
        def value_at(values):
            return values[index] if index < len(values) else ""

        raw_meal = value_at(food_meal_ids)
        try:
            meal_index = int(raw_meal)
        except (TypeError, ValueError):
            errors.append("A food could not be matched to its meal. Reload the form and try again.")
            continue
        if meal_index < 0 or meal_index >= len(meal_names):
            errors.append("A food refers to an invalid meal.")
            continue
        name = value_at(food_names).strip()
        catalog_food = catalog_by_name.get(name)
        if catalog_food is None:
            errors.append("Choose a food from the food library.")
        try:
            quantity_g = to_float(value_at(food_quantities), minimum=0.1, maximum=10000)
        except ValueError as exc:
            errors.append(f"Quantity for {name or 'the selected food'} {exc}.")
            quantity_g = None
        if quantity_g is None:
            errors.append(f"Enter the quantity in grams for {name or 'the selected food'}.")
        scale = (quantity_g or 0) / 100
        food = {
            "name": name,
            "quantity_g": quantity_g,
            "calories": round(catalog_food["calories"] * scale, 1) if catalog_food else None,
            "protein_g": round(catalog_food["protein"] * scale, 2) if catalog_food else None,
            "carbs_g": round(catalog_food["carbs"] * scale, 2) if catalog_food else None,
            "fat_g": round(catalog_food["fat"] * scale, 2) if catalog_food else None,
        }
        meal_foods[meal_index].append(food)

    for index, (name, foods) in enumerate(zip(meal_names, meal_foods)):
        name = name.strip()
        if not name and not foods:
            continue
        if not name:
            errors.append("Every meal needs a name.")
        if not foods:
            errors.append(f"Add at least one food to {name or f'meal {index + 1}'}, or remove the empty meal.")
        data["meals"].append({"name": name, "foods": foods})

    # Prefer the explicit daily targets when all three macros are supplied;
    # otherwise validate the calorie target against the complete food table.
    macro_source = None
    if all(data[field] is not None for field in ("protein_g", "carbs_g", "fat_g")):
        macro_source = (data["protein_g"], data["carbs_g"], data["fat_g"])
    elif data["meals"] and all(
        food["calories"] is not None
        for meal in data["meals"]
        for food in meal["foods"]
    ):
        meal_calories = sum(food["calories"] for meal in data["meals"] for food in meal["foods"])
        mismatch = (
            meal_calories
            if data["calories"] is not None
            and abs(data["calories"] - meal_calories) > max(10, meal_calories * 0.05)
            else None
        )
        if mismatch is not None:
            errors.append(
                f"Calories ({data['calories']:g} kcal) differ from the selected foods "
                f"({mismatch:g} kcal). The difference must be within 5% or 10 kcal."
            )
    elif macro_source:
        mismatch = _calorie_mismatch(data["calories"], *macro_source)
        if mismatch is not None:
            errors.append(
                f"Calories ({data['calories']:g} kcal) do not match the macro estimate "
                f"({mismatch:g} kcal from 4 kcal/g protein, 4 kcal/g carbohydrates, "
                "and 9 kcal/g fat). The difference must be within 5% or 10 kcal."
            )
    return data, errors


def _get_plan(db, plan_id):
    plan = db.execute(
        "SELECT * FROM diet_plans WHERE id = ? AND user_id = ?",
        (plan_id, g.user["id"]),
    ).fetchone()
    if plan is None:
        abort(404)
    return plan


def _form_context(plan, editing, plan_id=None):
    return {
        "plan": plan,
        "editing": editing,
        "plan_id": plan_id,
        "food_catalog": load_foods(),
    }


def _save_meals(db, plan_id, meals):
    db.execute("DELETE FROM diet_plan_meals WHERE diet_plan_id = ?", (plan_id,))
    for meal_position, meal in enumerate(meals):
        cursor = db.execute(
            "INSERT INTO diet_plan_meals (diet_plan_id, position, name) VALUES (?, ?, ?)",
            (plan_id, meal_position, meal["name"]),
        )
        for food_position, food in enumerate(meal["foods"]):
            db.execute(
                """INSERT INTO diet_plan_foods
                   (meal_id, position, name, quantity_g, calories, protein_g, carbs_g, fat_g)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (cursor.lastrowid, food_position, food["name"], food["quantity_g"],
                 food["calories"],
                 food["protein_g"], food["carbs_g"], food["fat_g"]),
            )


@bp.route("/")
@login_required
def index():
    db = get_db()
    plans = db.execute(
        "SELECT * FROM diet_plans WHERE user_id = ? ORDER BY created_at DESC, id DESC",
        (g.user["id"],),
    ).fetchall()
    details = {}
    for plan in plans:
        details[plan["id"]] = _load_meals(db, plan["id"])
    return render_template("diets/list.html", plans=plans, plan_details=details)


@bp.route("/new", methods=("GET", "POST"))
@login_required
def new():
    db = get_db()
    if request.method == "POST":
        data, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template("diets/form.html", **_form_context(data, editing=False)), 400

        cursor = db.execute(
            """INSERT INTO diet_plans (user_id, name, guidance, calories, protein_g, carbs_g, fat_g)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (g.user["id"], data["name"], data["guidance"], data["calories"],
             data["protein_g"], data["carbs_g"], data["fat_g"]),
        )
        _save_meals(db, cursor.lastrowid, data["meals"])
        db.commit()
        flash("Diet plan added.", "success")
        return redirect(url_for("diets.index"))

    return render_template(
        "diets/form.html",
        **_form_context({"name": "", "guidance": "", "calories": "", "protein_g": "",
                         "carbs_g": "", "fat_g": "", "meals": []}, editing=False),
    )


@bp.route("/<int:plan_id>/edit", methods=("GET", "POST"))
@login_required
def edit(plan_id):
    db = get_db()
    plan = _get_plan(db, plan_id)
    if request.method == "POST":
        data, errors = _parse_form()
        if errors:
            for error in errors:
                flash(error, "danger")
            return render_template(
                "diets/form.html", **_form_context(data, editing=True, plan_id=plan_id)
            ), 400

        db.execute(
            """UPDATE diet_plans SET name = ?, guidance = ?, calories = ?, protein_g = ?,
                                      carbs_g = ?, fat_g = ?
               WHERE id = ? AND user_id = ?""",
            (data["name"], data["guidance"], data["calories"], data["protein_g"],
             data["carbs_g"], data["fat_g"], plan_id, g.user["id"]),
        )
        _save_meals(db, plan_id, data["meals"])
        db.commit()
        flash("Diet plan updated.", "success")
        return redirect(url_for("diets.index"))

    data = dict(plan)
    data["meals"], _ = _load_meals(db, plan_id)
    return render_template(
        "diets/form.html", **_form_context(data, editing=True, plan_id=plan_id)
    )


@bp.route("/<int:plan_id>/delete", methods=("POST",))
@login_required
def delete(plan_id):
    db = get_db()
    _get_plan(db, plan_id)
    db.execute("DELETE FROM diet_plans WHERE id = ? AND user_id = ?", (plan_id, g.user["id"]))
    db.commit()
    flash("Diet plan deleted.", "info")
    return redirect(url_for("diets.index"))
