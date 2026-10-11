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
    """Return completion percentage (0-150) for a goal given the current value.

    Decreasing targets (target < start, e.g. losing weight/fat) are measured
    from the start point; increasing targets use a zero-based current/target
    ratio (so an unlogged goal defaults to its start value).
    """
    start = _as_float(goal["start_value"])
    target = _as_float(goal["target_value"])
    if current_value is None or target is None:
        return None
    if start is not None and target < start:
        ratio = (current_value - start) / (target - start)
    else:
        if target <= 0:
            return None
        ratio = current_value / target
    return round(max(0.0, min(150.0, ratio * 100)), 1)


def _as_float(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number
