"""Tests for StatementView and StatementViewModel interactive statement features."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import QDate
from PySide6.QtWidgets import QLabel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.statement_dto import AccountStatementDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.viewmodels.statement_viewmodel import StatementViewModel
from novabank.ui.views.statement_view import StatementView
from novabank.ui.workers.task_runner import TaskRunner


@pytest.fixture
def banking_service():
    """Create in-memory banking service configured with StaticPool."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return BankingService(session_factory=session_factory)


def test_statement_viewmodel_presets() -> None:
    """Verify preset calculations for Today, Last 7 Days, This Month, YTD, and Custom."""
    vm = StatementViewModel()
    ref_date = date(2026, 10, 25)

    # 1. Today
    vm.select_preset(StatementViewModel.PRESET_TODAY, reference_date=ref_date)
    assert vm.start_date == date(2026, 10, 25)
    assert vm.end_date == date(2026, 10, 25)
    assert vm.selected_preset == StatementViewModel.PRESET_TODAY

    # 2. Last 7 Days
    vm.select_preset(StatementViewModel.PRESET_LAST_7_DAYS, reference_date=ref_date)
    assert vm.start_date == date(2026, 10, 18)
    assert vm.end_date == date(2026, 10, 25)

    # 3. This Month
    vm.select_preset(StatementViewModel.PRESET_THIS_MONTH, reference_date=ref_date)
    assert vm.start_date == date(2026, 10, 1)
    assert vm.end_date == date(2026, 10, 25)

    # 4. Year to Date (YTD)
    vm.select_preset(StatementViewModel.PRESET_YTD, reference_date=ref_date)
    assert vm.start_date == date(2026, 1, 1)
    assert vm.end_date == date(2026, 10, 25)

    # 5. All Time
    vm.select_preset(StatementViewModel.PRESET_ALL_TIME, reference_date=ref_date)
    assert vm.start_date is None
    assert vm.end_date == date(2026, 10, 25)

    # 6. Custom Range Valid
    assert vm.set_custom_date_range(date(2026, 3, 1), date(2026, 3, 31)) is True
    assert vm.start_date == date(2026, 3, 1)
    assert vm.end_date == date(2026, 3, 31)
    assert vm.selected_preset == StatementViewModel.PRESET_CUSTOM

    # 7. Custom Range Invalid (start > end)
    error_events: list[str] = []
    vm.error_occurred.connect(lambda msg: error_events.append(msg))
    assert vm.set_custom_date_range(date(2026, 5, 10), date(2026, 5, 1)) is False
    assert len(error_events) == 1
    assert "cannot be after end date" in error_events[0]


def test_statement_view_ui_initialization(qtbot) -> None:
    """Verify StatementView widgets, columns, presets, and initial state."""
    view = StatementView()
    qtbot.addWidget(view)
    view.show()

    assert view.table.columnCount() == 7
    assert view.table.horizontalHeaderItem(0).text() == "Date & Time"
    assert view.table.horizontalHeaderItem(1).text() == "Reference ID"
    assert view.table.horizontalHeaderItem(2).text() == "Type"
    assert view.table.horizontalHeaderItem(3).text() == "Description"
    assert view.table.horizontalHeaderItem(4).text() == "Debit (-)"
    assert view.table.horizontalHeaderItem(5).text() == "Credit (+)"
    assert view.table.horizontalHeaderItem(6).text() == "Running Balance"

    assert view.btn_this_month.isChecked() is True
    assert view.custom_container.isEnabled() is False


