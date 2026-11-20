from sqlalchemy import BigInteger, Column, ForeignKey, Integer, MetaData, Unicode, Table, Text, text


metadata = MetaData()
# SQL Server needs bounded index keys. SQLite retains its original affinities.
identifier = BigInteger().with_variant(Integer(), "sqlite")


def string(length):
    return Unicode(length, collation="Latin1_General_100_BIN2").with_variant(Text(), "sqlite")


users = Table(
    "users", metadata,
    Column("id", identifier, primary_key=True),
    Column("name", string(160), nullable=False),
    Column("username", string(256), nullable=False, unique=True),
    Column("password", string(256), nullable=False),
    Column("role", string(16), nullable=False),
)
settings = Table(
    "settings", metadata,
    Column("key", string(64), primary_key=True, nullable=False),
    Column("value", string(256), nullable=False),
)
sessions = Table(
    "sessions", metadata,
    Column("token", string(64), primary_key=True, nullable=True),
    Column("user_id", identifier, ForeignKey("users.id")),
    Column("expires", identifier),
)
chores = Table(
    "chores", metadata,
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
    "occurrences", metadata,
    Column("chore_id", identifier, ForeignKey("chores.id"), primary_key=True, nullable=True),
    Column("day", string(10), primary_key=True, nullable=True),
    Column("assignee", identifier, ForeignKey("users.id")),
    Column("completed", Integer, nullable=False, server_default=text("0")),
)
