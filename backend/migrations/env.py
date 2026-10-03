"""Alembic runs as the owner role (tables are owned by keel_owner; runtime uses keel_app)."""

from alembic import context
from sqlalchemy import create_engine

from keel.platform.config import get_settings

url = context.config.get_main_option("sqlalchemy.url") or get_settings().database_owner_url

with create_engine(url).connect() as connection:
    context.configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()
    connection.commit()