def test_statement_view_lookup_and_table_population(qtbot, banking_service) -> None:
    """Verify looking up account populates statement table, KPI cards, and reconciliation badge."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Diana Prince",
        dob=date(1990, 8, 12),
        address_line="100 Gateway Blvd",
        city="Paradise Island",
        state="FL",
        country="USA",
        phone_number="5558889999",
        initial_deposit=Decimal("1500.00"),
    )
    acc_num = res.account.account_number

    # Execute transactions
    banking_service.deposit(acc_num, Decimal("500.00"), description="Consulting bonus")
    banking_service.withdraw(acc_num, Decimal("250.00"), description="Flight ticket")

    view = StatementView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    # Select All Time to encompass all transactions regardless of test execution date
    view.btn_all_time.click()

    with qtbot.waitSignal(view.vm.statement_loaded, timeout=5000) as blocker:
        view.account_edit.setText(acc_num)

    statement: AccountStatementDTO = blocker.args[0]
    assert statement.transaction_count == 3
    assert statement.closing_balance == Decimal("1750.00")
    assert statement.is_reconciled() is True

    # Assert UI updates
    assert view.reconciliation_badge.isVisible() is True
    assert view.table.rowCount() == 3

    # Check KPI Card values
    card_open_val = view.card_opening.findChild(QLabel, "kpi_value").text()
    card_cred_val = view.card_credits.findChild(QLabel, "kpi_value").text()
    card_deb_val = view.card_debits.findChild(QLabel, "kpi_value").text()
    card_close_val = view.card_closing.findChild(QLabel, "kpi_value").text()

    assert "$0.00 USD" in card_open_val
    assert "+$2,000.00 USD" in card_cred_val
    assert "-$250.00 USD" in card_deb_val
    assert "$1,750.00 USD" in card_close_val

    # Check table items
    # Row 0: Initial Deposit $1500.00
    assert view.table.item(0, 2).text() == "DEPOSIT"
    assert view.table.item(0, 5).text() == "+$1,500.00"
    assert view.table.item(0, 6).text() == "$1,500.00"

    # Row 1: Deposit bonus $500.00
    assert view.table.item(1, 2).text() == "DEPOSIT"
    assert view.table.item(1, 5).text() == "+$500.00"
    assert view.table.item(1, 6).text() == "$2,000.00"

    # Row 2: Withdrawal $250.00
    assert view.table.item(2, 2).text() == "WITHDRAWAL"
    assert view.table.item(2, 4).text() == "-$250.00"
    assert view.table.item(2, 6).text() == "$1,750.00"


def test_statement_view_custom_range_filter(qtbot, banking_service) -> None:
    """Verify switching to Custom Range enables pickers and applies date filter."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Barry Allen",
        dob=date(1992, 3, 15),
        address_line="500 Central Ave",
        city="Central City",
        state="MO",
        country="USA",
        phone_number="5553332211",
        initial_deposit=Decimal("100.00"),
    )
    acc_num = res.account.account_number

    view = StatementView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    # Load initial statement
    with qtbot.waitSignal(view.vm.statement_loaded, timeout=5000):
        view.account_edit.setText(acc_num)

    # Click Custom Range
    view.btn_custom.click()
    assert view.custom_container.isEnabled() is True

    # Set custom range for future date with no transactions
    view.start_date_edit.setDate(QDate(2099, 1, 1))
    view.end_date_edit.setDate(QDate(2099, 1, 31))

    with qtbot.waitSignal(view.vm.statement_loaded, timeout=5000) as blocker:
        view.apply_custom_btn.click()

    stmt: AccountStatementDTO = blocker.args[0]
    assert stmt.transaction_count == 0
    assert stmt.opening_balance == Decimal("100.00")
    assert stmt.closing_balance == Decimal("100.00")
    assert view.table.rowCount() == 0


def test_statement_view_non_existent_account(qtbot, banking_service) -> None:
    """Verify lookup for non-existent account displays error and clears table."""
    task_runner = TaskRunner()
    view = StatementView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    with qtbot.waitSignal(view.vm.account_lookup_failed, timeout=5000):
        view.account_edit.setText("999988887777")

    assert view.account_error.isVisible() is True
    assert "does not exist" in view.account_error.text()
    assert view.table.rowCount() == 0
    assert view.reconciliation_badge.isVisible() is False


