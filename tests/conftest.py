import sqlite3

import pytest

from fitapp import create_app


@pytest.fixture()
def db_path(tmp_path):
    return str(tmp_path / "test.db")


@pytest.fixture()
def app(db_path):
    return create_app({"DATABASE": db_path, "TESTING": True, "SECRET_KEY": "test"})


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    yield con
    con.close()
