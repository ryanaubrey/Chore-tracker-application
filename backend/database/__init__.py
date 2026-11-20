from contextlib import contextmanager
from pathlib import Path

from flask import current_app
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, event, select
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool


write_lock = Table("chores_write_lock", MetaData(), Column("id", Integer, primary_key=True))


def encrypted_sql_server_url(url):
    if (url.drivername != "mssql+pyodbc" or not url.host or not url.database
            or not url.username or not url.password):
        raise ValueError("Use a named SQL Server database and credentials with mssql+pyodbc.")
    if any(value in url.host for value in ";{}") or any(
        character in url.database for character in ";{}"
    ):
        raise ValueError("Invalid SQL Server host or database name.")
    if url.query:
        raise ValueError("SQL Server driver and TLS options are fixed by the application.")
    return url.set(query={"driver": "ODBC Driver 18 for SQL Server", "Encrypt": "yes",
                          "TrustServerCertificate": "no"})


def build_engine(value):
    url = make_url(value)
    if url.get_backend_name() == "mssql":
        return create_engine(encrypted_sql_server_url(url), hide_parameters=True,
                             connect_args={"timeout": 15}, pool_pre_ping=True)
    if url.get_backend_name() != "sqlite":
        raise ValueError("Use SQLite or SQL Server.")
    if not url.database or url.database == ":memory:" or url.query.get("mode") == "memory":
        raise ValueError("Configure a file-backed SQLite database.")
    Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(url, connect_args={"timeout": 15}, poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def configure_connection(dbapi_connection, _):
        # SQLAlchemy owns BEGIN, including the SQLite-specific write lock.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def begin(connection):
        sql = "BEGIN IMMEDIATE" if connection.get_execution_options().get("immediate") else "BEGIN"
        connection.exec_driver_sql(sql)

    return engine


def connect():
    return current_app.extensions["chores_engine"].connect()


@contextmanager
def write_transaction():
    with connect() as db:
        with db.execution_options(immediate=True).begin():
            acquire_write_lock(db)
            yield db


def acquire_write_lock(db):
    if db.dialect.name == "mssql":
        statement = (select(write_lock.c.id).where(write_lock.c.id == 1)
                     .with_hint(write_lock, "WITH (UPDLOCK, HOLDLOCK)", "mssql"))
        db.execute(statement).scalar_one()
