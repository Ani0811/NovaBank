"""NovaBank desktop application entrypoint."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.config import AppConfig
from novabank.infrastructure.db.diagnostics import check_database_connectivity
from novabank.infrastructure.db.session import create_db_engine, create_session_factory
from novabank.ui.main_window import MainWindow
from novabank.ui.workers.task_runner import TaskRunner

APP_NAME = "NovaBank"
APP_VERSION = "1.0.0"
ORG_NAME = "NovaBank Enterprise Solutions"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line flags."""
    parser = argparse.ArgumentParser(
        prog="novabank",
        description="NovaBank Enterprise Desktop Banking System",
    )
    parser.add_argument(
        "-v", "--version", action="version", version=f"{APP_NAME} v{APP_VERSION}"
    )
    parser.add_argument(
        "--diagnostics", action="store_true", help="Run database and system diagnostics and exit"
    )
    parser.add_argument(
        "--check-db", action="store_true", help="Verify MySQL database connectivity and exit"
    )
    parser.add_argument(
        "--demo", action="store_true", help="Launch in demo mode using an in-memory database"
    )
    return parser.parse_args(argv)


def run_diagnostics(config: AppConfig) -> int:
    """Run diagnostics and print report to console."""
    print("=" * 60)
    print(f" {APP_NAME} System Diagnostics (v{APP_VERSION})")
    print("=" * 60)
    print(f"Host: {config.db_host}:{config.db_port}")
    print(f"Database: {config.db_name}")
    print(f"User: {config.db_user}")

    diag = check_database_connectivity(config)
    print("\n[Database Check Results]")
    print(f"Connection Status: {'SUCCESS' if diag.connection_successful else 'FAILED'}")
    if diag.server_version:
        print(f"Server Version: {diag.server_version}")
    if diag.error_message:
        print(f"Diagnostic Error: {diag.error_message}")
    print(f"Legacy narDB Detected: {'YES' if diag.has_legacy_bms_tables else 'NO'}")
    print("=" * 60)
    return 0 if diag.connection_successful else 1


def main(argv: Optional[list[str]] = None) -> int:
    """Application main entrypoint."""
    args = parse_args(argv)
    config = AppConfig()

    if args.diagnostics:
        return run_diagnostics(config)

    if args.check_db:
        diag = check_database_connectivity(config)
        if diag.connection_successful:
            print(f"Database connection healthy: {diag.server_version}")
            return 0
        print(f"Database connection failed: {diag.error_message}")
        return 1

    # Initialize PySide6 GUI Application
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName(ORG_NAME)

    # Set default modern font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Initialize database engine & session factory
    if args.demo:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from novabank.infrastructure.db.models import Base

        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)
    else:
        try:
            engine = create_db_engine(config)
            session_factory = create_session_factory(engine)
        except Exception:
            # Fallback to local SQLite in-memory for demo / graceful start
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from novabank.infrastructure.db.models import Base

            engine = create_engine("sqlite:///:memory:", echo=False)
            Base.metadata.create_all(bind=engine)
            session_factory = sessionmaker(bind=engine)

    banking_service = BankingService(session_factory)
    task_runner = TaskRunner()

    main_win = MainWindow(banking_service=banking_service, task_runner=task_runner)
    main_win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

