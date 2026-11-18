"""UI tests for LoanDeskView, Amortization Simulator, and Portfolio Servicing."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.loan_dto import LoanOriginationRequestDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.views.loan_desk_view import (
    LoanDeskView,
    LoanDisbursementReceiptDialog,
    LoanRepaymentDialog,
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
def seed_borrower(banking_service):
    acc_res = banking_service.open_account(
        holder_name="Nexus Technologies LLC",
        dob=date(1988, 3, 14),
        address_line="800 Enterprise Parkway",
        city="Austin",
        state="TX",
        country="USA",
        phone_number="5125550144",
        initial_deposit=Decimal("25000.00"),
    )
    return acc_res.account.account_number


def test_loan_desk_view_initialization(qtbot, banking_service, task_runner):
    """Verify LoanDeskView initializes with 3 institutional tabs and controls."""
    view = LoanDeskView(banking_service, task_runner)
    qtbot.addWidget(view)

    assert view.tab_widget.count() == 3
    assert view.tab_widget.tabText(0) == "Origination & Simulator"
    assert view.tab_widget.tabText(1) == "Loan Portfolio & Repayments"
    assert view.tab_widget.tabText(2) == "Amortization Schedule Explorer"

    # Default inputs
    assert view.principal_input.text() == "100,000.00"
    assert view.apr_input.text() == "7.50"
    assert view.term_spinbox.value() == 36
    assert view.btn_originate.isEnabled() is False


def test_loan_simulation_and_term_pills(qtbot, banking_service, task_runner):
    """Verify clicking term pills recalculates EMI and updates spinbox."""
    view = LoanDeskView(banking_service, task_runner)
    qtbot.addWidget(view)

    # Click '12m' pill
    btn_12m = view.pill_buttons[12]
    qtbot.mouseClick(btn_12m, Qt.MouseButton.LeftButton)

    assert view.term_spinbox.value() == 12
    assert view.quote_term_val.text() == "12 Months"
    assert view.preview_table.rowCount() == 6


def test_borrower_lookup_and_origination_flow(qtbot, banking_service, task_runner, seed_borrower):
    """Test full interactive flow: borrower lookup -> quote -> disburse -> portfolio update."""
    view = LoanDeskView(banking_service, task_runner)
    qtbot.addWidget(view)

    # Enter account and look up
    view.borrower_acc_input.setText(seed_borrower)
    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view._on_lookup_clicked()

    assert view.vm.target_account is not None
    assert view.btn_originate.isEnabled() is True

    # Underwrite & disburse
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(LoanDisbursementReceiptDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            with qtbot.waitSignal(view.vm.loans_loaded, timeout=3000):
                view.btn_originate.click()

    # Active tab should have switched to Portfolio tab
    assert view.tab_widget.currentIndex() == 1
    # Check that portfolio table has 1 row
    assert view.portfolio_table.rowCount() == 1
    assert view.portfolio_table.item(0, 1).text() == seed_borrower


def test_portfolio_table_selection_and_repayment_flow(qtbot, banking_service, task_runner, seed_borrower):
    """Test selecting loan, opening repayment dialog, and settling installment."""
    # Seed an active loan directly
    req = LoanOriginationRequestDTO(
        account_number=seed_borrower,
        loan_type="COMMERCIAL_EQUIPMENT",
        principal=Decimal("12000.00"),
        apr_percentage=Decimal("6.00"),
        term_months=12,
        purpose="Testing Repayment Desk",
    )
    loan_dto = banking_service.originate_loan(req)

    view = LoanDeskView(banking_service, task_runner)
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.vm.loans_loaded, timeout=3000):
        view.refresh_portfolio()

    assert view.portfolio_table.rowCount() == 1
    view.portfolio_table.selectRow(0)

    assert view.btn_repay.isEnabled() is True
    assert view.btn_view_schedule.isEnabled() is True

    # Execute repayment
    with patch.object(LoanRepaymentDialog, "exec", return_value=QDialog.DialogCode.Accepted):
        with patch.object(QMessageBox, "information"):
            with qtbot.waitSignal(view.vm.repayment_completed, timeout=3000):
                view.btn_repay.click()


def test_schedule_explorer_and_csv_export(qtbot, banking_service, task_runner, seed_borrower):
    """Test switching to Schedule Explorer and viewing full table."""
    req = LoanOriginationRequestDTO(
        account_number=seed_borrower,
        loan_type="WORKING_CAPITAL",
        principal=Decimal("6000.00"),
        apr_percentage=Decimal("5.00"),
        term_months=6,
    )
    loan_dto = banking_service.originate_loan(req)

    view = LoanDeskView(banking_service, task_runner)
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.vm.schedule_loaded, timeout=3000):
        view.vm.load_loan_schedule(loan_dto.loan_id)

    assert view.schedule_table.rowCount() == 6
    assert view.btn_export_csv.isEnabled() is True

    # Test CSV export delegation
    with patch.object(view.vm, "export_schedule_csv") as mock_export:
        with patch("PySide6.QtWidgets.QFileDialog.getSaveFileName", return_value=("test_sched.csv", "CSV")):
            view.btn_export_csv.click()
            mock_export.assert_called_once_with(loan_dto.loan_id, destination_path="test_sched.csv")
