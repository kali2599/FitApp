"""Body stats and lifestyle profile (Phase 2)."""
import re

from helpers import make_user, scalar


def test_lifestyle_zero_values_are_kept(client, db):
    """Zero is a real answer: it must be stored and shown back, not blanked."""
    make_user(client, "tester")
    r = client.post(
        "/stats/lifestyle",
        data={
            "sessions_per_week": "0",
            "session_duration_min": "45",
            "intensity": "moderate",
            "activity_level": "sedentary",
            "sleep_hours": "7.5",
            "daily_calories": "2200",
            "goal_direction": "maintain",
            "water_cups": "0",
            "stress_level": "low",
        },
    )
    assert r.status_code == 302

    row = db.execute("SELECT sessions_per_week, water_cups FROM user_lifestyle").fetchone()
    assert row["sessions_per_week"] == 0
    assert row["water_cups"] == 0

    body = client.get("/stats/lifestyle").get_data(as_text=True)
    sessions = re.search(r'id="sessions_per_week"[^>]*value="([^"]*)"', body).group(1)
    water = re.search(r'id="water_cups"[^>]*value="([^"]*)"', body).group(1)
    assert sessions == "0"
    assert float(water) == 0.0


def test_lifestyle_blank_fields_stay_blank(client, db):
    """An empty field is still empty; only the zero case changed."""
    make_user(client, "tester")
    client.post("/stats/lifestyle", data={"sessions_per_week": "3", "water_cups": ""})
    row = db.execute("SELECT sessions_per_week, water_cups FROM user_lifestyle").fetchone()
    assert row["sessions_per_week"] == 3
    assert row["water_cups"] is None

    body = client.get("/stats/lifestyle").get_data(as_text=True)
    water = re.search(r'id="water_cups"[^>]*value="([^"]*)"', body).group(1)
    assert water == ""


def test_lifestyle_not_saved_without_a_profile(client, db):
    make_user(client, "tester")
    body = client.get("/stats/lifestyle").get_data(as_text=True)
    assert "Lifestyle profile" in body
    assert scalar(db, "SELECT COUNT(*) FROM user_lifestyle") == 0
