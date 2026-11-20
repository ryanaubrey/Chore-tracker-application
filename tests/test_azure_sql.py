from contextlib import closing
import importlib
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_mock_engine
from sqlalchemy.dialects import mssql
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateTable

from backend.database import acquire_write_lock, build_engine, encrypted_sql_server_url
from backend.database.models import chores, occurrences, users
from scripts.backup_sqlite import backup_database
from scripts.transfer_sqlite import require_matching_rows, snapshot, transfer


def test_sql_server_uses_driver_18_with_certificate_validation():
    url = encrypted_sql_server_url(make_url("mssql+pyodbc://user:example@sql.invalid:1433/chores"))
    assert url.query["driver"] == "ODBC Driver 18 for SQL Server"
    assert url.query["Encrypt"] == "yes"
    assert url.query["TrustServerCertificate"] == "no"
    assert "example" not in str(url)
    with pytest.raises(ValueError, match="TLS options"):
        encrypted_sql_server_url(url.set(query={"TrustServerCertificate": "yes"}))


def test_sql_server_schema_compiles_with_identity_unicode_and_nonnull_keys():
    revision = importlib.import_module("backend.migrations.versions.0001_sqlite_baseline")
    dialect = mssql.dialect()
    for model in (users, chores, occurrences):
        ddl = str(CreateTable(model).compile(dialect=dialect))
        assert ddl == str(CreateTable(revision.mssql_metadata.tables[model.name]).compile(dialect=dialect))
    assert "BIGINT NOT NULL IDENTITY" in str(CreateTable(users).compile(dialect=dialect))
    assert "NVARCHAR(256)" in str(CreateTable(users).compile(dialect=dialect))
    ddl = str(CreateTable(occurrences).compile(dialect=dialect))
    assert "PRIMARY KEY (chore_id, day)" in ddl and "chore_id BIGINT NOT NULL" in ddl
    assert "day NVARCHAR(10) COLLATE Latin1_General_100_BIN2 NOT NULL" in ddl


def test_sql_server_write_guard_compiles_with_transaction_lock_hints():
    statements = []

    class Result:
        def scalar_one(self):
            return 1

    def execute(statement, *args, **kwargs):
        statements.append(str(statement.compile(dialect=mssql.dialect())))
        return Result()

    db = create_mock_engine("mssql+pyodbc://", execute)
    acquire_write_lock(db)
    assert "WITH (UPDLOCK, HOLDLOCK)" in statements[0]


def test_transfer_rehearsal_keeps_accounts_assignments_and_history(tmp_path):
    source = tmp_path / "origin.sqlite3"
    with closing(sqlite3.connect(source)) as db, db:
        db.executescript(Path(__file__).with_name("legacy_schema.sql").read_text())
        db.executescript("""
            INSERT INTO users VALUES (9,'Owner','owner','scrypt:131072:8:1$salt$hash','owner');
            INSERT INTO users VALUES (12,'Member','member','legacy-format','member');
            INSERT INTO settings VALUES ('invite','test invite');
            INSERT INTO sessions VALUES ('test token',9,2000000000);
            INSERT INTO chores VALUES (7,'Recycling','','weekly','2026-01-01',3,9,0);
            INSERT INTO occurrences VALUES (7,'2026-01-01',12,1);
        """)
    backup = tmp_path / "backup.sqlite3"
    backup_database(source, backup)
    data = snapshot(backup)
    engine = build_engine(f"sqlite:///{(tmp_path / 'target.sqlite3').as_posix()}")
    try:
        transfer(engine, data)
        with engine.connect() as db:
            require_matching_rows(db, data)
            assert db.exec_driver_sql("SELECT count(*) FROM sessions").scalar_one() == 0
        with pytest.raises(ValueError, match="target must be empty"):
            transfer(engine, data)
        assert snapshot(source) == data
    finally:
        engine.dispose()
