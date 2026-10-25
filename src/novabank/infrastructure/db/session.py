"""Database engine and session management for NovaBank."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from novabank.infrastructure.config import AppConfig
from novabank.infrastructure.db.models import Base


def create_db_engine(
    config: Optional[AppConfig] = None,
    custom_url: Optional[str] = None,
    echo: bool = False,
) -> Engine:
    """Create a SQLAlchemy Engine with connection pooling configured."""
    if custom_url:
        db_url = custom_url
    else:
        if config is None:
            config = AppConfig()
        db_url = config.database_url

    connect_args = {}
    if "sqlite" in db_url:
        connect_args["check_same_thread"] = False
    elif "mysql" in db_url:
        connect_args["connect_timeout"] = 5

    engine = create_engine(
        db_url,
        echo=echo,
        connect_args=connect_args,
        pool_pre_ping=True,
    )
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a configured sessionmaker bound to the given engine."""
    return sessionmaker(
        bind=engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def init_database(engine: Engine) -> None:
    """Initialize all database tables defined in metadata."""
    Base.metadata.create_all(bind=engine)
