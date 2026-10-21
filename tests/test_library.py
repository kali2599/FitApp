"""Library CRUD, tabs and per-user isolation (Phase 2)."""
from helpers import make_user, scalar


def test_pages_render(client, db):
    make_user(client, "tester")
    for url in [
        "/library",
        "/library?tab=exercises",
        "/library/modules/new",
        "/library/exercises/new",
        "/library/circuits/new",
    ]:
        assert client.get(url).status_code == 200, url

    html = client.get("/library").get_data(as_text=True)
    assert ">Library<" in html.replace("\n", "")
    assert "Module library" not in html


def test_exercise_crud(client, db):
    make_user(client, "tester")
    r = client.post(
        "/library/exercises/new",
        data={"name": "Test Press", "label": "strength", "muscles": ["Chest", "Triceps"]},
    )
    assert r.status_code == 302

    row = db.execute("SELECT * FROM library_exercises WHERE name = 'Test Press'").fetchone()
    assert row is not None
    assert row["muscles"] == "Chest,Triceps"
    assert row["label"] == "strength"

    # duplicate (case-insensitive) rejected
    r = client.post("/library/exercises/new", data={"name": "test press", "muscles": []})
    assert r.status_code == 400

    # edit
    r = client.post(
        f"/library/exercises/{row['id']}/edit",
        data={"name": "Test Press", "label": "skill", "muscles": ["Chest"]},
    )
    assert r.status_code == 302
    row = db.execute("SELECT * FROM library_exercises WHERE id = ?", (row["id"],)).fetchone()
    assert row["label"] == "skill"
    assert row["muscles"] == "Chest"

    # delete
    assert client.post(f"/library/exercises/{row['id']}/delete").status_code == 302
    assert scalar(db, "SELECT COUNT(*) FROM library_exercises WHERE id = ?", row["id"]) == 0


def test_circuit_crud(client, db):
    make_user(client, "tester")
    client.post("/library/exercises/new", data={"name": "A", "muscles": []})
    client.post("/library/exercises/new", data={"name": "B", "muscles": []})
    a = scalar(db, "SELECT id FROM library_exercises WHERE name = 'A'")
    b = scalar(db, "SELECT id FROM library_exercises WHERE name = 'B'")

    r = client.post(
        "/library/circuits/new",
        data={"name": "Burner", "rounds": "3", "rest_sec": "45", "member_id": [str(a), str(b)]},
    )
    assert r.status_code == 302
    circ = db.execute("SELECT * FROM library_circuits WHERE name = 'Burner'").fetchone()
    members = [
        m["exercise_id"]
        for m in db.execute(
            "SELECT exercise_id FROM library_circuit_members WHERE circuit_id = ? ORDER BY position",
            (circ["id"],),
        )
    ]
    assert members == [a, b]

    # a circuit needs at least two members
    r = client.post(
        "/library/circuits/new",
        data={"name": "Bad", "rounds": "3", "rest_sec": "0", "member_id": [str(a)]},
    )
    assert r.status_code == 400


def test_module_crud_and_day_resync(client, db):
    make_user(client, "tester")
    for name in ("Press", "Curl", "Plank"):
        client.post("/library/exercises/new", data={"name": name, "label": "strength", "muscles": []})
    e1 = scalar(db, "SELECT id FROM library_exercises WHERE name = 'Press'")
    e2 = scalar(db, "SELECT id FROM library_exercises WHERE name = 'Curl'")
    e3 = scalar(db, "SELECT id FROM library_exercises WHERE name = 'Plank'")
    client.post(
        "/library/circuits/new",
        data={"name": "Circuit", "rounds": "3", "rest_sec": "60", "member_id": [str(e1), str(e2)]},
    )
    circ = scalar(db, "SELECT id FROM library_circuits WHERE name = 'Circuit'")

    r = client.post(
        "/library/modules/new",
        data={"name": "Push", "item_type": ["exercise", "circuit"], "item_id": [str(e3), str(circ)]},
    )
    assert r.status_code == 302
    module = scalar(db, "SELECT id FROM workout_modules WHERE name = 'Push'")
    items = db.execute(
        "SELECT exercise_id, circuit_id FROM module_items WHERE module_id = ? ORDER BY position",
        (module,),
    ).fetchall()
    assert len(items) == 2
    assert items[0]["exercise_id"] == e3
    assert items[1]["circuit_id"] == circ

    # place the module on a day, then edit it and confirm the day re-syncs
    sport = _make_day(client, db, "tester")
    client.post(f"/sports/{sport['sport']}/workouts/{sport['workout']}/days/{sport['day']}/build",
                data={"target": f"m:{module}"})
    entry = scalar(db, "SELECT id FROM day_entries WHERE module_id = ?", module)
    before = scalar(db, "SELECT COUNT(*) FROM day_entry_sets WHERE day_entry_id = ? AND exercise_id = ?",
                    entry, e1)

    r = client.post(
        f"/library/modules/{module}/edit",
        data={
            "name": "Push",
            "item_type": ["exercise", "circuit", "exercise"],
            "item_id": [str(e3), str(circ), str(e1)],
        },
    )
    assert r.status_code == 302
    after = scalar(db, "SELECT COUNT(*) FROM day_entry_sets WHERE day_entry_id = ? AND exercise_id = ?",
                   entry, e1)
    assert before == 1 and after == 2  # e1 was already a circuit member, now also standalone


