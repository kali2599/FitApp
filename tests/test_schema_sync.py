"""The native schema is the source of truth: the live database must match it.

A database created by an older version of the app keeps whatever shape the
migrations left behind, because CREATE TABLE IF NOT EXISTS cannot change a
table that already exists. _sync_schema() repairs that drift, and these
tests pin the behaviour down.
"""
import sqlite3

from fitapp import create_app
from fitapp.db import _normalize_ddl

from test_migration import LEGACY_SQL, LEGACY_DATA


def _fingerprint(path):
    """Every table and index of a database, normalized so only the shape counts."""
    con = sqlite3.connect(path)
    rows = con.execute(
        "SELECT type, name, sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    con.close()
    return sorted((t, n, _normalize_ddl(s)) for t, n, s in rows)


def _tables(path):
    con = sqlite3.connect(path)
    names = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    )}
    con.close()
    return names


def _columns(path, table):
    con = sqlite3.connect(path)
    cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    con.close()
    return cols


def _ddl(path, table):
    con = sqlite3.connect(path)
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name = ?", (table,)
    ).fetchone()
    con.close()
    return row[0] if row else None


def _rows(path, table):
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute(f"SELECT * FROM {table} ORDER BY id")]
    con.close()
    return rows


def _init(app, path):
    with app.app_context():
        from fitapp import db as fitdb
        fitdb.init_db()


def test_native_schema_has_no_dead_values(tmp_path):
    """The schema only allows what the app can actually produce and read."""
    path = str(tmp_path / "native.db")
    create_app({"DATABASE": path, "TESTING": True})

    goals = _ddl(path, "goals")
    assert "'levels'" not in goals
    assert "'kg'" in goals and "'seconds'" in goals and "'reps'" in goals

    # audit columns nothing ever reads are gone
    assert "updated_at" not in _columns(path, "user_lifestyle")
    assert "created_at" not in _columns(path, "goal_logs")
    assert "created_at" not in _columns(path, "cardio_goal_logs")


def test_migrated_db_is_identical_to_a_native_db(tmp_path):
    """A database that came through the migrations ends up exactly like a fresh one.

    This is the invariant that makes "the schema works by its native
    implementation" true, whatever the database's history is.
    """
    legacy = str(tmp_path / "legacy.db")
    con = sqlite3.connect(legacy)
    con.executescript(LEGACY_SQL)
    con.executescript(LEGACY_DATA)
    con.commit()
    con.close()

    create_app({"DATABASE": legacy, "TESTING": True})

    native = str(tmp_path / "native.db")
    create_app({"DATABASE": native, "TESTING": True})

    assert _fingerprint(legacy) == _fingerprint(native)


def test_sync_repairs_a_drifted_table(tmp_path):
    """A table that lost a constraint is rebuilt with its native definition."""
    path = str(tmp_path / "drift.db")
    app = create_app({"DATABASE": path, "TESTING": True})

    # rewrite users the way an old migration left it: the role column was
    # added with ALTER TABLE, which cannot carry a CHECK constraint
    con = sqlite3.connect(path)
    con.executescript("""
        PRAGMA foreign_keys = OFF;
        CREATE TABLE users_old (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT UNIQUE NOT NULL,
            email         TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            height_cm     REAL,
            birth_date    TEXT,
            sex           TEXT,
            created_at    TEXT NOT NULL DEFAULT (datetime('now')),
            role          TEXT NOT NULL DEFAULT 'user');
        INSERT INTO users_old SELECT id, username, email, password_hash, height_cm,
                               birth_date, sex, created_at, role FROM users;
        DROP TABLE users;
        ALTER TABLE users_old RENAME TO users;
    """)
    con.execute(
        "INSERT INTO users (id, username, email, password_hash, role) "
        "VALUES (7, 'boss', 'boss@e.com', 'x', 'admin')"
    )
    con.commit()
    con.close()

    assert "CHECK" not in (_ddl(path, "users") or "")

    _init(app, path)

    ddl = _ddl(path, "users")
    assert "CHECK (role IN ('user', 'admin'))" in ddl
    # the row and its id survived the rebuild
    row = con = sqlite3.connect(path)
    row.row_factory = sqlite3.Row
    user = dict(row.execute("SELECT * FROM users WHERE id = 7").fetchone())
    row.close()
    assert user["username"] == "boss"
    assert user["role"] == "admin"


