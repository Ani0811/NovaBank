import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# Add src to sys.path so novabank can be imported
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from novabank.infrastructure.config import AppConfig
from novabank.infrastructure.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode without an active DB connection."""
    app_config = AppConfig()
    url = config.get_main_option("sqlalchemy.url") or app_config.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with an active engine."""
    # If a connection or engine is passed programmatically via config.attributes
    connection = config.attributes.get("connection", None)

    if connection is not None:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()
    else:
        app_config = AppConfig()
        db_url = config.get_main_option("sqlalchemy.url") or app_config.database_url

        connect_args = {}
        if "sqlite" in db_url:
            connect_args["check_same_thread"] = False
        elif "mysql" in db_url:
            connect_args["connect_timeout"] = 5

        connectable = create_engine(
            db_url,
            poolclass=pool.NullPool,
            connect_args=connect_args,
        )

        with connectable.connect() as conn:
            context.configure(
                connection=conn,
                target_metadata=target_metadata,
            )
            with context.begin_transaction():
                context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
