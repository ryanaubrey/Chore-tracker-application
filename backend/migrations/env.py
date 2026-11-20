from alembic import context

from backend.config import database_url
from backend.database import build_engine
from backend.database.models import metadata


def migrate(connection):
    context.configure(connection=connection, target_metadata=metadata, transactional_ddl=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("This migration requires a live database connection for schema checks.")

existing = context.config.attributes.get("connection")
if existing is not None:
    migrate(existing)
else:
    engine = build_engine(database_url())
    try:
        with engine.connect().execution_options(immediate=True) as connection, connection.begin():
            migrate(connection)
    finally:
        engine.dispose()
