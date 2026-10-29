# FitApp

A Flask web app for managing your personal fitness life: **sports, diet, goals and body statistics**.

## Features

FitApp keeps your fitness planning in one place — plan your training, record your diet,
set goals, and track body measurements over time.

- **Plan your training** — create sports (e.g. *calisthenics*, *climbing*), each with
  reusable workouts and days. Maintain a personal **library** of exercises and
  mini-circuits, plus **modules** (ordered combinations of the two). Build a day from
  the library: drop in a module, a mini-circuit or a single exercise, then set the
  prescriptions (sets, reps, weight, duration, distance, rest, notes — `max` allowed) that
  apply to that day only. Cardio-labelled exercises use their own attribute set:
  distance (m), time (s or min), pace (km/min), rounds and rest (s). Reuse a module
  across days and sports; edit it once and every dependent day re-syncs.
- **Record your diet** — save named diet plans with guidance, optional daily calorie and macro targets, and an optional daily meal distribution. Pick foods from the bundled CSV library and FitApp calculates the calories and macros for each quantity. Calories can also be calculated from daily macro targets and checked against the 4/4/9 estimate. FitApp does not log meals or food intake.
- **Set goals, watch progress** — body, skill, strength and cardio goals on one page,
  with automatic progress tracking and a simple way to log each step. Cardio is a goal
  type with five attributes — distance (m), time (s or min), pace (km/min), rounds and
  rest (s) — each carrying its own unit, with progress tracked on distance logged
  manually.
- **Understand your body** — record weight, body fat and measurements over time and
  get a personal report: BMI, estimated BMR/TDEE, calorie and macro starting points,
  and general training and recovery suggestions.
- **Your dashboard** — weight and body-fat trends, saved diet plans, active goals and
  recent activity at a glance.
- **Private by default** — secure login, with your data stored locally and separated
  per user.
- **Admin tools** — a separate role for administrators: manage users and
  application settings only.

All data is private per user and stored in a local SQLite database
(`instance/fitapp.db`, auto-created on first run).

## Roles

- **user** — the normal account: sports, library, diet, goals, body stats,
  dashboard and profile.
- **admin** — a management-only account. Admins get the **Admin** area
  (user management + application settings) and the **Profile** page, but *not*
  the personal sections: they are redirected away from the dashboard, sports,
  library, diet, goals and body stats. Admins can inspect a user's data from the
  admin area and reset a user's password, but cannot manage their own training
  or nutrition. Admin accounts are hidden from the user list.

Create an admin with the CLI: `./.venv/bin/python user.py create --admin ...`.

## Setup

Requires Python 3.9+ (Flask 3.1).

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> If your system Python ships without `pip`/`ensurepip`, create the venv with
> `python3 -m venv --without-pip .venv`, then bootstrap pip inside it:
> `curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py && python /tmp/get-pip.py`,
> and finally `pip install -r requirements.txt`.

## Run

```bash
source .venv/bin/activate
python run.py
```

Open http://127.0.0.1:5000 — sign up, then start building your library, defining sports,
workouts and days, recording diet plans and goals, and tracking body statistics.

## Configuration

- `FITAPP_SECRET_KEY` — stable Flask session secret. If unset, FitApp generates a
  random key at startup, which signs out users when the process restarts. Set a
  stable secret in any deployment and share it across app workers.
- `FITAPP_COOKIE_SECURE` — set to `1` when serving over HTTPS to mark session cookies
  secure. It defaults to `0` for local HTTP development.
- `DATABASE` — SQLite path, defaulting to `instance/fitapp.db`. Also overridable
  per call via `create_app({"DATABASE": ...})` and, for the user CLI, `user.py --database`.

The schema is created and migrated automatically when the app starts
(`create_app()` → `db.init_db()`), so a fresh database needs no setup step.

### Food library

The starter catalog is `fitapp/data/foods.csv`. Each row describes the values per
100 g and must use the columns `food,calories,protein,carbs,fat` in that order.
Add or edit rows in this file to customize the choices available in meal
distributions. Food names containing commas must be quoted according to CSV rules.

## Project layout

```
run.py                  entry point
user.py                 CLI: create / delete users, reset passwords
requirements.txt
fitapp/
  __init__.py           app factory
  db.py                 SQLite schema, migrations + helpers (flask init-db)
  auth.py               signup / login / logout, login_required
  user_admin.py         user create / delete / reset helpers used by user.py
  progress.py           current value of a goal
  insights.py           BMI / BMR / TDEE / calorie & macro targets + suggestions
  utils.py              form parsing helpers, goal progress math
  routes/               blueprints: dashboard, profile, sports, library, diets, goals, stats, admin
  templates/            Jinja2 templates (Bootstrap 5)
  static/               custom CSS
  instance/fitapp.db    database file (created automatically)
tests/                  pytest suite (see "Tests")
```

## Tests

The suite runs against throw-away databases in `tmp_path` — it never touches
`instance/fitapp.db`.

```bash
pip install -r requirements-dev.txt
pytest              # everything
pytest -q           # quiet
pytest tests/test_sports.py -k prescriptions
```

Coverage: the library CRUD and per-user isolation, the sport → workout → day →
builder flow and its per-day prescriptions (including notes and distance), the
goal forms (standard and cardio), the lifestyle profile, admin (no exercise
catalog), the legacy → unified library migration, the schema reconciliation
(a migrated database ends up identical to a fresh one), and a render check over
every top-level page.

## The schema is the source of truth

`SCHEMA` in `fitapp/db.py` is the only description of the database. Migrations
exist to carry an old database forward, but the last step of every start-up is
`_sync_schema()`: it compares the live tables with the native ones and rebuilds
the ones that drifted, so a database created by an older version ends up
exactly like a fresh one — same columns, same constraints, same indexes. Rows
are copied one at a time, so a row the current schema no longer allows is
skipped (and logged) instead of blocking the start-up. Tables the schema does
not know about are removed while they are still empty.

## Useful commands

```bash
flask --app run init-db    # apply the schema + migrations now (also run on each startup)
./.venv/bin/python user.py create --name Alice --email alice@example.com --password hunter2
./.venv/bin/python user.py create --name Boss --email boss@example.com --password adminpw1 --admin
./.venv/bin/python user.py reset --email alice@example.com --password newpass1   # any user
./.venv/bin/python user.py delete --email alice@example.com                      # any user
./.venv/bin/python user.py --database instance/fitapp.db reset --email a@b.com --password newpass1  # custom DB
deactivate                 # leave the venv
```
