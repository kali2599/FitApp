"""Compute the current value and completion percent used for a goal's progress."""

from .utils import goal_progress


def _to_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _fallback(goal):
    start = goal["start_value"]
    if start is None or not str(start).strip():
        return (None, None)
    value = _to_number(start)
    if value is not None:
        return (value, "start baseline")
    return (None, None)


def current_value(db, user_id, goal):
    """Return (value, source_label) for a goal, or (None, None).

    Numeric goals return a float.
    """
    goal_type = goal["goal_type"]
    unit = goal["unit"] or ""

    manual = db.execute(
        "SELECT value FROM goal_logs WHERE goal_id = ? AND user_id = ? "
        "ORDER BY logged_date DESC, id DESC LIMIT 1",
        (goal["id"], user_id),
    ).fetchone()
    if manual is not None and manual["value"] is not None:
        value = _to_number(manual["value"])
        if value is not None:
            return (value, "logged progress")

    if goal_type == "body":
        column, label = (
            ("body_fat_pct", "latest body fat %") if unit == "%" else ("weight_kg", "latest weight")
        )
        row = db.execute(
            f"SELECT {column} AS value FROM body_stats "
            f"WHERE user_id = ? AND {column} IS NOT NULL "
            "ORDER BY stat_date DESC, id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if row:
            return (_to_number(row["value"]), label)

    return _fallback(goal)


def percent(db, goal, current):
    """Completion percent (0-150) for a goal given its current value."""
    if current is None:
        return None
    return goal_progress(goal, current)