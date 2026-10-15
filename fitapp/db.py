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
    user_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    name     TEXT NOT NULL,
    notes    TEXT
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
    goal_type    TEXT NOT NULL CHECK (goal_type IN ('body', 'skill', 'strength', 'cardio')),
    category     TEXT NOT NULL,
    target_value TEXT NOT NULL,
    unit         TEXT NOT NULL CHECK (unit IN ('kg', '%', 'seconds', 'reps', 'levels', 'meters', 'kilometers', 'km/min', 'minutes')),
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

CREATE TABLE IF NOT EXISTS library_exercises (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    name     TEXT NOT NULL,
    muscles  TEXT,
    label    TEXT CHECK (label IN ('strength', 'skill', 'cardio')),
    notes    TEXT
);

CREATE TABLE IF NOT EXISTS library_circuits (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    name     TEXT NOT NULL,
    rounds   INTEGER NOT NULL DEFAULT 3,
    rest_sec INTEGER NOT NULL DEFAULT 60,
    notes    TEXT
);

CREATE TABLE IF NOT EXISTS library_circuit_members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    circuit_id  INTEGER NOT NULL REFERENCES library_circuits (id) ON DELETE CASCADE,
    exercise_id INTEGER NOT NULL REFERENCES library_exercises (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS module_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    module_id   INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL DEFAULT 0,
    exercise_id INTEGER REFERENCES library_exercises (id) ON DELETE CASCADE,
    circuit_id  INTEGER REFERENCES library_circuits (id) ON DELETE CASCADE,
    CHECK ((exercise_id IS NULL) <> (circuit_id IS NULL))
);

CREATE TABLE IF NOT EXISTS day_entries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_day_id INTEGER NOT NULL REFERENCES workout_days (id) ON DELETE CASCADE,
    position       INTEGER NOT NULL DEFAULT 0,
    module_id      INTEGER REFERENCES workout_modules (id) ON DELETE CASCADE,
    circuit_id     INTEGER REFERENCES library_circuits (id) ON DELETE CASCADE,
    exercise_id    INTEGER REFERENCES library_exercises (id) ON DELETE CASCADE,
    CHECK ((module_id IS NOT NULL) + (circuit_id IS NOT NULL)
         + (exercise_id IS NOT NULL) = 1)
);

CREATE TABLE IF NOT EXISTS day_entry_sets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day_entry_id INTEGER NOT NULL REFERENCES day_entries (id) ON DELETE CASCADE,
    position     INTEGER NOT NULL DEFAULT 0,
    exercise_id  INTEGER NOT NULL REFERENCES library_exercises (id) ON DELETE CASCADE,
    circuit_id   INTEGER REFERENCES library_circuits (id) ON DELETE SET NULL,
    sets         INTEGER,
    reps         INTEGER,
    weight_kg    REAL,
    duration_sec INTEGER,
    duration_min REAL,
    distance_km  REAL,
    rest_sec     INTEGER,
    notes        TEXT
);

