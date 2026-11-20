"""Create the initial schema or register a verified legacy SQLite database."""

from alembic import op
import sqlalchemy as sa


from sqlalchemy import BigInteger, Column, ForeignKey, Integer, MetaData, Unicode, Table, text


# Frozen SQL Server schema for the initial revision.
mssql_metadata = MetaData()
# SQL Server needs bounded index keys. SQLite retains its original affinities.
identifier = BigInteger()


def string(length):
    return Unicode(length, collation="Latin1_General_100_BIN2")


users = Table(
    "users", mssql_metadata,
    Column("id", identifier, primary_key=True),
    Column("name", string(160), nullable=False),
    Column("username", string(256), nullable=False, unique=True),
    Column("password", string(256), nullable=False),
    Column("role", string(16), nullable=False),
)
settings = Table(
    "settings", mssql_metadata,
    Column("key", string(64), primary_key=True, nullable=False),
    Column("value", string(256), nullable=False),
)
sessions = Table(
    "sessions", mssql_metadata,
    Column("token", string(64), primary_key=True, nullable=True),
    Column("user_id", identifier, ForeignKey("users.id")),
    Column("expires", identifier),
)
chores = Table(
    "chores", mssql_metadata,
    Column("id", identifier, primary_key=True),
    Column("title", string(200), nullable=False),
    Column("details", string(1000), nullable=False),
    Column("frequency", string(16), nullable=False),
    Column("start", string(10), nullable=False),
    Column("weekday", Integer, nullable=False),
    Column("assignee", identifier, ForeignKey("users.id")),
    Column("retired", Integer, nullable=False, server_default=text("0")),
)
occurrences = Table(
    "occurrences", mssql_metadata,
    Column("chore_id", identifier, ForeignKey("chores.id"), primary_key=True, nullable=True),
    Column("day", string(10), primary_key=True, nullable=True),
    Column("assignee", identifier, ForeignKey("users.id")),
    Column("completed", Integer, nullable=False, server_default=text("0")),
)

write_lock = Table("chores_write_lock", mssql_metadata,
                   Column("id", Integer, primary_key=True, autoincrement=False))


revision = "0001_sqlite_baseline"
down_revision = None
branch_labels = None
depends_on = None


def schema():
    metadata = sa.MetaData()
    sa.Table("users", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("username", sa.Text, nullable=False, unique=True),
        sa.Column("password", sa.Text, nullable=False),
        sa.Column("role", sa.Text, nullable=False),
    )
    sa.Table("settings", metadata,
        sa.Column("key", sa.Text, primary_key=True, nullable=True),
        sa.Column("value", sa.Text, nullable=False),
    )
    sa.Table("sessions", metadata,
        sa.Column("token", sa.Text, primary_key=True, nullable=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("expires", sa.Integer),
    )
    sa.Table("chores", metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("details", sa.Text, nullable=False),
        sa.Column("frequency", sa.Text, nullable=False),
        sa.Column("start", sa.Text, nullable=False),
        sa.Column("weekday", sa.Integer, nullable=False),
        sa.Column("assignee", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("retired", sa.Integer, nullable=False, server_default=sa.text("0")),
    )
    sa.Table("occurrences", metadata,
        sa.Column("chore_id", sa.Integer, sa.ForeignKey("chores.id"), primary_key=True, nullable=True),
        sa.Column("day", sa.Text, primary_key=True, nullable=True),
        sa.Column("assignee", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("completed", sa.Integer, nullable=False, server_default=sa.text("0")),
    )
    return metadata


def validate_legacy(connection, inspector, metadata):
    for name, table in metadata.tables.items():
        columns = {column["name"]: column for column in inspector.get_columns(name)}
        expected_pk = tuple(column.name for column in table.primary_key.columns)
        actual_pk = tuple(inspector.get_pk_constraint(name)["constrained_columns"])
        expected_unique = {(column.name,) for column in table.columns if column.unique}
        actual_unique = {tuple(item["column_names"]) for item in inspector.get_unique_constraints(name)}
        expected_fks = {(fk.parent.name, fk.column.table.name, fk.column.name)
                        for fk in table.foreign_keys}
        actual_fks = {(local, fk["referred_table"], remote)
                      for fk in inspector.get_foreign_keys(name)
                      for local, remote in zip(fk["constrained_columns"], fk["referred_columns"])}
        if (set(columns) != set(table.columns.keys()) or actual_pk != expected_pk
                or actual_unique != expected_unique or actual_fks != expected_fks):
            raise RuntimeError(f"Legacy schema does not match expected keys or columns in {name}.")
        for column in table.columns:
            reflected = columns[column.name]
            expected_default = str(column.server_default.arg) if column.server_default else None
            implicit_rowid = column.primary_key and len(expected_pk) == 1 and column.name == "id"
            if (str(reflected["type"]) != str(column.type)
                    or reflected["default"] != expected_default
                    or (not implicit_rowid and reflected["nullable"] != column.nullable)):
                raise RuntimeError(f"Legacy column definition does not match {name}.{column.name}.")
    if connection.exec_driver_sql("PRAGMA integrity_check").scalars().all() != ["ok"]:
        raise RuntimeError("SQLite integrity check failed.")
    if connection.exec_driver_sql("PRAGMA foreign_key_check").first() is not None:
        raise RuntimeError("SQLite foreign-key check failed.")


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "mssql":
        tables = set(sa.inspect(connection).get_table_names()) - {"alembic_version"}
        if tables:
            raise RuntimeError("Use an empty SQL Server database for the initial revision.")
        mssql_metadata.create_all(connection)
        connection.execute(write_lock.insert().values(id=1))
        return
    metadata = schema()
    inspector = sa.inspect(connection)
    tables = set(inspector.get_table_names()) - {"alembic_version"}
    if not tables:
        metadata.create_all(connection)
    elif tables == set(metadata.tables):
        validate_legacy(connection, inspector, metadata)
    else:
        raise RuntimeError("Database contains an unexpected or incomplete legacy schema.")


def downgrade():
    if op.get_bind().dialect.name == "mssql":
        raise RuntimeError("SQL Server rollback uses a database restore or a separate database.")
    # The previous application uses the same tables. Only remove the revision marker.
    pass