def test_isolation_between_users(client, db):
    make_user(client, "tester")
    client.post("/library/exercises/new", data={"name": "Mine", "muscles": []})
    ex = scalar(db, "SELECT id FROM library_exercises WHERE name = 'Mine'")

    make_user(client, "intruder")
    assert client.get(f"/library/exercises/{ex}/edit").status_code == 404
    assert client.post(f"/library/exercises/{ex}/delete").status_code == 404
    html = client.get("/library?tab=exercises").get_data(as_text=True)
    assert "Mine" not in html


def _make_day(client, db, username):
    client.post("/sports/new", data={"name": "Sport"})
    sport = scalar(db, "SELECT id FROM sports WHERE name = 'Sport'")
    client.post(f"/sports/{sport}/workouts/new", data={"name": "W"})
    workout = scalar(db, "SELECT id FROM workouts WHERE sport_id = ?", sport)
    client.post(f"/sports/{sport}/workouts/{workout}/days/new", data={"day_name": "D"})
    day = scalar(db, "SELECT id FROM workout_days WHERE workout_id = ?", workout)
    return {"sport": sport, "workout": workout, "day": day}


def test_goals_suggestions_come_from_library(client, db):
    """Goal suggestions are the user's library exercises, not a global catalog."""
    make_user(client, "tester")
    client.post("/library/exercises/new",
                data={"name": "Handstand", "label": "skill", "muscles": []})
    r = client.get("/goals/new")
    assert r.status_code == 200
    assert "Handstand" in r.get_data(as_text=True)


def test_cardio_label_and_goal(client, db):
    make_user(client, "tester")
    r = client.post(
        "/library/exercises/new",
        data={"name": "Rowing", "label": "cardio", "muscles": []},
    )
    assert r.status_code == 302
    row = db.execute("SELECT * FROM library_exercises WHERE name = 'Rowing'").fetchone()
    assert row["label"] == "cardio"

    # the unified goal form offers cardio and lists the labelled library exercise
    body = client.get("/goals/new").get_data(as_text=True)
    assert "cardio" in body
    assert "Rowing" in body

    # a cardio goal with the 5 attribute fields is accepted
    r = client.post(
        "/goals/new",
        data={"goal_type": "cardio", "category": "Running", "distance_m": "5000",
              "time_s": "1500", "pace_km_per_min": "3.3", "rounds": "4", "rest_s": "60",
              "status": "active"},
    )
    assert r.status_code == 302
    goal = db.execute("SELECT * FROM cardio_goals WHERE category = 'Running'").fetchone()
    assert goal["distance_m"] == 5000.0
    assert goal["time_s"] == 1500
    assert goal["pace_km_per_min"] == 3.3
    assert goal["rounds"] == 4
    assert goal["rest_s"] == 60

    # distance is required
    r = client.post(
        "/goals/new",
        data={"goal_type": "cardio", "category": "Running", "status": "active"},
    )
    assert r.status_code == 400

    # progress is tracked on distance (meters), logged manually
    r = client.post(
        "/goals/new",
        data={"goal_type": "cardio", "category": "Cycling", "distance_m": "20000",
              "status": "active"},
    )
    assert r.status_code == 302
    goal = db.execute("SELECT * FROM cardio_goals WHERE category = 'Cycling'").fetchone()
    client.post(f"/goals/cardio/{goal['id']}/log",
                data={"value": "10000", "logged_date": "2026-01-01"})
    log = db.execute("SELECT * FROM cardio_goal_logs WHERE cardio_goal_id = ?", (goal["id"],)).fetchone()
    assert log["value"] == "10000.0"

    # the label field still rejects unknown values
    r = client.post("/library/exercises/new", data={"name": "Nope", "label": "bogus", "muscles": []})
    assert r.status_code == 400


def test_goals_page_lists_standard_and_cardio_together(client, db):
    """Strength and cardio goals share one list on /goals."""
    make_user(client, "tester")
    client.post("/goals/new", data={
        "goal_type": "strength", "category": "Bench", "target_value": "100",
        "unit": "kg", "status": "active",
    })
    client.post("/goals/new", data={
        "goal_type": "cardio", "category": "Running", "distance_m": "5000",
        "status": "active",
    })

    body = client.get("/goals/").get_data(as_text=True)
    assert "Bench" in body
    assert "Running" in body
    assert "5000" in body

    # each card links to its own type-scoped edit route
    bench = db.execute("SELECT id FROM goals WHERE category = 'Bench'").fetchone()
    cardio = db.execute("SELECT id FROM cardio_goals WHERE category = 'Running'").fetchone()
    assert f"/goals/{bench['id']}/edit" in body
    assert f"/goals/cardio/{cardio['id']}/edit" in body


def test_standard_goal_cannot_become_cardio(client, db):
    """Editing locks the goal type; a standard goal stays standard."""
    make_user(client, "tester")
    client.post("/goals/new", data={
        "goal_type": "strength", "category": "Bench", "target_value": "100",
        "unit": "kg", "status": "active",
    })
    bench = db.execute("SELECT id FROM goals WHERE category = 'Bench'").fetchone()

    r = client.post(f"/goals/{bench['id']}/edit", data={
        "goal_type": "cardio", "category": "Bench", "distance_m": "5000",
        "status": "active",
    })
    assert r.status_code == 400
    assert db.execute("SELECT COUNT(*) AS n FROM cardio_goals").fetchone()["n"] == 0