CREATE INDEX IF NOT EXISTS idx_sports_user ON sports (user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_workouts_sport ON workouts (sport_id, position);
CREATE INDEX IF NOT EXISTS idx_days_workout ON workout_days (workout_id, position);
CREATE INDEX IF NOT EXISTS idx_modules_user ON workout_modules (user_id, position);
CREATE INDEX IF NOT EXISTS idx_diets_user ON diets (user_id, diet_date);
CREATE INDEX IF NOT EXISTS idx_stats_user ON body_stats (user_id, stat_date);
CREATE INDEX IF NOT EXISTS idx_goals_user ON goals (user_id, status);
CREATE INDEX IF NOT EXISTS idx_goal_logs_goal ON goal_logs (goal_id, logged_date);

CREATE INDEX IF NOT EXISTS idx_library_exercises_user ON library_exercises (user_id, position);
CREATE INDEX IF NOT EXISTS idx_library_circuits_user ON library_circuits (user_id, position);
CREATE INDEX IF NOT EXISTS idx_library_circuit_members ON library_circuit_members (circuit_id, position);
CREATE INDEX IF NOT EXISTS idx_module_items_module ON module_items (module_id, position);
CREATE INDEX IF NOT EXISTS idx_day_entries_day ON day_entries (workout_day_id, position);
CREATE INDEX IF NOT EXISTS idx_day_entry_sets_entry ON day_entry_sets (day_entry_id, position);
"""

_LIBRARY_DDL = """
CREATE TABLE IF NOT EXISTS library_exercises (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    name     TEXT NOT NULL,
    muscles  TEXT,
    label    TEXT CHECK (label IN ('strength', 'skill', 'cardio')),
    notes    TEXT
);

CREATE TABLE IF NOT EXISTS library_circuits (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    name     TEXT NOT NULL,
    rounds   INTEGER NOT NULL DEFAULT 3,
    rest_sec INTEGER NOT NULL DEFAULT 60,
    notes    TEXT
);

CREATE TABLE IF NOT EXISTS library_circuit_members (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    circuit_id  INTEGER NOT NULL REFERENCES library_circuits (id) ON DELETE CASCADE,
    exercise_id INTEGER NOT NULL REFERENCES library_exercises (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS module_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    module_id   INTEGER NOT NULL REFERENCES workout_modules (id) ON DELETE CASCADE,
    position    INTEGER NOT NULL DEFAULT 0,
    exercise_id INTEGER REFERENCES library_exercises (id) ON DELETE CASCADE,
    circuit_id  INTEGER REFERENCES library_circuits (id) ON DELETE CASCADE,
    CHECK ((exercise_id IS NULL) <> (circuit_id IS NULL))
);

CREATE TABLE IF NOT EXISTS day_entries (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    workout_day_id INTEGER NOT NULL REFERENCES workout_days (id) ON DELETE CASCADE,
    position       INTEGER NOT NULL DEFAULT 0,
    module_id      INTEGER REFERENCES workout_modules (id) ON DELETE CASCADE,
    circuit_id     INTEGER REFERENCES library_circuits (id) ON DELETE CASCADE,
    exercise_id    INTEGER REFERENCES library_exercises (id) ON DELETE CASCADE,
    CHECK ((module_id IS NOT NULL) + (circuit_id IS NOT NULL)
         + (exercise_id IS NOT NULL) = 1)
);

CREATE TABLE IF NOT EXISTS day_entry_sets (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    day_entry_id INTEGER NOT NULL REFERENCES day_entries (id) ON DELETE CASCADE,
    position     INTEGER NOT NULL DEFAULT 0,
    exercise_id  INTEGER NOT NULL REFERENCES library_exercises (id) ON DELETE CASCADE,
    circuit_id   INTEGER REFERENCES library_circuits (id) ON DELETE SET NULL,
    sets         INTEGER,
    reps         INTEGER,
    weight_kg    REAL,
    duration_sec INTEGER,
    duration_min REAL,
    distance_km  REAL,
    rest_sec     INTEGER,
    notes        TEXT
);
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


def _migrate_library_shared(db):
    """Turn the per-sport module library into a single per-user library.

    Databases created after the sport-library refactor still key modules by
    sport_id. Those rows move to the owning user so every sport can share the
    same modules. Modules whose sport no longer exists cannot be assigned and
    are skipped.
    """
    if not _table_exists(db, "workout_modules"):
        return
    cols = db.execute("PRAGMA table_info(workout_modules)").fetchall()
    if not any(col["name"] == "sport_id" for col in cols):
        return

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.executescript("""
            DROP TABLE IF EXISTS workout_modules_shared;
            CREATE TABLE workout_modules_shared (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                name     TEXT NOT NULL,
                focus    TEXT,
                notes    TEXT
            );
            INSERT INTO workout_modules_shared (id, user_id, position, name, focus, notes)
                SELECT m.id,
                       (SELECT s.user_id FROM sports s WHERE s.id = m.sport_id),
                       m.position, m.name, m.focus, m.notes
                FROM workout_modules m
                WHERE m.sport_id IN (SELECT id FROM sports);
            DROP TABLE workout_modules;
            ALTER TABLE workout_modules_shared RENAME TO workout_modules;
        """)
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def _migrate_drop_sport_type(db):
    """Drop the redundant sport category column from sports."""
    if not _table_exists(db, "sports"):
        return
    cols = db.execute("PRAGMA table_info(sports)").fetchall()
    if not any(col["name"] == "sport_type" for col in cols):
        return

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.executescript("""
            CREATE TABLE sports_plain (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                name       TEXT NOT NULL,
                notes      TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO sports_plain (id, user_id, name, notes, created_at)
                SELECT id, user_id, name, notes, created_at FROM sports;
            DROP TABLE sports;
            ALTER TABLE sports_plain RENAME TO sports;
        """)
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def _migrate_unified_library(db):
    """Copy the legacy module/day exercise model into the unified library tables.

    Additive: the legacy tables are left in place so the running app keeps
    working; a later migration drops them once the routes use the new model.
    A user-scoped library of exercises and circuits is built from the exercise
    names embedded in the old modules, modules are rebuilt as a structural list
    of library items, and every day placement is expanded into day_entries with
    per-day day_entry_sets (prescriptions copied from the old module).
    """
    if not _table_exists(db, "day_exercises"):
        return
    cols = {row["name"] for row in db.execute("PRAGMA table_info(day_exercises)")}
    if "kind" not in cols:
        return

    db.executescript(_LIBRARY_DDL)
    if db.execute("SELECT 1 FROM library_exercises LIMIT 1").fetchone():
        return

    module_user = {
        row["id"]: row["user_id"]
        for row in db.execute("SELECT id, user_id FROM workout_modules")
        if row["user_id"] is not None
    }

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        exercise_id = {}
        exercise_pos = {}
        for row in db.execute(
            "SELECT de.name, de.kind, m.user_id, de.workout_module_id, de.position, de.id "
            "FROM day_exercises de "
            "JOIN workout_modules m ON m.id = de.workout_module_id "
            "ORDER BY de.workout_module_id, de.position, de.id"
        ):
            uid = row["user_id"]
            if uid is None:
                continue
            key = (uid, row["name"].strip().lower())
            if key in exercise_id:
                continue
            label = "strength" if row["kind"] == "gym" else None
            pos = exercise_pos.get(uid, 0)
            cursor = db.execute(
                "INSERT INTO library_exercises (user_id, position, name, muscles, label, notes) "
                "VALUES (?, ?, ?, NULL, ?, NULL)",
                (uid, pos, row["name"], label),
            )
            exercise_id[key] = cursor.lastrowid
            exercise_pos[uid] = pos + 1

        circuit_id = {}
        circuit_pos = {}
        for row in db.execute(
            "SELECT id, workout_module_id, label, rounds, rest_sec FROM circuits ORDER BY id"
        ):
            uid = module_user.get(row["workout_module_id"])
            if uid is None:
                continue
            pos = circuit_pos.get(uid, 0)
            cursor = db.execute(
                "INSERT INTO library_circuits (user_id, position, name, rounds, rest_sec, notes) "
                "VALUES (?, ?, ?, ?, ?, NULL)",
                (uid, pos, row["label"] or "Circuit", row["rounds"], row["rest_sec"]),
            )
            circuit_id[row["id"]] = cursor.lastrowid
            circuit_pos[uid] = pos + 1

        member_pos = {}
        for row in db.execute(
            "SELECT circuit_id, name, workout_module_id FROM day_exercises "
            "WHERE circuit_id IS NOT NULL ORDER BY circuit_id, position, id"
        ):
            lib_circuit = circuit_id.get(row["circuit_id"])
            uid = module_user.get(row["workout_module_id"])
            lib_exercise = exercise_id.get((uid, row["name"].strip().lower()))
            if lib_circuit is None or lib_exercise is None:
                continue
            pos = member_pos.get(lib_circuit, 0)
            db.execute(
                "INSERT INTO library_circuit_members (circuit_id, exercise_id, position) "
                "VALUES (?, ?, ?)",
                (lib_circuit, lib_exercise, pos),
            )
            member_pos[lib_circuit] = pos + 1

        item_pos = {}
        for row in db.execute(
            "SELECT workout_module_id, name FROM day_exercises "
            "WHERE circuit_id IS NULL ORDER BY workout_module_id, position, id"
        ):
            module = row["workout_module_id"]
            uid = module_user.get(module)
            lib_exercise = exercise_id.get((uid, row["name"].strip().lower()))
            if lib_exercise is None:
                continue
            pos = item_pos.get(module, 0)
            db.execute(
                "INSERT INTO module_items (module_id, position, exercise_id, circuit_id) "
                "VALUES (?, ?, ?, NULL)",
                (module, pos, lib_exercise),
            )
            item_pos[module] = pos + 1
        for row in db.execute(
            "SELECT id, workout_module_id FROM circuits ORDER BY workout_module_id, position, id"
        ):
            lib_circuit = circuit_id.get(row["id"])
            if lib_circuit is None:
                continue
            module = row["workout_module_id"]
            pos = item_pos.get(module, 0)
            db.execute(
                "INSERT INTO module_items (module_id, position, exercise_id, circuit_id) "
                "VALUES (?, ?, NULL, ?)",
                (module, pos, lib_circuit),
            )
            item_pos[module] = pos + 1

        entry_pos = {}
        for placement in db.execute(
            "SELECT workout_day_id, module_id FROM day_modules "
            "ORDER BY workout_day_id, position, id"
        ):
            day = placement["workout_day_id"]
            module = placement["module_id"]
            pos = entry_pos.get(day, 0)
            cursor = db.execute(
                "INSERT INTO day_entries (workout_day_id, position, module_id, circuit_id, exercise_id) "
                "VALUES (?, ?, ?, NULL, NULL)",
                (day, pos, module),
            )
            entry = cursor.lastrowid
            entry_pos[day] = pos + 1

            uid = module_user.get(module)
            set_pos = 0
            for row in db.execute(
                "SELECT * FROM day_exercises WHERE workout_module_id = ? ORDER BY position, id",
                (module,),
            ):
                lib_exercise = exercise_id.get((uid, row["name"].strip().lower()))
                if lib_exercise is None:
                    continue
                lib_circuit = circuit_id.get(row["circuit_id"]) if row["circuit_id"] else None
                db.execute(
                    "INSERT INTO day_entry_sets "
                    "(day_entry_id, position, exercise_id, circuit_id, sets, reps, weight_kg, "
                    " duration_sec, duration_min, distance_km, rest_sec, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (entry, set_pos, lib_exercise, lib_circuit, row["sets"], row["reps"],
                     row["weight_kg"], row["duration_sec"], row["duration_min"],
                     row["distance_km"], row["rest_sec"], row["notes"]),
                )
                set_pos += 1
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def _migrate_drop_legacy(db):
    """Drop the legacy per-module exercise tables and the module focus column.

    Runs after _migrate_unified_library has copied everything into the unified
    library tables. Only acts on databases that still carry the old shape.
    """
    had_legacy = any(
        _table_exists(db, name)
        for name in ("day_exercises", "day_modules", "circuits", "exercises")
    )
    focus_col = False
    if _table_exists(db, "workout_modules"):
        cols = {row["name"] for row in db.execute("PRAGMA table_info(workout_modules)")}
        focus_col = "focus" in cols

    if not had_legacy and not focus_col:
        return

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.executescript("""
            DROP TABLE IF EXISTS day_modules;
            DROP TABLE IF EXISTS day_exercises;
            DROP TABLE IF EXISTS circuits;
            DROP TABLE IF EXISTS exercises;
        """)
        if focus_col:
            db.executescript("""
                CREATE TABLE workout_modules_no_focus (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                    position INTEGER NOT NULL DEFAULT 0,
                    name     TEXT NOT NULL,
                    notes    TEXT
                );
                INSERT INTO workout_modules_no_focus (id, user_id, position, name, notes)
                    SELECT id, user_id, position, name, notes FROM workout_modules;
                DROP TABLE workout_modules;
                ALTER TABLE workout_modules_no_focus RENAME TO workout_modules;
            """)
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def _migrate_exercise_labels(db):
    """Widen the library exercise label CHECK to include 'cardio'.

    SQLite cannot alter a CHECK constraint, so the table is rebuilt in place
    with ids preserved (foreign keys are switched off during the swap).
    """
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'library_exercises'"
    ).fetchone()
    if row is None or "'cardio'" in (row["sql"] or ""):
        return

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.executescript("""
            CREATE TABLE library_exercises_new (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                position INTEGER NOT NULL DEFAULT 0,
                name     TEXT NOT NULL,
                muscles  TEXT,
                label    TEXT CHECK (label IN ('strength', 'skill', 'cardio')),
                notes    TEXT
            );
            INSERT INTO library_exercises_new (id, user_id, position, name, muscles, label, notes)
                SELECT id, user_id, position, name, muscles, label, notes FROM library_exercises;
            DROP TABLE library_exercises;
            ALTER TABLE library_exercises_new RENAME TO library_exercises;
        """)
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def _migrate_goal_cardio(db):
    """Widen the goals CHECKs to allow cardio goals and distance/time units."""
    row = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'goals'"
    ).fetchone()
    if row is None:
        return
    sql = row["sql"] or ""
    if "'cardio'" in sql and "'km/min'" in sql:
        return

    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.executescript("""
            CREATE TABLE goals_new (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
                goal_type    TEXT NOT NULL CHECK (goal_type IN ('body', 'skill', 'strength', 'cardio')),
                category     TEXT NOT NULL,
                target_value TEXT NOT NULL,
                unit         TEXT NOT NULL CHECK (unit IN ('kg', '%', 'seconds', 'reps', 'levels', 'meters', 'kilometers', 'km/min', 'minutes')),
                start_value  TEXT,
                target_date  TEXT,
                status       TEXT NOT NULL DEFAULT 'active'
                             CHECK (status IN ('active', 'achieved', 'abandoned')),
                notes        TEXT,
                created_at   TEXT NOT NULL DEFAULT (datetime('now'))
            );
            INSERT INTO goals_new (id, user_id, goal_type, category, target_value, unit,
                                   start_value, target_date, status, notes, created_at)
                SELECT id, user_id, goal_type, category, target_value, unit,
                       start_value, target_date, status, notes, created_at FROM goals;
            DROP TABLE goals;
            ALTER TABLE goals_new RENAME TO goals;
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
    _migrate_library_shared(db)
    _migrate_drop_sport_type(db)
    _migrate_unified_library(db)
    _migrate_drop_legacy(db)
    _migrate_exercise_labels(db)
    _migrate_goal_cardio(db)
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
