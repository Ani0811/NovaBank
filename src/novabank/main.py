"""NovaBank desktop application entrypoint."""

from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal
import logging
from pathlib import Path
import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication

from novabank.application.services.audit_service import AuditService
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.config import AppConfig
from novabank.infrastructure.db.diagnostics import check_database_connectivity
from novabank.infrastructure.db.models import Base
from novabank.infrastructure.db.session import (
    create_db_engine,
    create_session_factory,
    init_database,
)
from novabank.ui.main_window import MainWindow
from novabank.ui.workers.task_runner import TaskRunner

APP_NAME = "NovaBank"
APP_VERSION = "1.0.0"
ORG_NAME = "NovaBank Enterprise Solutions"
logger = logging.getLogger(__name__)


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


def seed_demo_data(banking_service: BankingService) -> None:
    """Seed realistic initial data for demonstration mode."""
    try:
        acc1 = banking_service.open_account(
            holder_name="Clark Kent",
            dob=date(1985, 6, 18),
            address_line="344 Clinton St, Apt 3B",
            city="Metropolis",
            state="NY",
            country="USA",
            phone_number="212-555-0199",
            initial_deposit=Decimal("15000.00"),
            currency="USD",
            actor="system_demo",
        )
        acc2 = banking_service.open_account(
            holder_name="Diana Prince",
            dob=date(1988, 3, 22),
            address_line="100 Central Pkwy, Suite 4",
            city="Gateway City",
            state="CA",
            country="USA",
            phone_number="415-555-0142",
            initial_deposit=Decimal("28500.00"),
            currency="USD",
            actor="system_demo",
        )
        acc3 = banking_service.open_account(
            holder_name="Bruce Wayne",
            dob=date(1982, 5, 27),
            address_line="1007 Mountain Drive",
            city="Gotham",
            state="NJ",
            country="USA",
            phone_number="201-555-0188",
            initial_deposit=Decimal("95000.00"),
            currency="USD",
            actor="system_demo",
        )

        banking_service.deposit(
            account_number=acc1.account.account_number,
            amount=Decimal("2500.00"),
            description="Payroll Direct Deposit - Daily Planet",
            actor="payroll_system",
        )
        banking_service.withdraw(
            account_number=acc1.account.account_number,
            amount=Decimal("450.00"),
            description="ATM Withdrawal - Metropolis Downtown",
            actor="atm_terminal_4",
        )
        banking_service.transfer(
            source_account_number=acc3.account.account_number,
            destination_account_number=acc2.account.account_number,
            amount=Decimal("5000.00"),
            description="Charity Gala Contribution",
            actor="wire_transfer",
        )
        print("[NovaBank] Demo database initialized with sample accounts and transactions.")
    except Exception as exc:
        print(f"[NovaBank] Notice: Demo seeding encountered: {exc}")


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
    if sys.platform == "win32":
        from PySide6.QtGui import QFontDatabase

        for font_file in ("segoeui.ttf", "seguisym.ttf", "seguiemj.ttf"):
            font_path = Path("C:/Windows/Fonts") / font_file
            if font_path.exists():
                QFontDatabase.addApplicationFont(str(font_path))

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    # Initialize database engine & session factory
    is_demo_mode = args.demo
    session_factory = None

    if not is_demo_mode:
        try:
            engine = create_db_engine(config)
            with engine.connect():
                pass
            init_database(engine)
            session_factory = create_session_factory(engine)
        except Exception as exc:
            print(
                f"[NovaBank] Could not connect to MySQL ({exc}). "
                f"Falling back to local in-memory demo mode."
            )
            is_demo_mode = True

    if is_demo_mode or session_factory is None:
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            echo=False,
        )
        Base.metadata.create_all(bind=engine)
        session_factory = create_session_factory(engine)

    banking_service = BankingService(session_factory)
    audit_service = AuditService(session_factory)
    banking_service.subscribe(audit_service.handle_event)

    if is_demo_mode:
        seed_demo_data(banking_service)

    task_runner = TaskRunner()

    main_win = MainWindow(banking_service=banking_service, task_runner=task_runner)
    main_win.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
