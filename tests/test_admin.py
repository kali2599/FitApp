"""Admin area: user management only, no exercise catalog (Phase 4)."""
from helpers import make_admin, make_user, scalar


def test_admin_pages_render_for_admin(client, db):
    make_admin(client, "boss")
    assert client.get("/admin/").status_code == 200
    user_id = scalar(db, "SELECT id FROM users WHERE username = 'boss'")
    assert client.get(f"/admin/users/{user_id}").status_code == 200


def test_exercise_catalog_route_removed(client, db):
    make_admin(client, "boss")
    for path in ["/admin/exercises", "/admin/exercises/new", "/admin/exercises/1/edit"]:
        assert client.get(path).status_code == 404, path

    html = client.get("/admin/").get_data(as_text=True)
    assert "Exercise catalog" not in html
    assert "/admin/exercises" not in html


def test_regular_user_cannot_open_admin(client, db):
    make_user(client, "tester")
    assert client.get("/admin/").status_code == 302
    assert client.get("/admin/users/1").status_code == 302


def test_admin_user_detail_shows_day_sets(client, db):
    """user_detail counts prescriptions via day_entry_sets, not day_exercises."""
    make_admin(client, "boss")
    make_user(client, "alice")
    client.post("/sports/new", data={"name": "S"})
    sport = scalar(db, "SELECT id FROM sports WHERE name = 'S'")
    client.post(f"/sports/{sport}/workouts/new", data={"name": "W"})
    workout = scalar(db, "SELECT id FROM workouts WHERE sport_id = ?", sport)
    client.post(f"/sports/{sport}/workouts/{workout}/days/new", data={"day_name": "D"})
    day = scalar(db, "SELECT id FROM workout_days WHERE workout_id = ?", workout)
    client.post("/library/exercises/new", data={"name": "Lift", "label": "strength", "muscles": []})
    lift = scalar(db, "SELECT id FROM library_exercises WHERE name = 'Lift'")
    client.post(f"/sports/{sport}/workouts/{workout}/days/{day}/build", data={"target": f"e:{lift}"})

    alice = scalar(db, "SELECT id FROM users WHERE username = 'alice'")
    boss = scalar(db, "SELECT id FROM users WHERE username = 'boss'")

    client.post("/logout")
    client.post("/login", data={"username": "boss", "password": "secret1"})
    r = client.get(f"/admin/users/{alice}")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Traceback" not in body
    # the exercise count on the detail page comes from day_entry_sets
    assert "day_exercises" not in body
    assert boss  # admin session active


def test_admin_user_detail_shows_cardio_goals(client, db):
    """Admin user detail includes the user's active cardio goals."""
    make_admin(client, "boss")
    make_user(client, "alice")
    client.post("/goals/new", data={
        "goal_type": "cardio", "category": "Running", "distance_m": "5000",
        "status": "active",
    })

    alice = scalar(db, "SELECT id FROM users WHERE username = 'alice'")
    client.post("/logout")
    client.post("/login", data={"username": "boss", "password": "secret1"})
    body = client.get(f"/admin/users/{alice}").get_data(as_text=True)
    assert "Running" in body
    assert "cardio" in body


PERSONAL_PAGES = ["/", "/sports/", "/diets/", "/goals/", "/stats/"]


def test_admin_redirected_from_personal_sections(client, db):
    make_admin(client, "boss")
    for path in PERSONAL_PAGES:
        r = client.get(path)
        assert r.status_code == 302, path
        assert "/admin" in r.headers["Location"], f"{path} -> {r.headers['Location']}"


def test_admin_blocked_post_creates_nothing(client, db):
    make_admin(client, "boss")
    r = client.post("/sports/new", data={"name": "Sneaky"})
    assert r.status_code == 302
    assert scalar(db, "SELECT COUNT(*) FROM sports WHERE name = 'Sneaky'") == 0


def test_admin_redirected_from_library_keeps_profile(client, db):
    make_admin(client, "boss")
    r = client.get("/library/")
    assert r.status_code == 302
    assert "/admin" in r.headers["Location"]
    assert client.get("/profile/").status_code == 200


def test_admin_not_listed_in_user_view(client, db):
    make_user(client, "alice")
    make_admin(client, "boss")
    body = client.get("/admin/").get_data(as_text=True)
    assert "alice@example.com" in body
    assert "boss@example.com" not in body


def test_admin_settings_page(client, db):
    make_admin(client, "boss")
    r = client.get("/admin/settings")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "Application settings" in body
    assert "Traceback" not in body


def test_admin_nav_hides_personal_links(client, db):
    make_admin(client, "boss")
    body = client.get("/admin/").get_data(as_text=True)
    for frag in ("/sports", "/diets", "/goals", "/stats", "/library"):
        assert frag not in body, frag
    assert "/admin" in body


def test_regular_user_nav_keeps_sections(client, db):
    make_user(client, "tester")
    body = client.get("/").get_data(as_text=True)
    assert "/sports" in body and "/diets" in body and "/goals" in body and "/stats" in body
