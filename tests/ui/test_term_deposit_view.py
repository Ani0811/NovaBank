"""UI tests for TermDepositView, CD Vault Calculator, and Portfolio Servicing."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.term_deposit_dto import OpenCDRequestDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.views.term_deposit_view import (
    CDEarlyRedemptionDialog,
    CDIssuanceReceiptDialog,
    TermDepositView,
)
from novabank.ui.workers.task_runner import TaskRunner


@pytest.fixture
def banking_service():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return BankingService(session_factory=session_factory)


@pytest.fixture
def task_runner():
    return TaskRunner()


@pytest.fixture
def seed_account(banking_service):
    acc_res = banking_service.open_account(
        holder_name="Meridian Capital Holdings",
        dob=date(1985, 6, 20),
        address_line="500 Wall Street",
        city="New York",
        state="NY",
        country="USA",
        phone_number="2125550199",
        initial_deposit=Decimal("150000.00"),
    )
    return acc_res.account.account_number


def test_term_deposit_view_initialization(qtbot, banking_service, task_runner):
    """Verify TermDepositView initializes with 3 tabs, default parameters, and live yield simulation."""
    view = TermDepositView(banking_service, task_runner)
    qtbot.addWidget(view)

    assert view.tab_widget.count() == 3
    assert view.tab_widget.tabText(0) == "CD Vault Calculator & Issuance"
    assert view.tab_widget.tabText(1) == "Active CD Vault Portfolio"
    assert view.tab_widget.tabText(2) == "Certificate Details & Accrual Schedule"

    # Default parameters
    assert view.principal_input.text() == "10000.00"
    assert view.tenor_spin.value() == 12
    assert view.apy_input.text() == "4.50"
    assert view.projection_table.rowCount() == 12
    assert "$10,450.00" in view.hero_payout_val.text()


def test_tenor_preset_pills_interaction(qtbot, banking_service, task_runner):
    """Verify clicking tenor pills automatically updates spinbox, APY, and re-computes compound yield."""
    view = TermDepositView(banking_service, task_runner)
    qtbot.addWidget(view)

    # Click 24 Months / 4.85% pill (index 4)
    pill_24m = view._tenor_buttons[4]
    qtbot.mouseClick(pill_24m, Qt.MouseButton.LeftButton)

    assert view.tenor_spin.value() == 24
    assert view.apy_input.text() == "4.85"
    assert view.projection_table.rowCount() == 24
    assert "$10,993.52" in view.hero_payout_val.text()

    # Click 6 Months / 3.75% pill (index 1)
    pill_6m = view._tenor_buttons[1]
    qtbot.mouseClick(pill_6m, Qt.MouseButton.LeftButton)

    assert view.tenor_spin.value() == 6
    assert view.apy_input.text() == "3.75"
    assert view.projection_table.rowCount() == 6
    assert "$10,185.77" in view.hero_payout_val.text()


def test_funding_account_lookup_and_cd_issuance(qtbot, banking_service, task_runner, seed_account):
    """Test full workflow: lookup funding account -> configure CD -> issue CD -> update portfolio."""
    view = TermDepositView(banking_service, task_runner)
    qtbot.addWidget(view)

    # Enter account and look up
    view.funding_acc_input.setText(seed_account)
    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view._on_lookup_clicked()

    assert view.vm.target_account is not None
    assert "Meridian Capital Holdings" in view.account_status_label.text()

    # Set parameters: $25,000 for 12 months at 4.50%
    view._set_principal("25000.00")

    # Issue CD (mock dialog exec to prevent blocking)
    with patch.object(CDIssuanceReceiptDialog, "exec", return_value=QDialog.DialogCode.Accepted):
        with qtbot.waitSignal(view.vm.cd_opened, timeout=3000):
            view._on_issue_cd_clicked()

    # Wait for portfolio reload
    with qtbot.waitSignal(view.vm.cds_loaded, timeout=3000):
        view.refresh_portfolio()

    # Check portfolio is updated
    assert view.tab_widget.currentIndex() == 1  # Switched to portfolio tab
    assert view.portfolio_table.rowCount() >= 1

    cd_item = view.portfolio_table.item(0, 0)
    assert cd_item is not None
    assert cd_item.text().startswith("CD-")

    # Verify account balance was atomically debited: 150,000 - 25,000 = 125,000
    acc = banking_service.get_account(seed_account)
    assert acc.balance == Decimal("125000.00")


def test_certificate_inspection_tab_and_accrual_schedule(qtbot, banking_service, task_runner, seed_account):
    """Test inspecting a Certificate of Deposit in Tab 3 with its full accrual schedule."""
    # Pre-open a CD
    cd_dto = banking_service.open_term_deposit(
        OpenCDRequestDTO(
            account_number=seed_account,
            principal=Decimal("50000.00"),
            apy_percentage=Decimal("5.00"),
            tenor_months=36,
            payout_frequency="AT_MATURITY",
            rollover_option="PAYOUT_AND_CLOSE",
        )
    )

    view = TermDepositView(banking_service, task_runner)
    qtbot.addWidget(view)

    # Inspect the CD
    view._inspect_cd(cd_dto)

    assert view.tab_widget.currentIndex() == 2
    assert view.doc_val_cert_num.text() == cd_dto.certificate_number
    assert view.doc_val_principal.text() == "$50,000.00"
    assert view.doc_val_apy.text() == "5.00%"
    assert view.schedule_table.rowCount() == 36


def test_early_redemption_preview_dialog(qtbot, banking_service, task_runner, seed_account):
    """Test previewing regulatory early breakage penalty and liquidating CD."""
    cd_dto = banking_service.open_term_deposit(
        OpenCDRequestDTO(
            account_number=seed_account,
            principal=Decimal("20000.00"),
            apy_percentage=Decimal("4.50"),
            tenor_months=12,
        )
    )

    view = TermDepositView(banking_service, task_runner)
    qtbot.addWidget(view)

    # Wrap both dialog and message box in patch to prevent GUI blocking
    with patch.object(CDEarlyRedemptionDialog, "exec", return_value=QDialog.DialogCode.Accepted), \
         patch.object(QMessageBox, "information"):
        with qtbot.waitSignal(view.vm.redemption_completed, timeout=3000):
            view._on_break_cd_clicked(cd_dto.id)

    # Verify status changed to PREMATURELY_CLOSED
    updated_cd = banking_service.get_term_deposit(cd_dto.id)
    assert updated_cd.status == "PREMATURELY_CLOSED"
