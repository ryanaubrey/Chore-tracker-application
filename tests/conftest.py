from datetime import date
import json
from http.cookiejar import CookieJar
from threading import Thread
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

import pytest
from werkzeug.serving import make_server

from backend import create_app
from backend.services import chores


SETUP_KEY = "synthetic-owner-setup-key"
PASSWORD = "synthetic-test-password"


class Client:
    def __init__(self, url):
        self.url = url
        self.cookies = CookieJar()
        self.opener = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, path, data=None):
        body = None if data is None else json.dumps(data).encode()
        headers = {} if body is None else {"Content-Type": "application/json", "X-Chores-Request": "1"}
        request = Request(self.url + path, data=body, headers=headers)
        try:
            response = self.opener.open(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.code, json.load(response), response.headers

    def ok(self, path, data=None):
        status, payload, _ = self.request(path, data)
        assert status == 200, payload
        return payload

    def board(self, day="2026-01-01"):
        return self.ok("/api/board?day=" + day)


def account(username, **fields):
    return {"username": username, "password": PASSWORD, **fields}


@pytest.fixture
def flask_app(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(chores, "today", lambda: date(2026, 1, 1))
    return create_app({
        "CHORES_DB": tmp_path / "test.sqlite3",
        "CHORES_SETUP_KEY": SETUP_KEY,
        "CHORES_PUBLIC_URL": "",
    })


@pytest.fixture
def app_context(flask_app):
    with flask_app.app_context():
        yield


@pytest.fixture
def clients(flask_app):
    with make_server("127.0.0.1", 0, flask_app, threaded=True) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.02})
        thread.start()
        try:
            yield lambda: Client(f"http://127.0.0.1:{server.server_port}")
        finally:
            server.shutdown()
            thread.join(timeout=10)


@pytest.fixture
def owner(clients):
    client = clients()
    client.ok("/api/setup", account("owner", name="Test Owner", key=SETUP_KEY))
    return client


@pytest.fixture
def join(clients, owner):
    def register(username):
        client = clients()
        client.ok("/api/signup", account(
            username, name=username.title(), key=owner.board()["invite"]
        ))
        return client

    return register


@pytest.fixture
def create_chore(owner):
    def create(**fields):
        chore = {
            "title": "Test chore",
            "details": "Synthetic instructions",
            "frequency": "once",
            "start": "2026-01-01",
            "weekday": 0,
            "assignee": None,
            **fields,
        }
        assert owner.ok("/api/save", chore) == {}
        return next(row for row in owner.board()["chores"] if row["title"] == chore["title"])

    return create
