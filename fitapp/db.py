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

CREATE TABLE IF NOT EXISTS sports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    sport_type TEXT NOT NULL CHECK (sport_type IN ('gym', 'cardio', 'hybrid')),
    notes      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workouts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id   INTEGER NOT NULL REFERENCES sports (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    name       TEXT NOT NULL,
    notes      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS workout_days (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER NOT NULL REFERENCES workouts (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    name       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workout_modules (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id INTEGER NOT NULL REFERENCES sports (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    name     TEXT NOT NULL,
    focus    TEXT,
    notes    TEXT
);

CREATE TABLE IF NOT EXISTS day_modules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_day_id INTEGER NOT NULL REFERENCES workout_days (id) ON DELETE CASCADE,
    module_id      INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    position       INTEGER NOT NULL DEFAULT 0,
    UNIQUE (workout_day_id, module_id)
);

CREATE TABLE IF NOT EXISTS circuits (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_module_id INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    position          INTEGER NOT NULL DEFAULT 0,
    label             TEXT NOT NULL,
    rounds            INTEGER NOT NULL DEFAULT 3,
    rest_sec          INTEGER NOT NULL DEFAULT 60
);

CREATE TABLE IF NOT EXISTS day_exercises (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_module_id INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    circuit_id        INTEGER REFERENCES circuits (id) ON DELETE CASCADE,
    position          INTEGER NOT NULL DEFAULT 0,
    kind              TEXT NOT NULL CHECK (kind IN ('gym', 'cardio')),
    name              TEXT NOT NULL,
    sets              INTEGER,
    reps              INTEGER,
    metric            TEXT CHECK (metric IN ('weight', 'duration')),
    weight_kg         REAL,
    duration_sec      INTEGER,
    duration_min      REAL,
    distance_km       REAL,
    rest_sec          INTEGER,
    notes             TEXT
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

CREATE INDEX IF NOT EXISTS idx_sports_user ON sports (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_workouts_sport ON workouts (sport_id, position);
CREATE INDEX IF NOT EXISTS idx_days_workout ON workout_days (workout_id, position);
CREATE INDEX IF NOT EXISTS idx_modules_sport ON workout_modules (sport_id, position);
CREATE INDEX IF NOT EXISTS idx_day_modules_day ON day_modules (workout_day_id, position);
CREATE INDEX IF NOT EXISTS idx_circuits_module ON circuits (workout_module_id, position);
CREATE INDEX IF NOT EXISTS idx_exercises_module ON day_exercises (workout_module_id, position);
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


def _table_exists(db, name):
    return db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
    ).fetchone() is not None


def _migrate_sports(db):
    """Restructure workouts/workout_days into sport -> workout -> day -> module.

    For existing databases the old tables are migrated in place: every program
    becomes a sport with one default workout, one default day, and its old
    modules moved under that day.
    """
    if not _table_exists(db, "workouts"):
        return
    cols = db.execute("PRAGMA table_info(workouts)").fetchall()
    if not any(col["name"] == "workout_type" for col in cols):
        return

    old_workouts = [dict(r) for r in db.execute("SELECT * FROM workouts ORDER BY id")]
    old_days = (
        [dict(r) for r in db.execute("SELECT * FROM workout_days ORDER BY id")]
        if _table_exists(db, "workout_days")
        else []
    )
    old_circuits = (
        [dict(r) for r in db.execute("SELECT * FROM circuits ORDER BY id")]
        if _table_exists(db, "circuits")
        else []
    )
    old_exercises = (
        [dict(r) for r in db.execute("SELECT * FROM day_exercises ORDER BY id")]
        if _table_exists(db, "day_exercises")
        else []
    )

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.executescript("""
            DROP TABLE IF EXISTS day_exercises;
            DROP TABLE IF EXISTS circuits;
            DROP TABLE IF EXISTS workout_days;
            DROP TABLE IF EXISTS workout_modules;
            DROP TABLE IF EXISTS workouts;
            DROP TABLE IF EXISTS sports;
        """)
        db.executescript(_SPORTS_CREATE)

        sport_type_by_workout = {}
        for row in old_workouts:
            sport_type = "gym" if row.get("workout_type") == "strength" else row.get("workout_type")
            db.execute(
                "INSERT INTO sports (id, user_id, name, sport_type, notes, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], row["user_id"], row["name"], sport_type,
                 row.get("notes"), row.get("created_at")),
            )
            db.execute(
                "INSERT INTO workouts (id, sport_id, position, name, notes, created_at) "
                "VALUES (?, ?, 0, ?, '', ?)",
                (row["id"], row["id"], row["name"], row.get("created_at")),
            )
            sport_type_by_workout[row["id"]] = sport_type

        day_id_by_workout = {}
        for wid in sport_type_by_workout:
            cursor = db.execute(
                "INSERT INTO workout_days (workout_id, position, name) VALUES (?, 0, 'Day 1')",
                (wid,),
            )
            day_id_by_workout[wid] = cursor.lastrowid

        for row in old_days:
            db.execute(
                "INSERT INTO workout_modules "
                "(id, workout_day_id, position, name, focus, notes) VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], day_id_by_workout[row["workout_id"]], row["position"],
                 row["name"], row.get("focus"), row.get("notes")),
            )

        for row in old_circuits:
            db.execute(
                "INSERT INTO circuits (id, workout_module_id, position, label, rounds, rest_sec) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], row["workout_day_id"], row["position"], row["label"],
                 row["rounds"], row["rest_sec"]),
            )

        for row in old_exercises:
            db.execute(
                "INSERT INTO day_exercises "
                "(id, workout_module_id, circuit_id, position, kind, name, sets, reps, metric, "
                " weight_kg, duration_sec, duration_min, distance_km, rest_sec, notes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (row["id"], row["workout_day_id"], row.get("circuit_id"), row["position"],
                 row["kind"], row["name"], row.get("sets"), row.get("reps"), row.get("metric"),
                 row.get("weight_kg"), row.get("duration_sec"), row.get("duration_min"),
                 row.get("distance_km"), row.get("rest_sec"), row.get("notes")),
            )
    finally:
        db.execute("PRAGMA foreign_keys = ON")


