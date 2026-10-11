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
    role          TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workouts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    workout_type TEXT NOT NULL CHECK (workout_type IN ('gym', 'cardio', 'hybrid')),
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
    kind          TEXT NOT NULL CHECK (kind IN ('gym', 'cardio')),
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
    goal_type    TEXT NOT NULL CHECK (goal_type IN ('body', 'skill', 'strength')),
    category     TEXT NOT NULL,
    target_value TEXT NOT NULL,
    unit         TEXT NOT NULL CHECK (unit IN ('kg', '%', 'seconds', 'reps', 'levels')),
    start_value  TEXT,
    target_date  TEXT,
    status       TEXT NOT NULL DEFAULT 'active'
                 CHECK (status IN ('active', 'achieved', 'abandoned')),
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_lifestyle (
    user_id             INTEGER PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    sessions_per_week   INTEGER,
    intensity           TEXT CHECK (intensity IN ('low', 'moderate', 'high')),
    session_duration_min INTEGER,
    activity_level      TEXT CHECK (activity_level IN
                        ('sedentary', 'light', 'moderate', 'active', 'very_active')),
    sleep_hours         REAL,
    daily_calories      REAL,
    goal_direction      TEXT CHECK (goal_direction IN ('lose', 'maintain', 'gain')),
    water_cups          REAL,
    stress_level        TEXT CHECK (stress_level IN ('low', 'moderate', 'high')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS goal_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    goal_id     INTEGER NOT NULL REFERENCES goals (id) ON DELETE CASCADE,
    value       TEXT NOT NULL,
    logged_date TEXT NOT NULL,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS exercises (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL CHECK (category IN ('gym', 'cardio')),
    subcategory TEXT CHECK (subcategory IN ('strength', 'skill')),
    name        TEXT NOT NULL UNIQUE COLLATE NOCASE,
    notes       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ((category = 'cardio' AND subcategory IS NULL)
        OR (category = 'gym' AND subcategory IN ('strength', 'skill')))
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
CREATE INDEX IF NOT EXISTS idx_goal_logs_goal ON goal_logs (goal_id, logged_date);
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


def _migrate_goals(db):
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'goals'"
    ).fetchone()
    if row and "'skill'" not in (row["sql"] or ""):
        db.execute("DROP TABLE IF EXISTS goal_logs")
        db.execute("DROP TABLE IF EXISTS goals")


def _migrate_workout_kinds(db):
    """Rename the workout category 'strength' -> 'gym' for existing data."""
    if db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'session_entries'"
    ).fetchone():
        db.execute("UPDATE session_entries SET kind = 'gym' WHERE kind = 'strength'")
        db.commit()

    for table, kind_col in (("workouts", "workout_type"), ("day_exercises", "kind")):
        row = db.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if not (row and "'strength'" in (row["sql"] or "")):
            continue
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.executescript(_rebuild_workout_table(table, kind_col))
        finally:
            db.execute("PRAGMA foreign_keys = ON")


def _rebuild_workout_table(table, kind_col):
    if kind_col == "workout_type":
        return f"""
        CREATE TABLE {table}_gym (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            name         TEXT NOT NULL,
            workout_type TEXT NOT NULL CHECK (workout_type IN ('gym', 'cardio', 'hybrid')),
            notes        TEXT,
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO {table}_gym (id, user_id, name, workout_type, notes, created_at)
            SELECT id, user_id, name,
                   CASE WHEN workout_type = 'strength' THEN 'gym' ELSE workout_type END,
                   notes, created_at
            FROM {table};
        DROP TABLE {table};
        ALTER TABLE {table}_gym RENAME TO {table};
        """
    return f"""
    CREATE TABLE {table}_gym (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        workout_day_id INTEGER NOT NULL REFERENCES workout_days (id) ON DELETE CASCADE,
        circuit_id     INTEGER REFERENCES circuits (id) ON DELETE CASCADE,
        position       INTEGER NOT NULL DEFAULT 0,
        kind           TEXT NOT NULL CHECK (kind IN ('gym', 'cardio')),
        name           TEXT NOT NULL,
        sets           INTEGER,
        reps           INTEGER,
        metric         TEXT CHECK (metric IN ('weight', 'duration')),
        weight_kg      REAL,
        duration_sec   INTEGER,
        duration_min   REAL,
        distance_km    REAL,
        rest_sec       INTEGER,
        notes          TEXT
    );
    INSERT INTO {table}_gym (
            id, workout_day_id, circuit_id, position, kind, name, sets, reps,
            metric, weight_kg, duration_sec, duration_min, distance_km, rest_sec, notes)
        SELECT id, workout_day_id, circuit_id, position,
               CASE WHEN kind = 'strength' THEN 'gym' ELSE kind END,
               name, sets, reps, metric, weight_kg, duration_sec,
               duration_min, distance_km, rest_sec, notes
        FROM {table};
    DROP TABLE {table};
    ALTER TABLE {table}_gym RENAME TO {table};
    """


def _migrate_roles(db):
    if not db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'users'"
    ).fetchone():
        return
    cols = db.execute("PRAGMA table_info(users)").fetchall()
    if not any(col["name"] == "role" for col in cols):
        db.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        db.commit()


def init_db():
    db = get_db()
    _migrate_goals(db)
    _migrate_workout_kinds(db)
    _migrate_roles(db)
    db.executescript(SCHEMA)
    db.commit()


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("Database initialized.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
