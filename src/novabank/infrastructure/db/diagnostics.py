"""Safe, read-only database connectivity and environment diagnostics for NovaBank."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from novabank.infrastructure.config import AppConfig


class DatabaseStatus(str, Enum):
    """Database connectivity status enum."""

    CONNECTED = "CONNECTED"
    UNREACHABLE = "UNREACHABLE"
    SERVICE_STOPPED = "SERVICE_STOPPED"
    AUTH_FAILED = "AUTH_FAILED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class LegacySchemaStatus(BaseModel):
    """Status of legacy narDB tables (read-only inspection)."""

    database_exists: bool = Field(default=False, description="True if legacy narDB schema exists")
    master_table_exists: bool = Field(default=False, description="True if BMS_MASTER table exists")
    master_row_count: int = Field(default=0, description="Approximate row count in BMS_MASTER")
    accounts_table_exists: bool = Field(
        default=False, description="True if BMS_ACCOUNTS table exists"
    )
    accounts_row_count: int = Field(default=0, description="Approximate row count in BMS_ACCOUNTS")


class DatabaseDiagnostics(BaseModel):
    """Structured report returned by the database diagnostics checker."""

    status: DatabaseStatus = Field(description="Connection outcome status")
    host: str = Field(description="Target host")
    port: int = Field(description="Target port")
    user: str = Field(description="Target database user")
    database_name: str = Field(description="Target database schema")
    server_version: Optional[str] = Field(default=None, description="MySQL server version string")
    version_compatible: bool = Field(default=False, description="True if server version >= 8.0")
    error_message: Optional[str] = Field(
        default=None, description="User-friendly error description if failed"
    )
    legacy_schema: Optional[LegacySchemaStatus] = Field(
        default=None, description="Legacy narDB inspection report"
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="UTC timestamp of check"
    )

    @property
    def is_ready(self) -> bool:
        """Check if database connection is fully operational."""
        return self.status == DatabaseStatus.CONNECTED and self.version_compatible


def parse_version_tuple(version_str: str) -> tuple[int, ...]:
    """Extract numeric version components from MySQL version string (e.g. '8.0.35' -> (8, 0, 35))."""
    match = re.search(r"(\d+(?:\.\d+)+)", version_str)
    if match:
        return tuple(int(part) for part in match.group(1).split("."))
    return (0, 0)


def check_database_connectivity(
    config: Optional[AppConfig] = None,
    timeout_seconds: float = 3.0,
    check_legacy_schema: bool = True,
) -> DatabaseDiagnostics:
    """Test MySQL connectivity, check server version, and inspect legacy tables in strictly read-only mode.

    NEVER issues DDL (no DROP, CREATE, or ALTER).
    """
    if config is None:
        config = AppConfig()

    host = config.db_host
    port = config.db_port
    user = config.db_user
    db_name = config.db_name
    password = config.resolve_db_password()

    # Connect to MySQL server (without specific schema first to allow server diagnostics)
    server_url = f"mysql+pymysql://{user}:{password}@{host}:{port}/"

    try:
        engine = create_engine(
            server_url,
            connect_args={"connect_timeout": int(timeout_seconds)},
            pool_pre_ping=True,
        )

        with engine.connect() as conn:
            # 1. Fetch MySQL server version
            version_result = conn.execute(text("SELECT VERSION();")).scalar()
            version_str = str(version_result) if version_result else "Unknown"

            parsed_ver = parse_version_tuple(version_str)
            version_compatible = parsed_ver >= (8, 0)

            # 2. Inspect legacy narDB in read-only mode via information_schema
            legacy_report = None
            if check_legacy_schema:
                legacy_report = _inspect_legacy_schema(conn)

            return DatabaseDiagnostics(
                status=DatabaseStatus.CONNECTED,
                host=host,
                port=port,
                user=user,
                database_name=db_name,
                server_version=version_str,
                version_compatible=version_compatible,
                legacy_schema=legacy_report,
            )

    except OperationalError as oe:
        err_str = str(oe).lower()
        if "2003" in err_str or "connection refused" in err_str or "can't connect" in err_str:
            status = (
                DatabaseStatus.SERVICE_STOPPED
                if host in ("localhost", "127.0.0.1")
                else DatabaseStatus.UNREACHABLE
            )
            msg = f"Cannot reach MySQL server at {host}:{port}. Verify that the MySQL service is running."
        elif "1045" in err_str or "access denied" in err_str:
            status = DatabaseStatus.AUTH_FAILED
            msg = f"Authentication failed for user '{user}' at {host}:{port}. Check password in .env or Windows Credential Manager."
        else:
            status = DatabaseStatus.UNREACHABLE
            msg = f"MySQL Operational error: {oe}"

        return DatabaseDiagnostics(
            status=status,
            host=host,
            port=port,
            user=user,
            database_name=db_name,
            error_message=msg,
        )

    except SQLAlchemyError as se:
        return DatabaseDiagnostics(
            status=DatabaseStatus.UNKNOWN_ERROR,
            host=host,
            port=port,
            user=user,
            database_name=db_name,
            error_message=f"Database error: {se}",
        )
    except Exception as e:
        return DatabaseDiagnostics(
            status=DatabaseStatus.UNKNOWN_ERROR,
            host=host,
            port=port,
            user=user,
            database_name=db_name,
            error_message=f"Unexpected error: {e}",
        )


def _inspect_legacy_schema(conn) -> LegacySchemaStatus:
    """Inspect information_schema for legacy narDB and tables in read-only mode."""
    # Check if narDB database exists
    schema_query = text(
        "SELECT SCHEMA_NAME FROM information_schema.SCHEMATA WHERE LOWER(SCHEMA_NAME) = 'nardb';"
    )
    schema_row = conn.execute(schema_query).scalar()
    if not schema_row:
        return LegacySchemaStatus(database_exists=False)

    # Query tables in legacy schema
    tables_query = text(
        "SELECT TABLE_NAME, TABLE_ROWS FROM information_schema.TABLES "
        "WHERE LOWER(TABLE_SCHEMA) = 'nardb' "
        "AND UPPER(TABLE_NAME) IN ('BMS_MASTER', 'BMS_ACCOUNTS');"
    )
    rows = conn.execute(tables_query).fetchall()

    master_exists = False
    master_count = 0
    accounts_exists = False
    accounts_count = 0

    for table_name, table_rows in rows:
        name_upper = str(table_name).upper()
        count = int(table_rows or 0)
        if name_upper == "BMS_MASTER":
            master_exists = True
            master_count = count
        elif name_upper == "BMS_ACCOUNTS":
            accounts_exists = True
            accounts_count = count

    return LegacySchemaStatus(
        database_exists=True,
        master_table_exists=master_exists,
        master_row_count=master_count,
        accounts_table_exists=accounts_exists,
        accounts_row_count=accounts_count,
    )


if __name__ == "__main__":
    report = check_database_connectivity()
    print("=" * 60)
    print(f"NovaBank Database Diagnostics Report ({report.timestamp.isoformat()})")
    print("=" * 60)
    print(f"Status:             {report.status.value}")
    print(f"Target:             {report.user}@{report.host}:{report.port}/{report.database_name}")
    if report.server_version:
        print(
            f"Server Version:     {report.server_version} (Compatible >= 8.0: {report.version_compatible})"
        )
    if report.error_message:
        print(f"Diagnostics:        {report.error_message}")
    if report.legacy_schema:
        print("-" * 60)
        print("Legacy narDB Inspection:")
        print(f"  Schema Exists:    {report.legacy_schema.database_exists}")
        if report.legacy_schema.database_exists:
            print(
                f"  BMS_MASTER:       {report.legacy_schema.master_table_exists} (~{report.legacy_schema.master_row_count} rows)"
            )
            print(
                f"  BMS_ACCOUNTS:     {report.legacy_schema.accounts_table_exists} (~{report.legacy_schema.accounts_row_count} rows)"
            )
    print("=" * 60)
