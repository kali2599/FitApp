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

bp = Blueprint("stats", __name__, url_prefix="/stats")

FIELDS = [
    ("weight_kg", "Weight", 20, 400),
    ("body_fat_pct", "Body fat", 1, 80),
    ("chest_cm", "Chest", 30, 250),
    ("waist_cm", "Waist", 30, 250),
    ("hip_cm", "Hip", 30, 250),
    ("arm_cm", "Arm", 10, 100),
]


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
    return render_template("stats/list.html", rows=rows, fields=FIELDS)


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