_SPORTS_CREATE = """
CREATE TABLE sports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    name       TEXT NOT NULL,
    sport_type TEXT NOT NULL CHECK (sport_type IN ('gym', 'cardio', 'hybrid')),
    notes      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE workouts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    sport_id   INTEGER NOT NULL REFERENCES sports (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    name       TEXT NOT NULL,
    notes      TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE workout_days (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_id INTEGER NOT NULL REFERENCES workouts (id) ON DELETE CASCADE,
    position   INTEGER NOT NULL DEFAULT 0,
    name       TEXT NOT NULL
);

CREATE TABLE workout_modules (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_day_id INTEGER NOT NULL REFERENCES workout_days (id) ON DELETE CASCADE,
    position       INTEGER NOT NULL DEFAULT 0,
    name           TEXT NOT NULL,
    focus          TEXT,
    notes          TEXT
);

CREATE TABLE circuits (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_module_id INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    position          INTEGER NOT NULL DEFAULT 0,
    label             TEXT NOT NULL,
    rounds            INTEGER NOT NULL DEFAULT 3,
    rest_sec          INTEGER NOT NULL DEFAULT 60
);

CREATE TABLE day_exercises (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_module_id INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    circuit_id        INTEGER REFERENCES circuits (id) ON DELETE CASCADE,
    position          INTEGER NOT NULL DEFAULT 0,
    kind              TEXT NOT NULL CHECK (kind IN ('gym', 'cardio')),
    name              TEXT NOT NULL,
    sets              INTEGER,
    reps              INTEGER,
    metric            TEXT CHECK (metric IN ('weight', 'duration')),
    weight_kg         REAL,
    duration_sec      INTEGER,
    duration_min      REAL,
    distance_km       REAL,
    rest_sec          INTEGER,
    notes             TEXT
);
"""