def test_sync_preserves_ids_and_row_counts(tmp_path):
    """Rebuilding a table keeps every row, its id and its autoincrement counter."""
    path = str(tmp_path / "rows.db")
    app = create_app({"DATABASE": path, "TESTING": True})
    _init(app, path)

    con = sqlite3.connect(path)
    con.executescript("""
        INSERT INTO users (username, email, password_hash, role) VALUES ('a', 'a@e.com', 'x', 'user');
        INSERT INTO sports (user_id, name) VALUES (1, 'Calisthenics');
        INSERT INTO workouts (sport_id, name) VALUES (1, 'Week 1');
        INSERT INTO workout_days (workout_id, name) VALUES (1, 'Push');
        INSERT INTO library_exercises (user_id, name, label) VALUES (1, 'Push-up', 'strength');
    """)
    con.commit()
    con.close()

    before = {t: _rows(path, t) for t in ("users", "sports", "workouts", "workout_days",
                                          "library_exercises")}

    # make every table drift, then let the sync repair it
    con = sqlite3.connect(path)
    con.executescript("""
        PRAGMA foreign_keys = OFF;
        CREATE TABLE users_old (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, height_cm REAL, birth_date TEXT,
            sex TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')), role TEXT NOT NULL DEFAULT 'user');
        INSERT INTO users_old SELECT id, username, email, password_hash, height_cm, birth_date,
                               sex, created_at, role FROM users;
        DROP TABLE users;
        ALTER TABLE users_old RENAME TO users;
    """)
    con.commit()
    con.close()

    _init(app, path)

    for table, rows in before.items():
        assert _rows(path, table) == rows, table

    con = sqlite3.connect(path)
    con.execute("INSERT INTO users (username, email, password_hash) VALUES ('b', 'b@e.com', 'x')")
    new_id = con.execute("SELECT id FROM users WHERE username = 'b'").fetchone()[0]
    con.close()
    assert new_id == 2  # the autoincrement counter survived the rebuild


def test_sync_drops_an_unknown_empty_table_and_keeps_a_populated_one(tmp_path):
    """Tables the schema does not know about are removed while they are empty."""
    path = str(tmp_path / "unknown.db")
    app = create_app({"DATABASE": path, "TESTING": True})
    _init(app, path)

    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE scratch (id INTEGER PRIMARY KEY, note TEXT);
        CREATE TABLE archive (id INTEGER PRIMARY KEY, note TEXT);
        INSERT INTO archive (note) VALUES ('keep me');
    """)
    con.commit()
    con.close()

    _init(app, path)

    assert "scratch" not in _tables(path)
    assert "archive" in _tables(path)
    con = sqlite3.connect(path)
    assert con.execute("SELECT note FROM archive").fetchone()[0] == "keep me"
    con.close()


def test_sync_skips_a_row_that_violates_a_new_check(tmp_path):
    """A row the native schema can no longer hold is skipped, not fatal."""
    path = str(tmp_path / "levels.db")
    app = create_app({"DATABASE": path, "TESTING": True})
    _init(app, path)

    # rebuild goals with the old unit list and add a goal the schema rejects
    con = sqlite3.connect(path)
    con.executescript("""
        PRAGMA foreign_keys = OFF;
        CREATE TABLE goals_old (
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
            created_at   TEXT NOT NULL DEFAULT (datetime('now')));
        INSERT INTO users (username, email, password_hash) VALUES ('a', 'a@e.com', 'x');
        INSERT INTO goals_old (user_id, goal_type, category, target_value, unit)
            VALUES (1, 'skill', 'Planche', '3', 'levels');
        DROP TABLE goals;
        ALTER TABLE goals_old RENAME TO goals;
    """)
    con.commit()
    con.close()

    # the app still starts, and the goals table now follows the native schema
    _init(app, path)

    assert "'levels'" not in _ddl(path, "goals")
    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM goals").fetchone()[0] == 0
    con.close()


def test_sync_is_idempotent(tmp_path):
    """Running the sync twice changes nothing the second time."""
    path = str(tmp_path / "twice.db")
    app = create_app({"DATABASE": path, "TESTING": True})
    _init(app, path)
    first = _fingerprint(path)
    _init(app, path)
    assert _fingerprint(path) == first


def test_fresh_db_needs_no_migration(tmp_path):
    """A brand new database is created by the schema alone."""
    path = str(tmp_path / "fresh.db")
    create_app({"DATABASE": path, "TESTING": True})
    con = sqlite3.connect(path)
    ddl = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='users'"
    ).fetchone()[0]
    con.close()
    assert "CHECK (role IN ('user', 'admin'))" in ddl
