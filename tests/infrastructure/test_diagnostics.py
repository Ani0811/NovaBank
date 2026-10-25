"""Tests for safe, read-only database connectivity diagnostics."""

from unittest.mock import MagicMock, patch

from sqlalchemy.exc import OperationalError

from novabank.infrastructure.config import AppConfig
from novabank.infrastructure.db.diagnostics import (
    DatabaseDiagnostics,
    DatabaseStatus,
    check_database_connectivity,
    parse_version_tuple,
)


def test_parse_version_tuple():
    """Verify version tuple parsing from various MySQL version strings."""
    assert parse_version_tuple("8.0.35") == (8, 0, 35)
    assert parse_version_tuple("8.4.1-commercial") == (8, 4, 1)
    assert parse_version_tuple("5.7.44-log") == (5, 7, 44)
    assert parse_version_tuple("10.11.2-MariaDB") == (10, 11, 2)
    assert parse_version_tuple("invalid_version") == (0, 0)


def test_diagnostics_is_ready_property():
    """Verify is_ready property logic."""
    diag_ready = DatabaseDiagnostics(
        status=DatabaseStatus.CONNECTED,
        host="localhost",
        port=3306,
        user="root",
        database_name="novabank_db",
        server_version="8.0.35",
        version_compatible=True,
    )
    assert diag_ready.is_ready is True

    diag_old_version = DatabaseDiagnostics(
        status=DatabaseStatus.CONNECTED,
        host="localhost",
        port=3306,
        user="root",
        database_name="novabank_db",
        server_version="5.7.44",
        version_compatible=False,
    )
    assert diag_old_version.is_ready is False

    diag_stopped = DatabaseDiagnostics(
        status=DatabaseStatus.SERVICE_STOPPED,
        host="localhost",
        port=3306,
        user="root",
        database_name="novabank_db",
    )
    assert diag_stopped.is_ready is False


def test_successful_connection_with_legacy_schema():
    """Verify diagnostics when MySQL 8.0 connects and legacy narDB exists."""
    mock_conn = MagicMock()

    # Mock execute results
    def mock_execute(statement, *args, **kwargs):
        sql_text = str(statement).lower()
        mock_cursor = MagicMock()
        if "version()" in sql_text:
            mock_cursor.scalar.return_value = "8.0.36"
        elif "schemata" in sql_text:
            mock_cursor.scalar.return_value = "narDB"
        elif "information_schema.tables" in sql_text:
            mock_cursor.fetchall.return_value = [
                ("BMS_MASTER", 42),
                ("BMS_ACCOUNTS", 150),
            ]
        return mock_cursor

    mock_conn.execute.side_effect = mock_execute
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    with patch("novabank.infrastructure.db.diagnostics.create_engine", return_value=mock_engine):
        report = check_database_connectivity()

    assert report.status == DatabaseStatus.CONNECTED
    assert report.server_version == "8.0.36"
    assert report.version_compatible is True
    assert report.is_ready is True

    assert report.legacy_schema is not None
    assert report.legacy_schema.database_exists is True
    assert report.legacy_schema.master_table_exists is True
    assert report.legacy_schema.master_row_count == 42
    assert report.legacy_schema.accounts_table_exists is True
    assert report.legacy_schema.accounts_row_count == 150


def test_successful_connection_without_legacy_schema():
    """Verify diagnostics when MySQL 8.0 connects and legacy narDB does not exist."""
    mock_conn = MagicMock()

    def mock_execute(statement, *args, **kwargs):
        sql_text = str(statement).lower()
        mock_cursor = MagicMock()
        if "version()" in sql_text:
            mock_cursor.scalar.return_value = "8.4.0"
        elif "schemata" in sql_text:
            mock_cursor.scalar.return_value = None  # narDB does not exist
        return mock_cursor

    mock_conn.execute.side_effect = mock_execute
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    with patch("novabank.infrastructure.db.diagnostics.create_engine", return_value=mock_engine):
        report = check_database_connectivity()

    assert report.status == DatabaseStatus.CONNECTED
    assert report.version_compatible is True
    assert report.legacy_schema is not None
    assert report.legacy_schema.database_exists is False
    assert report.legacy_schema.master_table_exists is False


def test_incompatible_version():
    """Verify diagnostics when connected MySQL version is less than 8.0."""
    mock_conn = MagicMock()

    def mock_execute(statement, *args, **kwargs):
        sql_text = str(statement).lower()
        mock_cursor = MagicMock()
        if "version()" in sql_text:
            mock_cursor.scalar.return_value = "5.7.42"
        elif "schemata" in sql_text:
            mock_cursor.scalar.return_value = None
        return mock_cursor

    mock_conn.execute.side_effect = mock_execute
    mock_engine = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    with patch("novabank.infrastructure.db.diagnostics.create_engine", return_value=mock_engine):
        report = check_database_connectivity()

    assert report.status == DatabaseStatus.CONNECTED
    assert report.server_version == "5.7.42"
    assert report.version_compatible is False
    assert report.is_ready is False


def test_connection_refused_or_service_stopped():
    """Verify diagnostics when connection refused indicates service is stopped."""
    mock_err = OperationalError(
        statement="SELECT 1",
        params={},
        orig=Exception("(2003, Can't connect to MySQL server on 'localhost' (10061))"),
    )

    with patch("novabank.infrastructure.db.diagnostics.create_engine", side_effect=mock_err):
        report = check_database_connectivity(AppConfig(db_host="localhost"))

    assert report.status == DatabaseStatus.SERVICE_STOPPED
    assert "Cannot reach MySQL server" in report.error_message
    assert report.is_ready is False


def test_auth_failed_error():
    """Verify diagnostics when password or user is rejected."""
    mock_err = OperationalError(
        statement="SELECT 1",
        params={},
        orig=Exception("(1045, Access denied for user 'root'@'localhost')"),
    )

    with patch("novabank.infrastructure.db.diagnostics.create_engine", side_effect=mock_err):
        report = check_database_connectivity(AppConfig(db_host="localhost", db_user="root"))

    assert report.status == DatabaseStatus.AUTH_FAILED
    assert "Authentication failed for user 'root'" in report.error_message
    assert report.is_ready is False


def test_live_database_diagnostics_on_local_host():
    """Live integration check against local host: cleanly returns diagnostics without unhandled exception."""
    config = AppConfig(db_host="localhost", db_port=3306)
    report = check_database_connectivity(config=config, timeout_seconds=1.0)
    # The local MySQL service may be stopped or running; whichever it is, report must be valid
    assert report.status in (
        DatabaseStatus.SERVICE_STOPPED,
        DatabaseStatus.UNREACHABLE,
        DatabaseStatus.CONNECTED,
        DatabaseStatus.AUTH_FAILED,
    )
    assert report.host == "localhost"
    assert report.port == 3306
