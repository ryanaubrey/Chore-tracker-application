"""Validate and import a private SQLite backup into an empty migrated SQL Server database."""

import argparse
import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError

from backend.config import database_url
from backend.database import acquire_write_lock, build_engine
from backend.database.migrations import prepare_database
from backend.database.models import chores, occurrences, sessions, settings, users


TABLES = (users, settings, chores, occurrences)


def snapshot(source):
    file = Path(source).resolve(strict=True)
    with closing(sqlite3.connect(file.as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        db.execute("BEGIN")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SQLite integrity check failed.")
        if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("SQLite contains broken foreign keys.")
        data = {
            table.name: [dict(row) for row in db.execute(
                'SELECT ' + ', '.join(f'"{c.name}"' for c in table.columns) + f' FROM "{table.name}"'
            )] for table in TABLES
        }
    validate(data)
    return data


def validate(data):
    for table in TABLES:
        for row in data[table.name]:
            for column in table.columns:
                value = row[column.name]
                if value is None and not column.nullable:
                    raise ValueError(f"Missing required value in {table.name}.{column.name}.")
                limit = getattr(column.type, "length", None)
                if limit is not None and value is not None:
                    if not isinstance(value, str) or len(value.encode("utf-16-le")) // 2 > limit:
                        raise ValueError(f"Incompatible text in {table.name}.{column.name}.")
    members = data["users"]
    if ((members and sum(row["role"] == "owner" for row in members) != 1)
            or any(row["role"] not in {"owner", "admin", "member"} for row in members)):
        raise ValueError("Invalid household ownership or role.")
    if members and not any(row["key"] == "invite" and row["value"] for row in data["settings"]):
        raise ValueError("The configured household is missing an invitation record.")
    for row in data["chores"]:
        if (row["frequency"] not in {"once", "daily", "weekly"}
                or row["weekday"] not in range(7) or row["retired"] not in (0, 1)):
            raise ValueError("Invalid recurrence fields in the SQLite backup.")
        validate_day(row["start"])
    for row in data["occurrences"]:
        validate_day(row["day"])
        if row["completed"] not in (0, 1):
            raise ValueError("Invalid completion flag in the SQLite backup.")


def validate_day(value):
    try:
        if date.fromisoformat(value).isoformat() == value:
            return
    except (TypeError, ValueError):
        pass
    raise ValueError("The backup contains a noncanonical chore date.")


def require_matching_rows(db, data):
    for table in TABLES:
        fields = list(table.columns.keys())
        key = lambda row: tuple(row[column.name] for column in table.primary_key.columns)
        expected = sorted(data[table.name], key=key)
        actual = sorted(db.execute(select(table)).mappings(), key=key)
        if [tuple(row[field] for field in fields) for row in expected] != [
            tuple(row[field] for field in fields) for row in actual
        ]:
            raise ValueError(f"Verification failed for {table.name}.")


def transfer(engine, data):
    prepare_database(engine)
    with engine.connect().execution_options(immediate=True) as db, db.begin():
        acquire_write_lock(db)
        for table in (*TABLES, sessions):
            if db.execute(select(table).limit(1)).first() is not None:
                raise ValueError("The target must be empty. Import does not overwrite data.")
        for table in TABLES:
            for row in data[table.name]:
                # Explicit IDs on SQL Server use SQLAlchemy's IDENTITY_INSERT support.
                db.execute(insert(table).values(**row))
        require_matching_rows(db, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Verified SQLite backup")
    operations = parser.add_mutually_exclusive_group(required=True)
    operations.add_argument("--check", action="store_true", help="Validate source offline")
    operations.add_argument("--apply", action="store_true", help="Import via DATABASE_URL")
    args = parser.parse_args()
    try:
        data = snapshot(args.source)
        if args.apply:
            url = database_url()
            if url.drivername != "mssql+pyodbc":
                raise ValueError("Set DATABASE_URL to the empty migrated SQL Server target.")
            engine = build_engine(url)
            try:
                transfer(engine, data)
            finally:
                engine.dispose()
    except SQLAlchemyError as error:
        parser.exit(1, f"Database operation failed ({type(error).__name__}). Check connectivity and schema.\n")
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as error:
        # Do not emit raw driver messages, SQL parameters, credentials, or private rows.
        if isinstance(error, (OSError, sqlite3.Error, UnicodeError)):
            parser.exit(1, "Unable to read or validate the SQLite backup.\n")
        parser.exit(1, f"{error}\n")
    for table, rows in data.items():
        print(f"{table}: {len(rows)}")
    print("Sessions are not transferred.")


if __name__ == "__main__":
    main()
