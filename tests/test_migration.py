"""Legacy schema -> unified library migration and fresh-schema shape."""
import sqlite3

import pytest

from fitapp import create_app

NEW_TABLES = ["library_exercises", "library_circuits", "library_circuit_members",
              "module_items", "day_entries", "day_entry_sets"]
LEGACY_TABLES = ["day_exercises", "circuits", "day_modules", "exercises"]

LEGACY_SQL = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE sports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name TEXT NOT NULL, sport_type TEXT, notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE workouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL REFERENCES sports (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL, notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE workout_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER NOT NULL REFERENCES workouts (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL
);
CREATE TABLE workout_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL REFERENCES sports (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0, name TEXT NOT NULL, focus TEXT, notes TEXT
);
CREATE TABLE circuits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_module_id INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0, label TEXT NOT NULL,
    rounds INTEGER NOT NULL DEFAULT 3, rest_sec INTEGER NOT NULL DEFAULT 60
);
CREATE TABLE day_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_module_id INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    circuit_id INTEGER REFERENCES circuits (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    kind TEXT NOT NULL CHECK (kind IN ('gym', 'cardio')),
    name TEXT NOT NULL, sets INTEGER, reps INTEGER,
    metric TEXT CHECK (metric IN ('weight', 'duration')),
    weight_kg REAL, duration_sec INTEGER, duration_min REAL,
    distance_km REAL, rest_sec INTEGER, notes TEXT
);
CREATE TABLE day_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_day_id INTEGER NOT NULL REFERENCES workout_days (id) ON DELETE CASCADE,
    module_id INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0, UNIQUE (workout_day_id, module_id)
);
CREATE TABLE exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL
);
"""

LEGACY_DATA = """
INSERT INTO users (id, username, email, password_hash) VALUES (1, 'u', 'u@e.com', 'x');
INSERT INTO sports (id, user_id, name, sport_type) VALUES (1, 1, 'Sport', 'strength');
INSERT INTO workouts (id, sport_id, name) VALUES (1, 1, 'W');
INSERT INTO workout_days (id, workout_id, name) VALUES (1, 1, 'D');
INSERT INTO workout_modules (id, sport_id, name, focus) VALUES (10, 1, 'Push', 'upper');
INSERT INTO day_modules (workout_day_id, module_id, position) VALUES (1, 10, 0);
INSERT INTO circuits (id, workout_module_id, label, rounds, rest_sec) VALUES (5, 10, 'Burner', 3, 60);
INSERT INTO day_exercises (id, workout_module_id, circuit_id, position, kind, name) VALUES (100, 10, NULL, 0, 'gym', 'Push-up');
INSERT INTO day_exercises (id, workout_module_id, circuit_id, position, kind, name) VALUES (101, 10, NULL, 1, 'cardio', 'Sprint');
INSERT INTO day_exercises (id, workout_module_id, circuit_id, position, kind, name) VALUES (102, 10, 5, 0, 'gym', 'Burpee');
"""


def _make_legacy(path):
    con = sqlite3.connect(path)
    con.executescript(LEGACY_SQL)
    con.executescript(LEGACY_DATA)
    con.commit()
    con.close()


def _tables(path):
    con = sqlite3.connect(path)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    return names


def _columns(path, table):
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    con.close()
    return cols


def _count(path, table, where=""):
    con = sqlite3.connect(path)
    n = con.execute(f"SELECT COUNT(*) FROM {table} {where}").fetchone()[0]
    con.close()
    return n


def test_fresh_db_has_unified_schema_and_no_legacy(tmp_path):
    path = str(tmp_path / "fresh.db")
    create_app({"DATABASE": path, "TESTING": True})
    tables = _tables(path)
    assert set(NEW_TABLES) <= tables
    assert not (set(LEGACY_TABLES) & tables)
    assert "focus" not in _columns(path, "workout_modules")
    for table in NEW_TABLES:
        assert _count(path, table) == 0


def test_legacy_db_migrates_into_library(tmp_path):
    path = str(tmp_path / "legacy.db")
    _make_legacy(path)

    app = create_app({"DATABASE": path, "TESTING": True})
    tables = _tables(path)
    assert not (set(LEGACY_TABLES) & tables), "legacy tables should be dropped"
    assert "focus" not in _columns(path, "workout_modules")
    assert "sport_id" not in _columns(path, "workout_modules")
    assert "sport_type" not in _columns(path, "sports")

    # one library exercise per distinct name, circuits + members rebuilt
    assert _count(path, "library_exercises") == 3
    assert _count(path, "library_circuits") == 1
    assert _count(path, "library_circuit_members") == 1
    # module = Push-up, Sprint, then the Burner circuit
    assert _count(path, "module_items", "WHERE module_id = 10") == 3
    # one day entry (module placement) expanded into three prescriptions
    assert _count(path, "day_entries") == 1
    assert _count(path, "day_entry_sets") == 3

    # labels: gym -> strength, cardio -> NULL (skill only when known)
    con = sqlite3.connect(path)
    labels = dict(con.execute("SELECT name, label FROM library_exercises"))
    con.close()
    assert labels["Push-up"] == "strength"
    assert labels["Sprint"] is None

    # idempotent
    with app.app_context():
        from fitapp import db as fitdb
        fitdb.init_db()
    assert _count(path, "library_exercises") == 3
    assert _count(path, "day_entry_sets") == 3


def test_migration_preserves_existing_library(tmp_path):
    """A database already carrying library rows is not re-migrated."""
    path = str(tmp_path / "partial.db")
    _make_legacy(path)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE library_exercises (id INTEGER PRIMARY KEY, user_id INTEGER, position INTEGER, name TEXT, muscles TEXT, label TEXT, notes TEXT)")
    con.execute("INSERT INTO library_exercises (user_id, position, name) VALUES (1, 0, 'Existing')")
    con.commit()
    con.close()

    create_app({"DATABASE": path, "TESTING": True})
    assert _count(path, "library_exercises") == 1
    # legacy tables are still dropped even though migration short-circuited
    assert not (set(LEGACY_TABLES) & _tables(path))


OLD_CHECK_SQL = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user', created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE library_exercises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    name TEXT NOT NULL, muscles TEXT,
    label TEXT CHECK (label IN ('strength', 'skill')), notes TEXT
);
CREATE TABLE goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    goal_type TEXT NOT NULL CHECK (goal_type IN ('body', 'skill', 'strength')),
    category TEXT NOT NULL, target_value TEXT NOT NULL,
    unit TEXT NOT NULL CHECK (unit IN ('kg', '%', 'seconds', 'reps', 'levels')),
    start_value TEXT, target_date TEXT,
    status TEXT NOT NULL DEFAULT 'active'
           CHECK (status IN ('active', 'achieved', 'abandoned')),
    notes TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE goal_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    goal_id INTEGER NOT NULL REFERENCES goals (id) ON DELETE CASCADE,
    value TEXT NOT NULL, logged_date TEXT NOT NULL, notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
INSERT INTO users (id, username, email, password_hash) VALUES (1, 'u', 'u@e.com', 'x');
INSERT INTO library_exercises (id, user_id, position, name, label) VALUES (1, 1, 0, 'Sprint', 'skill');
INSERT INTO goals (id, user_id, goal_type, category, target_value, unit)
    VALUES (1, 1, 'strength', 'Squat', '60', 'kg');
INSERT INTO goal_logs (id, user_id, goal_id, value, logged_date)
    VALUES (1, 1, 1, '60', '2026-01-01');
"""


