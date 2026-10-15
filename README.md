# FitApp

A Flask web app for managing your personal fitness life: **sports, diet, goals and body statistics**.

## Features

FitApp keeps your whole fitness life in one place — plan your training, track what
you eat, chase your goals, and watch your body change.

- **Plan your training** — create sports (e.g. *calisthenics*, *climbing*), each with
  reusable workouts and days. Maintain a personal **library** of exercises and
  mini-circuits, plus **modules** (ordered combinations of the two). Build a day from
  the library: drop in a module, a mini-circuit or a single exercise, then set the
  prescriptions (sets, reps, weight, duration, distance, rest — `max` allowed) that
  apply to that day only. Reuse a module across days and sports; edit it once and
  every dependent day re-syncs.
- **Track your diet** — log meals with calories and macros and see your daily totals.
- **Set goals, watch progress** — body, skill and strength goals with automatic
  progress tracking and a simple way to log each step.
- **Understand your body** — record weight, body fat and measurements over time and
  get a personal report: BMI, BMR, TDEE, calorie & macro targets, and tailored diet,
  training and recovery tips.
- **Your dashboard** — weight and body-fat trends, today's macros, active goals and
  recent activity at a glance.
- **Private by default** — secure login, with your data stored locally and separated
  per user.
- **Admin tools** — user management for administrators.

All data is private per user and stored in a local SQLite database
(`instance/fitapp.db`, auto-created on first run).

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
workouts and days, logging meals and goals, and recording body statistics.

## Configuration

- `FITAPP_SECRET_KEY` — Flask session secret. Defaults to `dev-secret-change-me`,
  so set a real value in any deployment.
- `DATABASE` — SQLite path, defaulting to `instance/fitapp.db`. Also overridable
  per call via `create_app({"DATABASE": ...})` and, for the user CLI, `user.py --database`.

The schema is created and migrated automatically when the app starts
(`create_app()` → `db.init_db()`), so a fresh database needs no setup step.

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
builder flow and its per-day prescriptions, admin (no exercise catalog), the
legacy → unified library migration, and a render check over every top-level page.

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