def _migrate_workout_kinds(db):
    """Rename the sport category 'strength' -> 'gym' for existing data."""
    for table, kind_col in (("sports", "sport_type"), ("day_exercises", "kind")):
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
    if kind_col == "sport_type":
        return f"""
        CREATE TABLE {table}_gym (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
            name       TEXT NOT NULL,
            sport_type TEXT NOT NULL CHECK (sport_type IN ('gym', 'cardio', 'hybrid')),
            notes      TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        INSERT INTO {table}_gym (id, user_id, name, sport_type, notes, created_at)
            SELECT id, user_id, name,
                   CASE WHEN sport_type = 'strength' THEN 'gym' ELSE sport_type END,
                   notes, created_at
            FROM {table};
        DROP TABLE {table};
        ALTER TABLE {table}_gym RENAME TO {table};
        """
    return f"""
    CREATE TABLE {table}_gym (
        id                INTEGER PRIMARY KEY AUTOINCREMENT,
        workout_module_id INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
        circuit_id        INTEGER REFERENCES circuits (id) ON DELETE CASCADE,
        position          INTEGER NOT NULL DEFAULT 0,
        kind              TEXT NOT NULL CHECK (kind IN ('gym', 'cardio')),
        name              TEXT NOT NULL,
        sets              INTEGER,
        reps              INTEGER,
        metric            TEXT CHECK (metric IN ('weight', 'duration')),
        weight_kg         REAL,
        duration_sec      INTEGER,
        duration_min      REAL,
        distance_km       REAL,
        rest_sec          INTEGER,
        notes             TEXT
    );
    INSERT INTO {table}_gym (
            id, workout_module_id, circuit_id, position, kind, name, sets, reps,
            metric, weight_kg, duration_sec, duration_min, distance_km, rest_sec, notes)
        SELECT id, workout_module_id, circuit_id, position,
               CASE WHEN kind = 'strength' THEN 'gym' ELSE kind END,
               name, sets, reps, metric, weight_kg, duration_sec,
               duration_min, distance_km, rest_sec, notes
        FROM {table};
    DROP TABLE {table};
    ALTER TABLE {table}_gym RENAME TO {table};
    """


def _migrate_module_library(db):
    """Make workout_modules a sport-level library and schedule them via day_modules.

    Old databases keep workout_day_id on each module. Those rows become sport
    library modules and a day_modules link is created for the day they belonged
    to, so existing day content is preserved without duplication.
    """
    if not _table_exists(db, "workout_modules"):
        return
    cols = db.execute("PRAGMA table_info(workout_modules)").fetchall()
    if not any(col["name"] == "workout_day_id" for col in cols):
        return

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.executescript("""
            DROP TABLE IF EXISTS workout_modules_lib;
            CREATE TABLE workout_modules_lib (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                sport_id INTEGER NOT NULL REFERENCES sports (id) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                name     TEXT NOT NULL,
                focus    TEXT,
                notes    TEXT
            );
            INSERT INTO workout_modules_lib (id, sport_id, position, name, focus, notes)
                SELECT m.id,
                       (SELECT w.sport_id
                          FROM workout_days d
                          JOIN workouts w ON w.id = d.workout_id
                         WHERE d.id = m.workout_day_id),
                       m.position, m.name, m.focus, m.notes
                FROM workout_modules m;
            CREATE TABLE IF NOT EXISTS day_modules (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                workout_day_id INTEGER NOT NULL REFERENCES workout_days (id) ON DELETE CASCADE,
                module_id      INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
                position       INTEGER NOT NULL DEFAULT 0,
                UNIQUE (workout_day_id, module_id)
            );
            INSERT INTO day_modules (workout_day_id, module_id, position)
                SELECT workout_day_id, id, position
                FROM workout_modules
                WHERE workout_day_id IS NOT NULL;
            DROP TABLE workout_modules;
            ALTER TABLE workout_modules_lib RENAME TO workout_modules;
        """)
    finally:
        db.execute("PRAGMA foreign_keys = ON")


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
    _migrate_sports(db)
    _migrate_workout_kinds(db)
    _migrate_module_library(db)
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
