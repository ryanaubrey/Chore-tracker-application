import hashlib
import time

import pytest

from backend.database import accounts, write_transaction
from backend.services import invitations

from conftest import PASSWORD, SETUP_KEY, account


HEADERS = {"X-Chores-Request": "1"}


def signed_in(flask_app):
    client = flask_app.test_client()
    response = client.post("/api/setup", headers=HEADERS,
                           json=account("owner", key=SETUP_KEY, name="Owner"))
    assert response.status_code == 200, response.json
    return client


@pytest.mark.parametrize("headers", [
    {},
    {"X-Chores-Request": "1", "Origin": "https://unrelated.invalid"},
    {"X-Chores-Request": "1", "Origin": "null"},
    {"X-Chores-Request": "1", "Sec-Fetch-Site": "same-site"},
])
def test_csrf_rejects_posts_without_revoking_session(flask_app, headers):
    client = signed_in(flask_app)
    assert client.post("/api/logout", json={}, headers=headers).status_code == 403
    assert client.get("/api/board").json["user"]["role"] == "owner"
    assert client.post("/api/logout", json={}, headers=HEADERS).status_code == 200


def test_same_origin_browser_post(flask_app):
    client = signed_in(flask_app)
    headers = dict(HEADERS, Origin="http://localhost")
    assert client.post("/api/logout", json={}, headers=headers).status_code == 200


@pytest.mark.parametrize("body", [
    b'{"username":"one","username":"two"}',
    b'{"bad":NaN}',
    b'{"bad":"\xff"}',
    b'{"username":"a\\u0000b","password":"test-password"}',
])
def test_invalid_api_values_return_json(flask_app, body):
    response = flask_app.test_client().post(
        "/api/login", data=body, content_type="application/json", headers=HEADERS)
    assert response.status_code == 400
    assert "error" in response.json


def test_legacy_password_upgrades_without_invalidating_other_session(flask_app, app_context):
    owner = signed_in(flask_app)
    salt = bytes(16)
    legacy = salt.hex() + ":" + hashlib.scrypt(
        PASSWORD.encode(), salt=salt, n=16384, r=8, p=1,
    ).hex()
    with write_transaction() as db:
        accounts.update_password(db, 1, legacy)
    another = flask_app.test_client()
    assert another.post("/api/login", json=account("owner"), headers=HEADERS).status_code == 200
    with write_transaction() as db:
        assert accounts.find_user(db, "owner")["password"].startswith("scrypt:131072:8:1$")
    assert owner.get("/api/board").json["user"]["id"] == 1


def test_expired_invitation_rejected_and_rotation_reopens_signup(flask_app, app_context):
    owner = signed_in(flask_app)
    before = owner.get("/api/board").json["invite"]
    with write_transaction() as db:
        accounts.set_invite_expiry(db, str(int(time.time()) - 1))
    assert owner.get("/api/board").json["invite_expired"] is True
    guest = flask_app.test_client()
    payload = account("guest", key=before, name="Guest")
    assert guest.post("/api/signup", json=payload, headers=HEADERS).status_code == 403
    assert owner.post("/api/renew-invite", json={}, headers=HEADERS).status_code == 200
    board = owner.get("/api/board").json
    assert board["invite_expired"] is False and board["invite"] != before
    assert guest.post("/api/signup", json=payload, headers=HEADERS).status_code == 403
    payload["key"] = board["invite"]
    assert guest.post("/api/signup", json=payload, headers=HEADERS).status_code == 200


def test_active_legacy_invite_gets_one_grace_period(flask_app, app_context, monkeypatch):
    owner = signed_in(flask_app)
    invite = owner.get("/api/board").json["invite"]
    with write_transaction() as db:
        db.exec_driver_sql("DELETE FROM settings WHERE key='invite_expires'")
    monkeypatch.setattr(invitations.time, "time", lambda: 1000)
    with write_transaction() as db:
        invitations.initialize_setup(db, None, False)
        assert accounts.get_setting(db, "invite") == invite
        assert accounts.get_setting(db, "invite_expires") == str(1000 + invitations.INVITE_AGE)
    monkeypatch.setattr(invitations.time, "time", lambda: 2000)
    with write_transaction() as db:
        invitations.initialize_setup(db, None, False)
        assert accounts.get_setting(db, "invite_expires") == str(1000 + invitations.INVITE_AGE)


def test_member_cannot_reassign_claimed_occurrence_with_valid_csrf(owner, join, create_chore):
    member = join("member")
    chore = create_chore()
    target = {"id": chore["id"], "day": chore["start"]}
    member.ok("/api/claim", target)
    assert member.request("/api/assign", {**target, "assignee": None})[0] == 403
    entry = next(item for item in owner.board()["items"] if item["id"] == chore["id"])
    assert entry["assignee"] == member.board()["user"]["id"]


def test_internal_error_does_not_expose_details(flask_app, monkeypatch, caplog):
    from backend.services import chores

    def fail():
        raise RuntimeError("sensitive database detail")

    monkeypatch.setattr(chores, "today", fail)
    response = flask_app.test_client().get("/api/board")
    assert response.status_code == 500
    assert response.json == {"error": "Something went wrong."}
    assert "sensitive database detail" not in caplog.text


def test_hosted_https_does_not_trust_raw_forwarded_headers(flask_app):
    flask_app.config["CHORES_PUBLIC_URL"] = "https://chore-tests.invalid"
    client = flask_app.test_client()
    response = client.get("/api/board", base_url="http://chore-tests.invalid",
                          headers={"X-Forwarded-Proto": "https"})
    assert response.status_code == 400
    assert "Strict-Transport-Security" not in response.headers
    response = client.get("/api/board", base_url="https://chore-tests.invalid")
    assert response.status_code == 200
    assert response.headers["Strict-Transport-Security"] == "max-age=31536000"
