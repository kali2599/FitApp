"""Compute the current value and completion percent used for a goal's progress."""

import re

from .utils import goal_progress

COLUMN_LABELS = {
    "weight_kg": "best logged weight",
    "reps": "best reps",
    "duration_sec": "longest hold",
}

STOPWORDS = {"a", "an", "the", "to", "in", "on", "at", "of", "for", "and", "or", "up"}

_WORD_SPLIT = re.compile(r"[^0-9a-z]+")


def _words(text):
    return [w for w in _WORD_SPLIT.split(text.lower()) if w]


def _to_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _match_score(tokens, name):
    words = _words(name)
    initials = "".join(w[0] for w in words)
    score = 0
    for token in tokens:
        if token == initials:
            score += 1
        elif any(
            token in w or w.startswith(token) or token.startswith(w) for w in words
        ):
            score += 1
    return score


def _fallback(goal):
    start = goal["start_value"]
    if start is None or not str(start).strip():
        return (None, None)
    value = _to_number(start)
    if value is not None:
        return (value, "start baseline")
    return (None, None)


def _best_match(db, user_id, category, column):
    tokens = [w for w in _words(category) if len(w) > 1 and w not in STOPWORDS]
    if not tokens:
        return None
    rows = db.execute(
        f"SELECT e.name AS name, e.{column} AS value FROM session_entries e "
        "JOIN workout_sessions s ON s.id = e.session_id "
        f"WHERE s.user_id = ? AND e.{column} IS NOT NULL",
        (user_id,),
    ).fetchall()
    best_score = 0
    best_value = None
    for row in rows:
        score = _match_score(tokens, row["name"])
        if score < best_score:
            continue
        value = _to_number(row["value"])
        if score > best_score:
            best_score = score
            best_value = value
        elif value is not None and (best_value is None or value > best_value):
            best_value = value
    if best_score > 0 and best_value is not None:
        return best_value
    return None


def current_value(db, user_id, goal):
    """Return (value, source_label) for a goal, or (None, None).

    Numeric goals return a float.
    """
    goal_type = goal["goal_type"]
    unit = goal["unit"] or ""
    category = (goal["category"] or "").lower()

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

    if goal_type == "strength":
        column = "reps" if unit == "reps" else "weight_kg"
        best = _best_match(db, user_id, category, column)
        if best is not None:
            return (best, COLUMN_LABELS[column])
        return _fallback(goal)

    if goal_type == "skill" and unit == "seconds":
        best = _best_match(db, user_id, category, "duration_sec")
        if best is not None:
            return (best, COLUMN_LABELS["duration_sec"])
        return _fallback(goal)

    return _fallback(goal)


def percent(db, goal, current):
    """Completion percent (0-150) for a goal given its current value."""
    if current is None:
        return None
    return goal_progress(goal, current)