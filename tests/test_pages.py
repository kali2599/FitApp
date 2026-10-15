"""The app boots and renders every top-level page without errors."""
from helpers import make_user

PAGES = ["/", "/sports/", "/library/", "/diets/", "/goals/", "/stats/", "/profile/"]


def test_all_pages_render(client, db):
    make_user(client, "tester")
    for path in PAGES:
        r = client.get(path)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert "Traceback" not in r.get_data(as_text=True), path


def test_no_gym_language(client, db):
    make_user(client, "tester")
    body = "".join(client.get(p).get_data(as_text=True) for p in ("/sports/", "/library/"))
    assert "gym" not in body.lower()


def test_login_required_redirects(client, db):
    for path in PAGES:
        r = client.get(path)
        assert r.status_code == 302, path


def test_regular_user_cannot_reach_admin(client, db):
    make_user(client, "tester")
    for path in ["/admin/", "/admin/users/1"]:
        r = client.get(path)
        assert r.status_code == 302, path
