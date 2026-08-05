"""Alembic environment with complete module-owned model registration."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from core.settings import Settings
from shared.model_registry import load_all_models
from shared.models import BaseModel

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

load_all_models()
target_metadata = BaseModel.metadata


def database_url() -> str:
    """Return the separately configured synchronous migration connection."""

    return Settings().DATABASE_MIGRATION_URL


def run_migrations_offline() -> None:
    """Generate SQL without opening a database connection."""

    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations using the dedicated schema-owner role."""

    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            render_as_batch=False,
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
