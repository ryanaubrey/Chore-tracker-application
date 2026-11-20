import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from backend import create_app
from backend.config import ROOT
from backend.database import write_transaction
from backend.database.chores import save_occurrence
from scripts.backup_sqlite import backup_database


def snapshot(filename):
    with closing(sqlite3.connect(filename)) as db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        return {
            table: db.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in ("users", "settings", "sessions", "chores", "occurrences")
        }


def test_legacy_baseline_preserves_rows_and_supports_rollback(tmp_path, monkeypatch):
    original = tmp_path / "old.sqlite3"
    with closing(sqlite3.connect(original)) as db, db:
        db.executescript(Path(__file__).with_name("legacy_schema.sql").read_text())
        db.executescript("""
            INSERT INTO users VALUES (9,'User','user','existing hash','owner');
            INSERT INTO settings VALUES ('invite','test invitation');
            INSERT INTO sessions VALUES ('test token',9,2000000000);
            INSERT INTO chores VALUES (7,'Bins','','daily','2026-01-01',3,9,0);
            INSERT INTO occurrences VALUES (7,'2026-01-01',9,1);
        """)
    backup, working = tmp_path / "backup.sqlite3", tmp_path / "working.sqlite3"
    backup_database(original, backup)
    backup_database(backup, working)
    expected = snapshot(backup)
    with pytest.raises(FileExistsError):
        backup_database(original, backup)
    url = URL.create("sqlite", database=str(working)).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("CHORES_DB", str(tmp_path / "unused.sqlite3"))
    config = Config(str(ROOT / "alembic.ini"))
    with pytest.raises(RuntimeError, match="Database needs migration"):
        create_app({"CHORES_PUBLIC_URL": ""})
    command.upgrade(config, "head")
    assert snapshot(working) == expected
    command.downgrade(config, "base")
    assert snapshot(working) == snapshot(original) == snapshot(backup) == expected
    command.upgrade(config, "head")
    create_app({"CHORES_PUBLIC_URL": ""})
    assert not (tmp_path / "unused.sqlite3").exists()


def test_incomplete_schema_is_not_stamped(tmp_path, monkeypatch):
    database = tmp_path / "incomplete.sqlite3"
    with closing(sqlite3.connect(database)) as db, db:
        db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY)")
    backup_database(database, tmp_path / "incomplete-backup.sqlite3")
    monkeypatch.setenv("DATABASE_URL", URL.create("sqlite", database=str(database)).render_as_string())
    with pytest.raises(RuntimeError, match="unexpected or incomplete"):
        command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
    with closing(sqlite3.connect(database)) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [("users",)]


def test_occurrence_key_rejects_duplicate_rows(owner, create_chore, app_context):
    chore = create_chore()
    with write_transaction() as db:
        save_occurrence(db, chore["id"], "2026-01-01", None, 0, exists=False)
    with pytest.raises(IntegrityError), write_transaction() as db:
        save_occurrence(db, chore["id"], "2026-01-01", None, 0, exists=False)
