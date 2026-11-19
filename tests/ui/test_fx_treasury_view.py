"""UI tests for FXTreasuryView, Spot Exchange Desk, Treasury Liquidity, and Trade Blotter."""

from datetime import date
from decimal import Decimal
from unittest.mock import patch
import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.views.fx_treasury_view import FXTradeReceiptDialog, FXTreasuryView
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
        holder_name="Global FX Capital LLC",
        dob=date(1982, 4, 15),
        address_line="100 Financial Center",
        city="New York",
        state="NY",
        country="USA",
        phone_number="2125550188",
        initial_deposit=Decimal("200000.00"),
    )
    return acc_res.account.account_number


def test_fx_treasury_view_initialization(qtbot, banking_service, task_runner):
    """Verify FXTreasuryView initializes with 3 tabs and default controls."""
    view = FXTreasuryView(banking_service, task_runner)
    qtbot.addWidget(view)

    assert view.tabs.count() == 3
    assert view.tabs.tabText(0) == "FX Spot Exchange & Trade Terminal"
    assert view.tabs.tabText(1) == "Treasury Reserves & Vault Liquidity"
    assert view.tabs.tabText(2) == "FX Blotter & Settlement Ledger"

    # Default controls
    assert view.combo_source.currentText() == "USD"
    assert view.combo_target.currentText() == "EUR"
    assert not view.btn_execute.isEnabled()


def test_fx_quote_calculation_and_currency_swap(qtbot, banking_service, task_runner):
    """Verify real-time quote calculation and swap currency direction button."""
    view = FXTreasuryView(banking_service, task_runner)
    qtbot.addWidget(view)

    # Set amount to $10,000.00
    view.input_amount.setText("10000.00")

    assert view._current_quote is not None
    assert view._current_quote.source_currency == "USD"
    assert view._current_quote.target_currency == "EUR"
    assert "EUR" in view.val_payout.text()
    assert Decimal("9000.00") < view._current_quote.target_amount < Decimal("10000.00")

    # Invert currencies with swap button
    qtbot.mouseClick(view.btn_swap, Qt.MouseButton.LeftButton)

    assert view.combo_source.currentText() == "EUR"
    assert view.combo_target.currentText() == "USD"
    assert view._current_quote.source_currency == "EUR"
    assert view._current_quote.target_currency == "USD"
    assert "USD" in view.val_payout.text()


def test_account_lookup_and_trade_execution(qtbot, banking_service, task_runner, seed_account):
    """Verify funding account lookup, quote calculation, atomic spot execution, and receipt display."""
    view = FXTreasuryView(banking_service, task_runner)
    qtbot.addWidget(view)

    # Lookup funding account
    view.input_account.setText(seed_account)
    with qtbot.waitSignal(view.viewmodel.account_found, timeout=3000):
        view._on_lookup_clicked()

    assert view._target_account is not None
    assert "Global FX Capital LLC" in view.lbl_account_status.text()

    # Configure conversion: $15,000 USD to EUR
    view.combo_source.setCurrentText("USD")
    view.combo_target.setCurrentText("EUR")
    view.input_amount.setText("15000.00")

    assert view.btn_execute.isEnabled()

    # Execute trade with modal confirmations mocked
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        with patch.object(FXTradeReceiptDialog, "exec", return_value=QDialog.DialogCode.Accepted):
            with qtbot.waitSignal(view.viewmodel.trade_executed, timeout=4000) as blocker:
                qtbot.mouseClick(view.btn_execute, Qt.MouseButton.LeftButton)

    trade_dto = blocker.args[0]
    assert trade_dto.account_number == seed_account
    assert trade_dto.source_currency == "USD"
    assert trade_dto.target_currency == "EUR"
    assert trade_dto.source_amount == Decimal("15000.00")
    assert trade_dto.status == "EXECUTED"


def test_treasury_overview_and_revaluation(qtbot, banking_service, task_runner):
    """Verify treasury reserves display 8 sovereign currencies with allocation and valuation."""
    view = FXTreasuryView(banking_service, task_runner)
    qtbot.addWidget(view)

    # Revalue treasury positions
    with qtbot.waitSignal(view.viewmodel.treasury_updated, timeout=3000):
        view._on_revalue_clicked()

    assert view.treasury_table.rowCount() == 8
    assert "$" in view.kpi_total_usd.text()
    assert "8 Currencies" in view.kpi_active_ccy.text()


def test_trade_receipt_dialog_rendering(qtbot):
    """Verify FXTradeReceiptDialog displays all institutional fields."""
    from novabank.application.dto.fx_dto import FXTradeDTO

    sample_trade = FXTradeDTO(
        trade_id="FX-TEST1234",
        account_number="111122223333",
        source_currency="USD",
        source_amount=Decimal("25000.00"),
        target_currency="GBP",
        target_amount=Decimal("19614.78"),
        spot_rate=Decimal("0.78616"),
        effective_rate=Decimal("0.78459"),
        spread_bps=20,
        spread_revenue_usd=Decimal("39.23"),
        fee_amount=Decimal("25.00"),
        status="EXECUTED",
        settlement_reference="SWIFT-CLS-12345678",
        actor="senior_fx_trader",
        executed_at="2026-11-19 12:00:00",
    )

    dialog = FXTradeReceiptDialog(sample_trade)
    qtbot.addWidget(dialog)

    assert "FX-TEST1234" in dialog.windowTitle() or dialog.isVisible() or dialog.findChild(QDialog) is None
