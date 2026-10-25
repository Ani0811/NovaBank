"""Tests for Alembic database migrations: upgrade, downgrade, and schema verification."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect

from novabank.infrastructure.db.migrator import run_migrations_down, run_migrations_up


@pytest.fixture
def test_db_engine(tmp_path: Path):
    """Create a temporary file-based SQLite database for running Alembic migrations."""
    db_file = tmp_path / "test_migration.db"
    engine = create_engine(f"sqlite:///{db_file}", echo=False)
    yield engine
    engine.dispose()


def test_alembic_upgrade_and_downgrade_cycle(test_db_engine):
    """Verify that alembic upgrades to head creating all tables, and downgrades to base cleanly."""
    inspector = inspect(test_db_engine)
    initial_tables = inspector.get_table_names()
    assert "accounts" not in initial_tables
    assert "transactions" not in initial_tables
    assert "audit_events" not in initial_tables

    # 1. Upgrade to head
    run_migrations_up(test_db_engine, revision="head")

    inspector = inspect(test_db_engine)
    migrated_tables = inspector.get_table_names()
    assert "accounts" in migrated_tables
    assert "transactions" in migrated_tables
    assert "audit_events" in migrated_tables
    assert "alembic_version" in migrated_tables

    # Check columns in accounts table
    account_cols = [c["name"] for c in inspector.get_columns("accounts")]
    assert "account_number" in account_cols
    assert "holder_name" in account_cols
    assert "balance" in account_cols
    assert "version" in account_cols

    # Check columns in transactions table
    tx_cols = [c["name"] for c in inspector.get_columns("transactions")]
    assert "transaction_id" in tx_cols
    assert "transaction_ref" in tx_cols
    assert "account_number" in tx_cols
    assert "direction" in tx_cols
    assert "amount" in tx_cols

    # 2. Downgrade to base
    run_migrations_down(test_db_engine, revision="base")

    inspector = inspect(test_db_engine)
    post_downgrade_tables = inspector.get_table_names()
    assert "accounts" not in post_downgrade_tables
    assert "transactions" not in post_downgrade_tables
    assert "audit_events" not in post_downgrade_tables


def test_migration_idempotent_reupgrade(test_db_engine):
    """Verify that re-running upgrade head after downgrade works idempotently."""
    run_migrations_up(test_db_engine, revision="head")
    run_migrations_down(test_db_engine, revision="base")
    run_migrations_up(test_db_engine, revision="head")

    inspector = inspect(test_db_engine)
    assert "accounts" in inspector.get_table_names()
    assert "transactions" in inspector.get_table_names()
