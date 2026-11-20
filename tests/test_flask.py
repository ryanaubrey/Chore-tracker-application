import pytest

from backend import create_app


def test_frontend_assets_are_served_from_same_origin(flask_app):
    client = flask_app.test_client()
    for url, mime in (("/", "text/html"), ("/style.css", "text/css"),
                      ("/app.js", "text/javascript"), ("/api.js", "text/javascript")):
        response = client.get(url)
        assert response.status_code == 200
        assert response.mimetype == mime
        assert response.headers["Cache-Control"] == "no-store"
    assert b'type="module" src="/app.js"' in client.get("/").data
    assert b'from "./api.js"' in client.get("/app.js").data


@pytest.mark.parametrize(
    ("body", "content_type", "status", "message"),
    [
        (b"{}", "text/plain", 415, "Expected JSON."),
        (b"", "application/json", 400, "Invalid request size."),
        (b"x" * 16385, "application/json", 400, "Invalid request size."),
        (b"{", "application/json", 400, "Invalid request."),
        (b"[]", "application/json", 400, "Invalid request."),
    ],
)
def test_json_request_validation(flask_app, body, content_type, status, message):
    response = flask_app.test_client().post("/api/setup", data=body, content_type=content_type)
    assert response.status_code == status
    assert response.get_json() == {"error": message}


def test_hosted_configuration_ignores_flask_debug(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("FLASK_DEBUG", "1")
    monkeypatch.setenv("CHORES_PUBLIC_URL", "https://chore-tests.invalid")
    monkeypatch.setenv("CHORES_SETUP_KEY", "synthetic-key")
    monkeypatch.setenv("CHORES_DB", str(tmp_path / "hosted.sqlite3"))
    app = create_app()
    assert app.debug is False
    assert app.config["CHORES_DB"] == tmp_path / "hosted.sqlite3"


def test_health_is_available_without_authentication(flask_app):
    flask_app.config["CHORES_PUBLIC_URL"] = "https://chore-tests.invalid"
    client = flask_app.test_client()
    response = client.get("/healthz", base_url="http://chore-tests.invalid")
    assert response.status_code == 200
    assert response.json == {"status": "ok"}
    assert client.get("/api/board", base_url="http://chore-tests.invalid").status_code == 400


def test_health_hides_database_failures(flask_app, monkeypatch):
    from sqlalchemy.exc import OperationalError
    from backend import routes

    def unavailable():
        raise OperationalError("internal database statement", None, RuntimeError())

    monkeypatch.setattr(routes, "connect", unavailable)
    response = flask_app.test_client().get("/healthz")
    assert response.status_code == 503
    assert response.json == {"status": "unavailable"}


def test_container_requires_database_under_data_mount(tmp_path, monkeypatch):
    from backend.config import require_container_storage
    from sqlalchemy.engine import URL

    monkeypatch.setenv("CHORES_REQUIRE_DATA_MOUNT", "1")
    with pytest.raises(ValueError, match="persistent volume"):
        require_container_storage(URL.create("sqlite", database=str(tmp_path / "ephemeral.sqlite3")))


def test_azure_container_apps_refuses_sqlite(monkeypatch):
    from backend.config import require_container_storage
    from sqlalchemy.engine import URL

    monkeypatch.setenv("CONTAINER_APP_NAME", "chores-test")
    with pytest.raises(ValueError, match="external database"):
        require_container_storage(URL.create("sqlite", database="/data/chores.sqlite3"))
