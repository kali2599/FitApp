import datetime as dt

from flask import Blueprint, g, render_template

from .. import progress
from ..auth import login_required
from ..db import get_db
from ..utils import goal_progress

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    db = get_db()
    uid = g.user["id"]
    today = dt.date.today()

    today_totals = db.execute(
        """SELECT COALESCE(SUM(calories), 0) AS calories,
                  COALESCE(SUM(protein_g), 0) AS protein,
                  COALESCE(SUM(carbs_g), 0) AS carbs,
                  COALESCE(SUM(fat_g), 0) AS fat,
                  COUNT(*) AS meals
           FROM diets WHERE user_id = ? AND diet_date = ?""",
        (uid, today.isoformat()),
    ).fetchone()

    week_start = (today - dt.timedelta(days=today.weekday())).isoformat()
    week = db.execute(
        """SELECT COUNT(*) AS sessions,
                  COALESCE(SUM(duration_min), 0) AS minutes,
                  COALESCE(SUM(calories), 0) AS burned
           FROM workout_sessions WHERE user_id = ? AND performed_date >= ?""",
        (uid, week_start),
    ).fetchone()

    weight_rows = db.execute(
        """SELECT stat_date, weight_kg, body_fat_pct FROM body_stats
           WHERE user_id = ? ORDER BY stat_date, id""",
        (uid,),
    ).fetchall()
    latest = weight_rows[-1] if weight_rows else None
    previous = weight_rows[-2] if len(weight_rows) > 1 else None

    def delta(current_row, previous_row, key):
        if not current_row or not previous_row or current_row[key] is None or previous_row[key] is None:
            return None
        return round(current_row[key] - previous_row[key], 1)

    workout_rows = db.execute(
        """SELECT performed_date AS workout_date, duration_min FROM workout_sessions
           WHERE user_id = ? ORDER BY performed_date""",
        (uid,),
    ).fetchall()
    diet_rows = db.execute(
        """SELECT diet_date, calories, protein_g, carbs_g, fat_g FROM diets
           WHERE user_id = ? ORDER BY diet_date""",
        (uid,),
    ).fetchall()

    weekly = {}
    for row in workout_rows:
        date = dt.date.fromisoformat(row["workout_date"])
        start = date - dt.timedelta(days=date.weekday())
        bucket = weekly.setdefault(start.isoformat(), {"sessions": 0, "minutes": 0})
        bucket["sessions"] += 1
        bucket["minutes"] += row["duration_min"] or 0
    weeks = [(today - dt.timedelta(days=today.weekday() - offset * 7)).isoformat() for offset in range(7, -1, -1)]
    weekly_labels = [dt.date.fromisoformat(w).strftime("%d %b") for w in weeks]
    weekly_minutes = [weekly.get(w, {}).get("minutes", 0) for w in weeks]
    weekly_sessions = [weekly.get(w, {}).get("sessions", 0) for w in weeks]

    daily = {}
    for row in diet_rows:
        entry = daily.setdefault(
            row["diet_date"], {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}
        )
        entry["calories"] += row["calories"] or 0
        entry["protein"] += row["protein_g"] or 0
        entry["carbs"] += row["carbs_g"] or 0
        entry["fat"] += row["fat_g"] or 0
    days = [(today - dt.timedelta(days=offset)).isoformat() for offset in range(13, -1, -1)]
    intake_labels = [dt.date.fromisoformat(d).strftime("%d %b") for d in days]
    intake = [daily.get(d, {"calories": 0, "protein": 0, "carbs": 0, "fat": 0}) for d in days]

    trend_labels = [row["stat_date"] for row in weight_rows[-30:]]
    trend_weight = [row["weight_kg"] for row in weight_rows[-30:]]
    trend_fat = [row["body_fat_pct"] for row in weight_rows[-30:]]

    goals = db.execute(
        """SELECT * FROM goals WHERE user_id = ? AND status = 'active'
           ORDER BY (target_date IS NULL), target_date""",
        (uid,),
    ).fetchall()
    goal_cards = []
    for goal in goals:
        current, source = progress.current_value(db, uid, goal)
        goal_cards.append(
            {
                "goal": goal,
                "current": current,
                "source": source,
                "percent": goal_progress(goal, current),
            }
        )

    recent_workouts = db.execute(
        """SELECT s.*, d.name AS day_name, w.name AS workout_name, w.workout_type
           FROM workout_sessions s
           LEFT JOIN workout_days d ON d.id = s.workout_day_id
           LEFT JOIN workouts w ON w.id = d.workout_id
           WHERE s.user_id = ?
           ORDER BY s.performed_date DESC, s.id DESC LIMIT 5""",
        (uid,),
    ).fetchall()
    recent_meals = db.execute(
        """SELECT * FROM diets WHERE user_id = ?
           ORDER BY diet_date DESC, id DESC LIMIT 5""",
        (uid,),
    ).fetchall()

    charts = {
        "trend": {
            "labels": trend_labels,
            "weight": trend_weight,
            "fat": trend_fat,
        },
        "weekly": {"labels": weekly_labels, "minutes": weekly_minutes, "sessions": weekly_sessions},
        "intake": {
            "labels": intake_labels,
            "calories": [round(item["calories"]) for item in intake],
            "protein": [round(item["protein"]) for item in intake],
            "carbs": [round(item["carbs"]) for item in intake],
            "fat": [round(item["fat"]) for item in intake],
        },
    }

    return render_template(
        "dashboard.html",
        today=today,
        today_totals=today_totals,
        week=week,
        week_start=week_start,
        latest=latest,
        weight_delta=delta(latest, previous, "weight_kg"),
        fat_delta=delta(latest, previous, "body_fat_pct"),
        goal_cards=goal_cards,
        recent_workouts=recent_workouts,
        recent_meals=recent_meals,
        charts=charts,
    )