def test_old_checks_gain_cardio_label_and_tables(tmp_path):
    """Databases built with the old label CHECK gain the cardio label and tables."""
    path = str(tmp_path / "old_check.db")
    con = sqlite3.connect(path)
    con.executescript(OLD_CHECK_SQL)
    con.commit()
    con.close()

    create_app({"DATABASE": path, "TESTING": True})

    # existing rows survive the table rebuilds
    assert _count(path, "library_exercises") == 1
    assert _count(path, "goals") == 1
    assert _count(path, "goal_logs") == 1

    # the new cardio tables and day_entry_sets columns exist
    assert "cardio_goals" in _tables(path)
    assert "cardio_goal_logs" in _tables(path)
    assert {"distance_m", "pace_km_per_min", "rounds"} <= _columns(path, "day_entry_sets")

    con = sqlite3.connect(path)
    con.execute(
        "INSERT INTO library_exercises (user_id, name, label) VALUES (1, 'Rowing', 'cardio')"
    )
    con.execute(
        "INSERT INTO cardio_goals (user_id, category, distance_m, time_s, pace_km_per_min, rounds, rest_s) "
        "VALUES (1, 'Running', 5000, 1500, 3.3, 4, 60)"
    )
    con.commit()
    con.close()

    assert _count(path, "library_exercises") == 2
    assert _count(path, "cardio_goals") == 1

    # goals no longer accepts the cardio goal_type
    con = sqlite3.connect(path)
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO goals (user_id, goal_type, category, target_value, unit) "
            "VALUES (1, 'cardio', 'Running', '5', 'kg')"
        )
    con.close()
