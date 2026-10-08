"""Compute the current value used to evaluate a goal's progress."""

BODY_FIELDS = [
    ("weight", "weight_kg", "latest weight"),
    ("body fat", "body_fat_pct", "latest body fat %"),
    ("fat", "body_fat_pct", "latest body fat %"),
    ("waist", "waist_cm", "latest waist"),
    ("chest", "chest_cm", "latest chest"),
    ("hip", "hip_cm", "latest hip"),
    ("arm", "arm_cm", "latest arm"),
    ("height", None, None),
]

AGGREGATES = [
    (("kg", "kilo"), "weight_kg", "MAX"),
    (("lb", "pound"), "weight_kg", "MAX"),
    (("rep",), "reps", "MAX"),
    (("set",), "sets", "MAX"),
    (("min", "time"), "duration_min", "MAX"),
]


def current_value(db, user_id, goal):
    """Return (value, source_label) for a goal, or (None, None)."""
    category = (goal["category"] or "").lower()
    unit = (goal["unit"] or "").lower()

    for keyword, column, label in BODY_FIELDS:
        if keyword in category and column:
            row = db.execute(
                f"SELECT {column} AS value FROM body_stats "
                f"WHERE user_id = ? AND {column} IS NOT NULL "
                "ORDER BY stat_date DESC, id DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            return (row["value"] if row else None), label

    keywords = [word for word in category.split() if len(word) > 2]
    if not keywords:
        return None, None

    column = "weight_kg"
    aggregate = "MAX"
    for unit_keys, candidate_column, candidate_agg in AGGREGATES:
        if any(key in unit for key in unit_keys):
            column = candidate_column
            aggregate = candidate_agg
            break

    matches = " OR ".join("LOWER(e.name) LIKE ?" for _ in keywords)
    params = [f"%{word}%" for word in keywords]
    row = db.execute(
        f"SELECT {aggregate}(e.{column}) AS value FROM exercises e "
        "JOIN workouts w ON w.id = e.workout_id "
        f"WHERE w.user_id = ? AND ({matches}) AND e.{column} IS NOT NULL",
        [user_id, *params],
    ).fetchone()
    if row and row["value"] is not None:
        label = {
            "weight_kg": "best logged weight",
            "reps": "best reps",
            "sets": "best sets",
            "duration_min": "longest session",
        }.get(column, "best logged value")
        return row["value"], label
    return None, None
