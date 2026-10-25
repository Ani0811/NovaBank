"""Programmatic database migration runner for NovaBank using Alembic."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine


def get_repo_root() -> Path:
    """Find repository root by locating pyproject.toml or alembic.ini."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "alembic.ini").is_file() or (parent / "pyproject.toml").is_file():
            return parent
    return current.parents[4]


def get_alembic_config(
    engine: Optional[Engine] = None,
    alembic_ini_path: Optional[str | Path] = None,
) -> Config:
    """Create configured Alembic Config instance."""
    repo_root = get_repo_root()
    if alembic_ini_path is None:
        alembic_ini_path = repo_root / "alembic.ini"

    cfg = Config(str(alembic_ini_path))
    # Ensure script_location is an absolute path to migrations directory
    cfg.set_main_option("script_location", str(repo_root / "migrations"))

    if engine is not None:
        cfg.attributes["connection"] = engine.connect()

    return cfg


def run_migrations_up(engine: Engine, revision: str = "head") -> None:
    """Apply database migrations up to the target revision (default 'head')."""
    cfg = get_alembic_config(engine)
    conn = cfg.attributes.get("connection")
    try:
        command.upgrade(cfg, revision)
    finally:
        if conn is not None:
            conn.close()


def run_migrations_down(engine: Engine, revision: str = "base") -> None:
    """Revert database migrations down to the target revision (default 'base')."""
    cfg = get_alembic_config(engine)
    conn = cfg.attributes.get("connection")
    try:
        command.downgrade(cfg, revision)
    finally:
        if conn is not None:
            conn.close()
