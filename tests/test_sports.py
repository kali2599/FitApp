"""Sport -> workout -> day -> build flow and per-day prescriptions (Phase 3)."""
import re

from helpers import make_user, scalar


def _id(location):
    return int(re.search(r"/(\d+)(?:/|$|\?)", location).group(1))


def _setup_library(client, db):
    for name, label in (("Push-up", "strength"), ("Dip", "strength"), ("Plank", "skill")):
        client.post("/library/exercises/new", data={"name": name, "label": label, "muscles": []})
    pushup = scalar(db, "SELECT id FROM library_exercises WHERE name = 'Push-up'")
    dip = scalar(db, "SELECT id FROM library_exercises WHERE name = 'Dip'")
    plank = scalar(db, "SELECT id FROM library_exercises WHERE name = 'Plank'")
    client.post(
        "/library/circuits/new",
        data={"name": "Burner", "rounds": "3", "rest_sec": "60",
              "member_id": [str(pushup), str(dip)]},
    )
    circuit = scalar(db, "SELECT id FROM library_circuits WHERE name = 'Burner'")
    client.post(
        "/library/modules/new",
        data={"name": "Push day", "item_type": ["exercise", "circuit"],
              "item_id": [str(plank), str(circuit)]},
    )
    module = scalar(db, "SELECT id FROM workout_modules WHERE name = 'Push day'")
    return {"pushup": pushup, "dip": dip, "plank": plank, "circuit": circuit, "module": module}


def _setup_day(client, db):
    client.post("/sports/new", data={"name": "Calisthenics"})
    sport = scalar(db, "SELECT id FROM sports WHERE name = 'Calisthenics'")
    client.post(f"/sports/{sport}/workouts/new", data={"name": "Week 1"})
    workout = scalar(db, "SELECT id FROM workouts WHERE sport_id = ?", sport)
    client.post(f"/sports/{sport}/workouts/{workout}/days/new", data={"day_name": "Push"})
    day = scalar(db, "SELECT id FROM workout_days WHERE workout_id = ? AND name = 'Push'", workout)
    return sport, workout, day


def test_full_build_flow(client, db):
    make_user(client, "tester")
    lib = _setup_library(client, db)
    sport, workout, day = _setup_day(client, db)
    base = f"/sports/{sport}/workouts/{workout}/days/{day}"

    assert client.post(f"{base}/build", data={"target": f"m:{lib['module']}"}).status_code == 302
    assert client.post(f"{base}/build", data={"target": f"e:{lib['pushup']}"}).status_code == 302
    assert client.post(f"{base}/build", data={"target": f"c:{lib['circuit']}"}).status_code == 302
    assert scalar(db, "SELECT COUNT(*) FROM day_entries WHERE workout_day_id = ?", day) == 3

    # module expands to its library items (plank + circuit members)
    mod_entry = scalar(db, "SELECT id FROM day_entries WHERE workout_day_id = ? AND module_id = ?",
                       day, lib["module"])
    assert scalar(db, "SELECT COUNT(*) FROM day_entry_sets WHERE day_entry_id = ?", mod_entry) == 3

    # single exercise gets one set row
    ex_entry = scalar(db, "SELECT id FROM day_entries WHERE workout_day_id = ? AND exercise_id = ?",
                      day, lib["pushup"])
    assert scalar(db, "SELECT COUNT(*) FROM day_entry_sets WHERE day_entry_id = ?", ex_entry) == 1

    # day detail shows all three entry kinds
    html = client.get(base).get_data(as_text=True)
    assert "Push day" in html and "Push-up" in html and "Burner" in html


def test_invalid_target_rejected(client, db):
    make_user(client, "tester")
    _setup_library(client, db)
    sport, workout, day = _setup_day(client, db)
    base = f"/sports/{sport}/workouts/{workout}/days/{day}/build"
    assert client.post(base, data={"target": "e:999999"}).status_code == 400
    assert client.post(base, data={"action": "add", "target": ""}).status_code == 400


def test_prescriptions_saved(client, db):
    make_user(client, "tester")
    lib = _setup_library(client, db)
    sport, workout, day = _setup_day(client, db)
    base = f"/sports/{sport}/workouts/{workout}/days/{day}/build"
    client.post(base, data={"target": f"e:{lib['pushup']}"})
    set_id = scalar(db, "SELECT s.id FROM day_entry_sets s JOIN day_entries de ON de.id = s.day_entry_id "
                        "WHERE de.workout_day_id = ?", day)

    r = client.post(base, data={
        "action": "save", "set_id": [str(set_id)],
        f"sets_{set_id}": "4", f"reps_{set_id}": "8", f"weight_{set_id}": "20",
        f"duration_sec_{set_id}": "", f"duration_min_{set_id}": "", f"distance_{set_id}": "",
        f"rest_{set_id}": "90", f"notes_{set_id}": "",
    })
    assert r.status_code == 302
    row = db.execute("SELECT sets, reps, weight_kg, rest_sec FROM day_entry_sets WHERE id = ?",
                     (set_id,)).fetchone()
    assert (row["sets"], row["reps"], row["weight_kg"], row["rest_sec"]) == (4, 8, 20.0, 90)

    # 'max' marker stored as text
    client.post(base, data={
        "action": "save", "set_id": [str(set_id)],
        f"sets_{set_id}": "3", f"reps_{set_id}": "max", f"weight_{set_id}": "",
        f"duration_sec_{set_id}": "", f"duration_min_{set_id}": "", f"distance_{set_id}": "",
        f"rest_{set_id}": "", f"notes_{set_id}": "",
    })
    row = db.execute("SELECT reps, weight_kg FROM day_entry_sets WHERE id = ?", (set_id,)).fetchone()
    assert row["reps"] == "max" and row["weight_kg"] is None

    # a bad value is rejected
    r = client.post(base, data={
        "action": "save", "set_id": [str(set_id)],
        f"sets_{set_id}": "abc", f"reps_{set_id}": "", f"weight_{set_id}": "",
        f"duration_sec_{set_id}": "", f"duration_min_{set_id}": "", f"distance_{set_id}": "",
        f"rest_{set_id}": "", f"notes_{set_id}": "",
    })
    assert r.status_code == 400


def test_remove_entry_cascades(client, db):
    make_user(client, "tester")
    lib = _setup_library(client, db)
    sport, workout, day = _setup_day(client, db)
    base = f"/sports/{sport}/workouts/{workout}/days/{day}"
    client.post(f"{base}/build", data={"target": f"c:{lib['circuit']}"})
    entry = scalar(db, "SELECT id FROM day_entries WHERE workout_day_id = ? AND circuit_id = ?",
                   day, lib["circuit"])
    assert client.post(f"{base}/entries/{entry}/remove").status_code == 302
    assert scalar(db, "SELECT COUNT(*) FROM day_entries WHERE id = ?", entry) == 0
    assert scalar(db, "SELECT COUNT(*) FROM day_entry_sets WHERE day_entry_id = ?", entry) == 0


def test_foreign_day_is_404(client, db):
    make_user(client, "tester")
    lib = _setup_library(client, db)
    sport, workout, day = _setup_day(client, db)
    make_user(client, "intruder")
    assert client.get(f"/sports/{sport}/workouts/{workout}/days/{day}").status_code == 404
