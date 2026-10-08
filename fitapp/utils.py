import datetime as _dt


def to_float(value, minimum=None, maximum=None):
    """Return a float from form input, or None when blank."""
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    try:
        number = float(value)
    except ValueError:
        raise ValueError("must be a number")
    if minimum is not None and number < minimum:
        raise ValueError(f"must be at least {minimum:g}")
    if maximum is not None and number > maximum:
        raise ValueError(f"must be at most {maximum:g}")
    return number


def to_int(value, minimum=None, maximum=None):
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    try:
        number = int(value)
    except ValueError:
        raise ValueError("must be a whole number")
    if minimum is not None and number < minimum:
        raise ValueError(f"must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"must be at most {maximum}")
    return number


def to_date(value):
    """Parse YYYY-MM-DD input into an ISO date string, or None when blank."""
    if value is None:
        return None
    value = str(value).strip()
    if value == "":
        return None
    try:
        return _dt.date.fromisoformat(value).isoformat()
    except ValueError:
        raise ValueError("must be a valid date (YYYY-MM-DD)")


def goal_progress(goal, current_value):
    """Return completion percentage (0-100+) for a goal given the current value."""
    start = goal["start_value"]
    target = goal["target_value"]
    if current_value is None or target is None:
        return None
    if start is None or start == target:
        reached = current_value >= target if target >= 0 else current_value <= target
        return 100.0 if reached else 0.0
    ratio = (current_value - start) / (target - start)
    return round(max(0.0, min(1.5, ratio * 100)), 1)
