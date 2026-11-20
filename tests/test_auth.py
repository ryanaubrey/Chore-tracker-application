from http.cookies import SimpleCookie

import pytest

from backend.database import connect
from backend.services.auth import token_hash

from conftest import PASSWORD, SETUP_KEY, account


def test_setup_creates_one_owner_and_consumes_key(clients):
    client = clients()
    assert client.board() == {"user": None, "today": "2026-01-01", "setup": True}
    assert client.request("/api/setup", account("owner", name="Owner", key="wrong"))[0] == 403
    client.ok("/api/setup", account("OWNER", name="Owner", key=SETUP_KEY))
    board = client.board()
    assert board["setup"] is False
    assert board["user"]["role"] == "owner"
    assert board["invite"]
    assert clients().request(
        "/api/setup", account("other", name="Other", key=SETUP_KEY)
    )[0] == 403


def test_signup_requires_current_invite_and_unique_username(owner, clients, join):
    old_invite = owner.board()["invite"]
    outsider = clients()
    assert outsider.request("/api/signup", account("guest", name="Guest", key="wrong"))[0] == 403
    member = join("member")
    assert member.board()["user"]["role"] == "member"
    assert "invite" not in member.board()
    assert "chores" not in member.board()
    assert outsider.request(
        "/api/signup", account("MEMBER", name="Duplicate", key=old_invite)
    )[0] == 409
    owner.ok("/api/renew-invite", {})
    assert owner.board()["invite"] != old_invite
    assert outsider.request(
        "/api/signup", account("guest", name="Guest", key=old_invite)
    )[0] == 403
    assert join("guest").board()["user"]["role"] == "member"


def test_login_replaces_session_and_logout_revokes_it(clients, owner, app_context):
    assert clients().request("/api/login", {"username": "owner", "password": "wrong-password"})[0] == 401
    old_token = next(iter(owner.cookies)).value
    status, payload, headers = owner.request("/api/login", account(" OWNER "))
    assert (status, payload) == (200, {})
    cookie = SimpleCookie(headers["Set-Cookie"])["chores_session"]
    assert cookie.value != old_token
    assert cookie["httponly"]
    assert cookie["samesite"] == "Lax"
    assert cookie["path"] == "/"
    assert int(cookie["max-age"]) == 14 * 24 * 60 * 60
    with connect() as db:
        tokens = db.exec_driver_sql("SELECT token FROM sessions").scalars().all()
        stored_password = db.exec_driver_sql("SELECT password FROM users").scalar_one()
    assert tokens == [token_hash(cookie.value)]
    assert stored_password != PASSWORD
    status, payload, headers = owner.request("/api/logout", {})
    assert (status, payload) == (200, {})
    assert SimpleCookie(headers["Set-Cookie"])["chores_session"]["max-age"] == "0"
    assert owner.board()["user"] is None
    assert owner.request("/api/logout", {})[0] == 401
    with connect() as db:
        assert db.exec_driver_sql("SELECT count(*) FROM sessions").fetchone()[0] == 0


def test_expired_session_cannot_access_board_or_mutate(owner, app_context):
    with connect() as db, db.begin():
        db.exec_driver_sql("UPDATE sessions SET expires = 0")
    assert owner.board()["user"] is None
    assert owner.request("/api/logout", {})[0] == 401


def test_hosted_mode_marks_cookie_secure(owner, flask_app):
    flask_app.config["CHORES_PUBLIC_URL"] = "https://chore-tests.invalid"
    response = flask_app.test_client().post(
        "/api/login", base_url="https://chore-tests.invalid", json=account("owner"),
        headers={"X-Chores-Request": "1"},
    )
    assert response.status_code == 200
    assert SimpleCookie(response.headers["Set-Cookie"])["chores_session"]["secure"]


@pytest.mark.parametrize("path", ["save", "delete", "assign", "claim", "complete", "role", "renew-invite"])
def test_anonymous_cannot_mutate(clients, owner, path):
    assert clients().request("/api/" + path, {})[0] == 401


def test_admin_can_rotate_invite_through_api(owner, join):
    admin = join("admin")
    owner.ok("/api/role", {"id": admin.board()["user"]["id"], "role": "admin"})
    old_invite = owner.board()["invite"]
    admin.ok("/api/renew-invite", {})
    assert owner.board()["invite"] != old_invite
