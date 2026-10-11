#!/usr/bin/env python3
"""Standalone user-administration script.

Run from the project root (inside the venv), e.g.:

    ./.venv/bin/python user.py create --name Alice --email alice@example.com --password hunter2
    ./.venv/bin/python user.py create --name Boss --email boss@example.com --password adminpw1 --admin
    ./.venv/bin/python user.py delete --email alice@example.com
    ./.venv/bin/python user.py reset --email alice@example.com --password newpass1
"""

import argparse
import os
import sys

from fitapp import create_app
from fitapp.user_admin import create_user, delete_user, reset_password


def main(argv=None):
    parser = argparse.ArgumentParser(description="FitApp user administration")
    parser.add_argument(
        "--database", default=None,
        help="SQLite database path (defaults to the app's instance DB).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create_p = sub.add_parser("create", help="Create a user (admin with --admin).")
    create_p.add_argument("--name", required=True, help="Username.")
    create_p.add_argument("--email", required=True, help="Email.")
    create_p.add_argument("--password", required=True, help="Password.")
    create_p.add_argument("--admin", action="store_true", help="Give the admin role.")

    delete_p = sub.add_parser("delete", help="Delete any user and their data.")
    delete_p.add_argument("--email", required=True, help="Email of the user.")

    reset_p = sub.add_parser("reset", help="Reset any user's password.")
    reset_p.add_argument("--email", required=True, help="Email of the user.")
    reset_p.add_argument("--password", required=True, help="New password.")

    args = parser.parse_args(argv)

    overrides = {}
    if args.database:
        overrides["DATABASE"] = args.database
    app = create_app(overrides)

    with app.app_context():
        from fitapp.db import get_db

        db = get_db()
        if args.command == "create":
            ok, messages = create_user(db, args.name, args.email, args.password, args.admin)
        elif args.command == "delete":
            ok, messages = delete_user(db, args.email)
        else:
            ok, messages = reset_password(db, args.email, args.password)

    for message in messages:
        print(message)
    if not ok:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())