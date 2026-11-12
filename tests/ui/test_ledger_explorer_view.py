"""UI tests for LedgerExplorerView and TransactionsHubView."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.views.ledger_explorer_view import LedgerExplorerView
from novabank.ui.views.transactions_hub_view import TransactionsHubView
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


def test_transactions_hub_tabs_count(qtbot, banking_service, task_runner):
    """Verify TransactionsHubView hosts all 4 operational tabs."""
    hub = TransactionsHubView(banking_service, task_runner)
    qtbot.addWidget(hub)
    hub.show()

    assert hub.tab_widget.count() == 4
    assert hub.tab_widget.tabText(0) == "Cash Deposit"
    assert hub.tab_widget.tabText(1) == "Cash Withdrawal"
    assert hub.tab_widget.tabText(2) == "Fund Transfer"
    assert "Ledger Explorer" in hub.tab_widget.tabText(3)
    assert "History" in hub.tab_widget.tabText(3)


def test_ledger_explorer_filtering_and_population(qtbot, banking_service, task_runner):
    """Verify ledger explorer table data retrieval and multi-column filtering."""
    acc = banking_service.open_account(
        holder_name="Explorer Customer",
        dob=date(1982, 3, 15),
        address_line="500 Ledger Lane",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5558889999",
        initial_deposit=Decimal("5000.00"),
    ).account

    banking_service.deposit(acc.account_number, Decimal("1000.00"), description="Bonus Deposit")
    banking_service.withdraw(acc.account_number, Decimal("250.00"), description="Counter Cash")

    view = LedgerExplorerView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    # Initial load has at least 3 transactions (initial deposit, deposit, withdrawal)
    qtbot.waitUntil(lambda: view.table.rowCount() >= 3, timeout=3000)
    assert view.table.columnCount() == 8
    assert "Bonus Deposit" in [
        view.table.item(r, 7).text() for r in range(view.table.rowCount()) if view.table.item(r, 7)
    ]

    # Filter by transaction type = WITHDRAWAL
    view.type_combo.setCurrentText("WITHDRAWAL")
    view._on_search_clicked()

    qtbot.waitUntil(lambda: view.table.rowCount() == 1, timeout=3000)
    assert view.table.item(0, 3).text() == "WITHDRAWAL"
    assert view.table.item(0, 4).text() == "DEBIT"

    # Reset filter
    view._on_reset_clicked()
    qtbot.waitUntil(lambda: view.table.rowCount() >= 3, timeout=3000)


def test_ledger_explorer_csv_export(qtbot, banking_service, task_runner, tmp_path, monkeypatch):
    """Verify CSV export workflow in LedgerExplorerView."""
    acc = banking_service.open_account(
        holder_name="CSV Exporter",
        dob=date(1988, 9, 9),
        address_line="777 Data Drive",
        city="Atlanta",
        state="GA",
        country="USA",
        phone_number="5551113333",
        initial_deposit=Decimal("3000.00"),
    ).account

    view = LedgerExplorerView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    qtbot.waitUntil(lambda: len(view.current_transactions) >= 1, timeout=3000)

    export_file = tmp_path / "test_ledger_export.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args, **kwargs: (str(export_file), "CSV"))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    view._on_export_csv_clicked()

    assert export_file.exists()
    content = export_file.read_text(encoding="utf-8")
    assert "Date,Reference,Type,Description,Debit,Credit,Balance,Currency" in content
    assert "Initial Deposit" in content
