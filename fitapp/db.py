import sqlite3

import click
from flask import current_app, g


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    height_cm     REAL,
    birth_date    TEXT,
    sex           TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workouts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    workout_type TEXT NOT NULL CHECK (workout_type IN ('strength', 'cardio', 'hybrid')),
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workout_days (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER NOT NULL REFERENCES workouts (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    name       TEXT NOT NULL,
    focus      TEXT,
    notes      TEXT
);

CREATE TABLE IF NOT EXISTS circuits (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_day_id INTEGER NOT NULL REFERENCES workout_days (id) ON DELETE CASCADE,
    position      INTEGER NOT NULL DEFAULT 0,
    label         TEXT NOT NULL,
    rounds        INTEGER NOT NULL DEFAULT 3,
    rest_sec      INTEGER NOT NULL DEFAULT 60
);

CREATE TABLE IF NOT EXISTS day_exercises (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_day_id INTEGER NOT NULL REFERENCES workout_days (id) ON DELETE CASCADE,
    circuit_id    INTEGER REFERENCES circuits (id) ON DELETE CASCADE,
    position      INTEGER NOT NULL DEFAULT 0,
    kind          TEXT NOT NULL CHECK (kind IN ('strength', 'cardio')),
    name          TEXT NOT NULL,
    sets          INTEGER,
    reps          INTEGER,
    metric        TEXT CHECK (metric IN ('weight', 'duration')),
    weight_kg     REAL,
    duration_sec  INTEGER,
    duration_min  REAL,
    distance_km   REAL,
    rest_sec      INTEGER,
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS workout_sessions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    workout_day_id INTEGER REFERENCES workout_days (id) ON DELETE SET NULL,
    performed_date TEXT NOT NULL,
    duration_min  INTEGER,
    calories      REAL,
    notes         TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS session_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    INTEGER NOT NULL REFERENCES workout_sessions (id) ON DELETE CASCADE,
    kind          TEXT NOT NULL,
    name          TEXT NOT NULL,
    circuit_label TEXT,
    sets          INTEGER,
    reps          INTEGER,
    metric        TEXT,
    weight_kg     REAL,
    duration_sec  INTEGER,
    duration_min  REAL,
    distance_km   REAL,
    position      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS diets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    diet_date   TEXT NOT NULL,
    meal_type   TEXT NOT NULL,
    description TEXT NOT NULL,
    calories    REAL,
    protein_g   REAL,
    carbs_g     REAL,
    fat_g       REAL,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS body_stats (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    stat_date    TEXT NOT NULL,
    weight_kg    REAL,
    body_fat_pct REAL,
    chest_cm     REAL,
    waist_cm     REAL,
    hip_cm       REAL,
    arm_cm       REAL,
    notes        TEXT
);

CREATE TABLE IF NOT EXISTS goals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    goal_type    TEXT NOT NULL CHECK (goal_type IN ('performance', 'body')),
    category     TEXT NOT NULL,
    target_value REAL NOT NULL,
    unit         TEXT NOT NULL,
    start_value  REAL,
    target_date  TEXT,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'achieved', 'abandoned')),
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_workouts_user ON workouts (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_days_workout ON workout_days (workout_id, position);
CREATE INDEX IF NOT EXISTS idx_circuits_day ON circuits (workout_day_id, position);
CREATE INDEX IF NOT EXISTS idx_exercises_day ON day_exercises (workout_day_id, position);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON workout_sessions (user_id, performed_date);
CREATE INDEX IF NOT EXISTS idx_session_entries ON session_entries (session_id, position);
CREATE INDEX IF NOT EXISTS idx_diets_user ON diets (user_id, diet_date);
CREATE INDEX IF NOT EXISTS idx_stats_user ON body_stats (user_id, stat_date);
CREATE INDEX IF NOT EXISTS idx_goals_user ON goals (user_id, status);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    db.commit()


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("Database initialized.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
