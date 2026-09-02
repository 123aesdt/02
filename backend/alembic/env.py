from sqlalchemy import engine_from_config, pool

import app.models  # noqa: F401
from alembic import context
from app.core.config import get_settings
from app.models.base import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_settings().database_url
    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
