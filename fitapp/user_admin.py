"""Core user-administration operations used by the standalone CLI (`user.py`).

Each function takes a database connection (already inside an app context) and
returns ``(ok, messages)``.
"""

import re
from werkzeug.security import generate_password_hash

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def create_user(db, name, email, password, admin=False):
    """Create a user (role 'user', or 'admin' when admin=True)."""
    name = name.strip()
    email = email.strip().lower()
    messages = []
    if len(name) < 3:
        messages.append("Username must be at least 3 characters.")
    if not EMAIL_RE.match(email):
        messages.append("Enter a valid email address.")
    if len(password) < 6:
        messages.append("Password must be at least 6 characters.")

    if not messages:
        if db.execute("SELECT id FROM users WHERE username = ?", (name,)).fetchone():
            messages.append("Username is already taken.")
        elif db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            messages.append("Email is already registered.")

    if messages:
        return False, messages

    role = "admin" if admin else "user"
    db.execute(
        "INSERT INTO users (username, email, password_hash, role) VALUES (?, ?, ?, ?)",
        (name, email, generate_password_hash(password), role),
    )
    db.commit()
    return True, [f"User '{name}' created ({role})."]


def delete_user(db, email):
    """Delete any user (normal or admin) and all their data."""
    email = email.strip().lower()
    user = db.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    if user is None:
        return False, [f"No user with email '{email}'."]
    cursor = db.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    db.commit()
    if not cursor.rowcount:
        return False, ["No user was deleted."]
    return True, [f"User '{user['username']}' deleted."]


def reset_password(db, email, password):
    """Reset the password for any user (normal or admin)."""
    email = email.strip().lower()
    if len(password) < 6:
        return False, ["Password must be at least 6 characters."]
    user = db.execute(
        "SELECT * FROM users WHERE email = ?", (email,)
    ).fetchone()
    if user is None:
        return False, [f"No user with email '{email}'."]
    db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(password), user["id"]),
    )
    db.commit()
    return True, [f"Password reset for '{user['username']}'."]