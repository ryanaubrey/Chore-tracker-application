from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

from ..config import ROOT


def prepare_database(engine):
    config = Config(str(ROOT / "alembic.ini"))
    expected = ScriptDirectory.from_config(config).get_current_head()
    with engine.connect().execution_options(immediate=True) as connection, connection.begin():
        tables = set(inspect(connection).get_table_names())
        current = MigrationContext.configure(connection).get_current_revision()
        if current == expected:
            return
        if engine.dialect.name == "mssql" or tables - {"alembic_version"} or current is not None:
            raise RuntimeError(
                "Database needs migration. Back it up, then run python -m alembic upgrade head."
            )
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
