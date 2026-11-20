import os
from ipaddress import ip_address
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import URL, make_url


ROOT = Path(__file__).resolve().parents[1]


def database_url(path=None):
    explicit = os.environ.get("DATABASE_URL")
    if explicit:
        return make_url(explicit)
    return URL.create("sqlite", database=str(path or os.environ.get("CHORES_DB")
                                            or ROOT / "chores.sqlite3"))


def configure(app, config):
    app.config.from_mapping(
        DEBUG=False,
        CHORES_DB=Path(os.environ.get("CHORES_DB", ROOT / "chores.sqlite3")),
        DATABASE_URL=None,
        CHORES_TIMEZONE=os.environ.get("CHORES_TIMEZONE"),
        CHORES_PUBLIC_URL=os.environ.get("CHORES_PUBLIC_URL", "").rstrip("/"),
        CHORES_TRUSTED_PROXY=os.environ.get("CHORES_TRUSTED_PROXY", ""),
        CHORES_SETUP_KEY=os.environ.get("CHORES_SETUP_KEY"),
        CHORES_HOST=os.environ.get("CHORES_HOST", "127.0.0.1"),
        PORT=int(os.environ.get("PORT", "8000")),
    )
    if config:
        app.config.update(config)
    app.debug = False
    value = app.config["DATABASE_URL"]
    app.config["DATABASE_URL"] = make_url(value) if value else database_url(app.config["CHORES_DB"])

    url = app.config["CHORES_PUBLIC_URL"]
    if url:
        origin = urlsplit(url)
        if (origin.scheme != "https" or not origin.hostname or origin.username is not None
                or origin.path or origin.query or origin.fragment):
            raise ValueError("CHORES_PUBLIC_URL must be an HTTPS origin.")
        hostname = origin.hostname
        host = f"[{hostname}]" if ":" in hostname else hostname
        port = origin.port
        app.config["CHORES_PUBLIC_URL"] = f"https://{host}" + (f":{port}" if port not in (None, 443) else "")
        app.config["TRUSTED_HOSTS"] = [host]
    proxy = app.config["CHORES_TRUSTED_PROXY"]
    if proxy:
        app.config["CHORES_TRUSTED_PROXY"] = str(ip_address(proxy))
    if (url and app.config["DATABASE_URL"].get_backend_name() == "sqlite"
            and not Path(app.config["DATABASE_URL"].database or "").is_file()
            and not app.config["CHORES_SETUP_KEY"]):
        raise ValueError("Set CHORES_SETUP_KEY before the first hosted startup.")


def require_container_storage(database):
    if database.get_backend_name() == "mssql":
        return
    if os.environ.get("CONTAINER_APP_NAME") and database.get_backend_name() == "sqlite":
        raise ValueError("Azure Container Apps requires a supported external database.")
    if os.environ.get("CHORES_REQUIRE_DATA_MOUNT") != "1":
        return
    if database.get_backend_name() != "sqlite" or not database.database:
        raise ValueError("This container release requires SQLite on a mounted /data directory.")
    data = Path("/data").resolve()
    file = Path(database.database).resolve()
    # Linux mountinfo also detects bind mounts on the same filesystem.
    message = "Mount a persistent volume at /data and place the SQLite file there."
    if not file.is_relative_to(data) or file == data:
        raise ValueError(message)
    with Path("/proc/self/mountinfo").open() as mountinfo:
        if not any(line.split()[4] == str(data)
                   and line.partition(" - ")[2].split()[0] not in {"tmpfs", "ramfs"}
                   for line in mountinfo):
            raise ValueError(message)
