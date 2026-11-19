"""Offscreen capture script for NovaBank CD Vault & Term Deposits module."""

from datetime import date
from decimal import Decimal
import os
import sys
from pathlib import Path

# Ensure offscreen rendering
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QApplication
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.term_deposit_dto import OpenCDRequestDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.main_window import MainWindow


def main():
    app = QApplication.instance() or QApplication(sys.argv)

    # In-memory database setup
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    service = BankingService(session_factory=session_factory)

    # 1. Seed Customer Profiles
    acc1 = service.open_account(
        holder_name="Apex Global Capital LLC",
        dob=date(1982, 4, 15),
        address_line="100 Financial Center Blvd",
        city="Charlotte",
        state="NC",
        country="USA",
        phone_number="7045550188",
        initial_deposit=Decimal("750000.00"),
    ).account.account_number

    acc2 = service.open_account(
        holder_name="Quantum Systems Holdings",
        dob=date(1989, 8, 22),
        address_line="450 Innovation Parkway",
        city="San Jose",
        state="CA",
        country="USA",
        phone_number="4085550122",
        initial_deposit=Decimal("500000.00"),
    ).account.account_number

    acc3 = service.open_account(
        holder_name="Meridian Heritage Trust",
        dob=date(1975, 11, 30),
        address_line="1200 Beacon Hill Rd",
        city="Boston",
        state="MA",
        country="USA",
        phone_number="6175550133",
        initial_deposit=Decimal("1250000.00"),
    ).account.account_number

    # 2. Seed Certificates of Deposit
    cd1 = service.open_term_deposit(
        OpenCDRequestDTO(
            account_number=acc1,
            principal=Decimal("100000.00"),
            apy_percentage=Decimal("4.50"),
            tenor_months=12,
            payout_frequency="AT_MATURITY",
            rollover_option="PAYOUT_AND_CLOSE",
        )
    )

    cd2 = service.open_term_deposit(
        OpenCDRequestDTO(
            account_number=acc2,
            principal=Decimal("250000.00"),
            apy_percentage=Decimal("4.85"),
            tenor_months=24,
            payout_frequency="QUARTERLY",
            rollover_option="PRINCIPAL_AND_INTEREST",
        )
    )

    cd3 = service.open_term_deposit(
        OpenCDRequestDTO(
            account_number=acc3,
            principal=Decimal("500000.00"),
            apy_percentage=Decimal("5.25"),
            tenor_months=60,
            payout_frequency="ANNUALLY",
            rollover_option="PRINCIPAL_ONLY",
        )
    )

    cd4 = service.open_term_deposit(
        OpenCDRequestDTO(
            account_number=acc1,
            principal=Decimal("50000.00"),
            apy_percentage=Decimal("3.75"),
            tenor_months=6,
            payout_frequency="AT_MATURITY",
            rollover_option="PAYOUT_AND_CLOSE",
        )
    )

    # 3. Initialize UI
    window = MainWindow(banking_service=service)
    window.resize(1340, 840)
    window.show()

    # Navigate to CD Vault
    window.navigate_to("term_deposits")
    app.processEvents()

    cd_view = window.term_deposit_view
    assert cd_view is not None

    artifact_dir = Path(r"C:\Users\basut\.gemini\antigravity\brain\52f8a3f6-4525-4dfc-8a7f-79e53a868da8")

    # Capture Tab 1: Calculator & Issuance
    cd_view.tab_widget.setCurrentIndex(0)
    cd_view.funding_acc_input.setText(acc1)
    cd_view._on_lookup_clicked()
    cd_view.principal_input.setText("150000.00")
    # Select 24m pill
    cd_view._select_tenor_preset(24, Decimal("4.85"), cd_view._tenor_buttons[4])
    app.processEvents()

    calc_path = artifact_dir / "novabank_cd_vault_calculator.png"
    pixmap1 = window.grab()
    pixmap1.save(str(calc_path))
    print(f"Captured Tab 1: {calc_path}")

    # Capture Tab 2: Portfolio Desk
    cd_view.tab_widget.setCurrentIndex(1)
    # Refresh to pull all 4 CDs
    cds, total = service.list_term_deposits()
    cd_view._on_cds_loaded(cds, total)
    app.processEvents()

    portfolio_path = artifact_dir / "novabank_cd_vault_portfolio.png"
    pixmap2 = window.grab()
    pixmap2.save(str(portfolio_path))
    print(f"Captured Tab 2: {portfolio_path}")

    # Capture Tab 3: Certificate Details & Schedule Explorer
    cd_view.tab_widget.setCurrentIndex(2)
    cd_view._inspect_cd(cd2)
    app.processEvents()

    cert_path = artifact_dir / "novabank_cd_vault_certificate.png"
    pixmap3 = window.grab()
    pixmap3.save(str(cert_path))
    print(f"Captured Tab 3: {cert_path}")

    print("All 3 CD Vault screenshots captured successfully.")


if __name__ == "__main__":
    main()
