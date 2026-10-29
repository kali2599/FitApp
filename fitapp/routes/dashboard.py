import datetime as dt

from flask import Blueprint, g, render_template

from .. import progress
from ..auth import login_required
from ..db import get_db
from ..insights import compute
from .goals import _cardio_as_goal, _cardio_current, _cardio_percent

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    db = get_db()
    uid = g.user["id"]
    today = dt.date.today()

    diet_plan_count = db.execute(
        "SELECT COUNT(*) FROM diet_plans WHERE user_id = ?", (uid,)
    ).fetchone()[0]

    weight_rows = db.execute(
        """SELECT stat_date, weight_kg, body_fat_pct FROM body_stats
           WHERE user_id = ? ORDER BY stat_date, id""",
        (uid,),
    ).fetchall()
    latest = weight_rows[-1] if weight_rows else None
    previous = weight_rows[-2] if len(weight_rows) > 1 else None

    lifestyle = db.execute(
        "SELECT * FROM user_lifestyle WHERE user_id = ?", (uid,)
    ).fetchone()
    latest_stat = db.execute(
        """SELECT * FROM body_stats WHERE user_id = ?
           ORDER BY stat_date DESC, id DESC LIMIT 1""",
        (uid,),
    ).fetchone()
    insight = compute(g.user, latest_stat, lifestyle)

    def delta(current_row, previous_row, key):
        if not current_row or not previous_row or current_row[key] is None or previous_row[key] is None:
            return None
        return round(current_row[key] - previous_row[key], 1)

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
                "goal": dict(goal, is_cardio=False),
                "current": current,
                "source": source,
                "percent": progress.percent(db, goal, current),
            }
        )
    cardio_goals = db.execute(
        """SELECT * FROM cardio_goals WHERE user_id = ? AND status = 'active'
           ORDER BY (target_date IS NULL), target_date""",
        (uid,),
    ).fetchall()
    for row in cardio_goals:
        goal = _cardio_as_goal(row)
        current, source = _cardio_current(db, goal)
        goal_cards.append(
            {
                "goal": goal,
                "current": current,
                "source": source,
                "percent": _cardio_percent(goal, current),
            }
        )

    diet_plans = db.execute(
        """SELECT * FROM diet_plans WHERE user_id = ?
           ORDER BY created_at DESC, id DESC LIMIT 3""",
        (uid,),
    ).fetchall()

    charts = {
        "trend": {
            "labels": trend_labels,
            "weight": trend_weight,
            "fat": trend_fat,
        },
    }

    return render_template(
        "dashboard.html",
        today=today,
        diet_plan_count=diet_plan_count,
        latest=latest,
        weight_delta=delta(latest, previous, "weight_kg"),
        fat_delta=delta(latest, previous, "body_fat_pct"),
        insight=insight,
        goal_cards=goal_cards,
        diet_plans=diet_plans,
        charts=charts,
    )