def test_statement_view_export_csv_button_lifecycle(qtbot, banking_service) -> None:
    """Verify export button is enabled only when a valid statement is loaded."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Clark Kent",
        dob=date(1988, 6, 18),
        address_line="344 Clinton St",
        city="Metropolis",
        state="NY",
        country="USA",
        phone_number="5551239876",
        initial_deposit=Decimal("500.00"),
    )
    acc_num = res.account.account_number

    view = StatementView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    # Initial state: button is disabled
    assert view.btn_export_csv.isEnabled() is False

    # Load account statement
    with qtbot.waitSignal(view.vm.statement_loaded, timeout=5000):
        view.account_edit.setText(acc_num)

    # Now enabled
    assert view.btn_export_csv.isEnabled() is True

    # Failed lookup disables button
    with qtbot.waitSignal(view.vm.account_lookup_failed, timeout=5000):
        view.account_edit.setText("000000000000")

    assert view.btn_export_csv.isEnabled() is False


def test_statement_view_export_csv_execution(qtbot, banking_service, tmp_path, monkeypatch) -> None:
    """Verify clicking export CSV invokes file dialog and produces valid CSV file on disk."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Bruce Wayne",
        dob=date(1980, 2, 19),
        address_line="1007 Mountain Drive",
        city="Gotham",
        state="NJ",
        country="USA",
        phone_number="5559998888",
        initial_deposit=Decimal("10000.00"),
    )
    acc_num = res.account.account_number
    banking_service.withdraw(acc_num, Decimal("1500.00"), description="Batmobile repair")

    view = StatementView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    view.btn_all_time.click()
    with qtbot.waitSignal(view.vm.statement_loaded, timeout=5000):
        view.account_edit.setText(acc_num)

    target_csv = tmp_path / "bruce_statement.csv"

    # Mock QFileDialog.getSaveFileName to return target_csv without opening native file dialog
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target_csv), "CSV Files (*.csv)"),
    )
    # Mock QMessageBox.information to prevent blocking modal
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    with qtbot.waitSignal(view.vm.statement_exported, timeout=5000) as blocker:
        view.btn_export_csv.click()

    assert blocker.args[0] == str(target_csv.resolve())
    assert target_csv.exists()

    content = target_csv.read_text(encoding="utf-8")
    assert "NovaBank Official Account Statement" in content
    assert "Bruce Wayne" in content
    assert "Batmobile repair" in content
    assert "10000.00" in content
    assert "8500.00" in content


def test_statement_viewmodel_export_csv_without_loaded_statement() -> None:
    """Verify export failure signal when no statement is loaded."""
    vm = StatementViewModel()
    failed_msgs: list[str] = []
    vm.export_failed.connect(lambda msg: failed_msgs.append(msg))

    vm.export_statement_csv("/path/dummy.csv")
    assert len(failed_msgs) == 1
    assert "No active statement loaded" in failed_msgs[0]


def test_statement_view_export_pdf_execution(qtbot, banking_service, tmp_path, monkeypatch) -> None:
    """Verify clicking export PDF opens save dialog and writes valid PDF document."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Arthur Curry",
        dob=date(1986, 1, 29),
        address_line="Amnesty Bay Lighthouse",
        city="Amnesty Bay",
        state="ME",
        country="USA",
        phone_number="5557778899",
        initial_deposit=Decimal("7500.00"),
    )
    acc_num = res.account.account_number

    view = StatementView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    # Initial state: PDF button disabled
    assert view.btn_export_pdf.isEnabled() is False

    with qtbot.waitSignal(view.vm.statement_loaded, timeout=5000):
        view.account_edit.setText(acc_num)

    assert view.btn_export_pdf.isEnabled() is True

    target_pdf = tmp_path / "arthur_statement.pdf"

    from PySide6.QtWidgets import QFileDialog, QMessageBox

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(target_pdf), "PDF Documents (*.pdf)"),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    with qtbot.waitSignal(view.vm.statement_exported, timeout=5000) as blocker:
        view.btn_export_pdf.click()

    assert blocker.args[0] == str(target_pdf.resolve())
    assert target_pdf.exists()
    assert target_pdf.read_bytes().startswith(b"%PDF-")
