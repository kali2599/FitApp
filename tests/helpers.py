import sqlite3


def db_file(client):
    return client.application.config["DATABASE"]


def make_user(client, username, password="secret1"):
    """Sign up and log in a user on the given test client."""
    email = f"{username}@example.com"
    r = client.post(
        "/signup",
        data={"username": username, "email": email, "password": password, "confirm": password},
    )
    assert r.status_code in (302, 200), f"signup failed: {r.status_code}"
    r = client.post("/login", data={"username": username, "password": password})
    assert r.status_code == 302, f"login failed: {r.status_code}"
    return client


def make_admin(client, username, password="secret1"):
    make_user(client, username, password)
    con = sqlite3.connect(db_file(client))
    con.execute("UPDATE users SET role = 'admin' WHERE username = ?", (username,))
    con.commit()
    con.close()
    return client


def logout(client):
    return client.post("/logout")


def scalar(db, sql, *params):
    row = db.execute(sql, params).fetchone()
    return row[0] if row is not None else None


def rows(db, sql, *params):
    return db.execute(sql, params).fetchall()
