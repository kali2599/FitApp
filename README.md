# FitApp

A Flask web app for managing your personal fitness life: **workouts, diets, goals and body statistics**.

## Features

- **Login / signup** with hashed passwords (Werkzeug) and session-based auth
- **Dashboard** (`/`) — summary cards, weight & body-fat trend, weekly training volume,
  daily calories & macros, active goals with progress bars, recent activity
- **Personal page** (`/profile`) — editable profile (username, email, height, birth date,
  sex, password), lifetime totals, latest measurements, personal records
- **Workouts** (`/workouts`) — build multi-day **strength**, **cardio** or **hybrid**
  training programs. Each day holds standalone exercises and/or **mini-circuits**
  (2+ exercises back-to-back, no rest between them, rest after each round).
  Strength entries track sets, reps and weight *or* duration; cardio entries are
  `run` / `swimming` / `spinning` with duration and optional distance. Log performed
  **sessions** ("Log this day") and later edit your actual reps/weight/time in
  `/workouts/sessions`
- **Diet** (`/diets`) — create / edit / delete meal entries with calories and macros
- **Goals** (`/goals`) — performance and body goals with automatic progress tracking
  (body goals use your latest measurement, performance goals your best matching exercise)
- **Body stats** (`/stats`) — weight, body fat and measurements over time

All data is private per user and stored in a local SQLite database
(`instance/fitapp.db`, auto-created on first run).

## Setup

> The system Python here has no `pip`/`ensurepip`, so the venv is created without pip
> and pip is bootstrapped afterwards.

```bash
# 1. virtual environment
python3 -m venv --without-pip .venv
source .venv/bin/activate

# 2. bootstrap pip inside the venv
curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
python /tmp/get-pip.py

# 3. install dependencies
pip install -r requirements.txt
```

## Run

```bash
source .venv/bin/activate
python run.py
```

Open http://127.0.0.1:5000 — sign up, then start logging workouts, meals, goals and
body statistics.

## Project layout

```
run.py                  entry point
requirements.txt
fitapp/
  __init__.py           app factory
  db.py                 SQLite schema + helpers (flask init-db)
  auth.py               signup / login / logout, login_required
  progress.py           current value of a goal
  utils.py              form parsing helpers, goal progress math
  routes/               blueprints: dashboard, profile, workouts, diets, goals, stats
  templates/            Jinja2 templates (Bootstrap 5)
  static/               custom CSS / JS
  instance/fitapp.db    database file (created automatically)
```

## Useful commands

```bash
flask --app run init-db    # (re)create the schema
deactivate                 # leave the venv
```
