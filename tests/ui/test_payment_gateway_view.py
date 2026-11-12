"""UI tests for PaymentGatewayView and Virtual Terminal."""

import tempfile
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.payment_dto import PaymentRequestDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.views.payment_gateway_view import (
    PaymentGatewayView,
    PaymentReceiptDialog,
    RefundConfirmationDialog,
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
        holder_name="Merchant Enterprise Corp",
        dob=date(1980, 1, 1),
        address_line="100 Financial Center",
        city="New York",
        state="NY",
        country="USA",
        phone_number="2125550199",
        initial_deposit=Decimal("1000.00"),
    )
    return acc_res.account.account_number


def test_payment_gateway_view_initialization(qtbot, banking_service, task_runner):
    """Verify PaymentGatewayView initializes with 2 tabs and default state."""
    view = PaymentGatewayView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    assert view.tab_widget.count() == 2
    assert "Virtual Terminal" in view.tab_widget.tabText(0)
    assert "Gateway Ledger" in view.tab_widget.tabText(1)
    assert view.val_gross.text() == "$0.00"
    assert view.val_net.text() == "$0.00"


def test_fee_calculation_and_channel_switching(qtbot, banking_service, task_runner):
    """Verify live interchange fee preview for various payment rails."""
    view = PaymentGatewayView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    # Enter amount 100.00 on CARD (default: 2.9% + $0.30 = $3.20 fee)
    view.amt_input.setText("100.00")
    assert view.val_gross.text() == "$100.00"
    assert view.val_fee.text() == "-$3.20"
    assert view.val_net.text() == "$96.80"

    # Switch to ACH (0.8% = $0.80 fee)
    view.channel_combo.setCurrentIndex(1)
    assert view.val_fee.text() == "-$0.80"
    assert view.val_net.text() == "$99.20"

    # Switch to FedNow ($0.25 flat)
    view.channel_combo.setCurrentIndex(2)
    assert view.val_fee.text() == "-$0.25"
    assert view.val_net.text() == "$99.75"

    # Switch to Wire ($15.00 flat)
    view.channel_combo.setCurrentIndex(3)
    assert view.val_fee.text() == "-$15.00"
    assert view.val_net.text() == "$85.00"


def test_card_brand_detection(qtbot, banking_service, task_runner):
    """Verify real-time card scheme / brand detection pill."""
    view = PaymentGatewayView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    # Visa
    view.card_num_input.setText("4242 4242")
    assert view.card_brand_badge.isVisible()
    assert view.card_brand_badge.text() == "VISA"

    # Mastercard
    view.card_num_input.setText("5100 1234")
    assert view.card_brand_badge.isVisible()
    assert view.card_brand_badge.text() == "MASTERCARD"

    # Amex
    view.card_num_input.setText("3782 8224")
    assert view.card_brand_badge.isVisible()
    assert view.card_brand_badge.text() == "AMEX"

    # Clear
    view.card_num_input.setText("")
    assert not view.card_brand_badge.isVisible()


def test_account_lookup_feedback(qtbot, banking_service, task_runner, seed_account):
    """Verify asynchronous account verification banner on 12-digit input."""
    view = PaymentGatewayView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.acc_input.setText(seed_account)

    assert "Verified: Merchant Enterprise Corp" in view.acc_status_banner.text()
    assert "$1,000.00" in view.acc_status_banner.text()


def test_submit_payment_workflow(qtbot, banking_service, task_runner, seed_account, monkeypatch):
    """Verify payment authorization and settlement via virtual terminal."""
    monkeypatch.setattr(PaymentReceiptDialog, "exec", lambda self: 1)

    view = PaymentGatewayView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    view.acc_input.setText(seed_account)
    view.amt_input.setText("200.00")
    view.card_num_input.setText("4242424242424242")
    view.card_holder_input.setText("Corporate Buyer LLC")
    view.card_exp_input.setText("12/29")
    view.card_cvv_input.setText("456")
    view.desc_input.setText("Payment for invoice #8812")

    with qtbot.waitSignal(view.vm.payment_completed, timeout=4000) as blocker:
        view.btn_submit.click()

    settled_dto = blocker.args[0]
    assert settled_dto.status == "SETTLED"
    assert settled_dto.amount == Decimal("200.00")
    # Gross $200 - Fee (2.9%+$0.30 = $6.10) = Net $193.90
    assert settled_dto.fee == Decimal("6.10")
    assert settled_dto.net_amount == Decimal("193.90")

    # Verify merchant account credited net
    acc = banking_service.get_account(seed_account)
    assert acc.balance == Decimal("1193.90")


def test_gateway_ledger_population_and_refund(qtbot, banking_service, task_runner, seed_account, monkeypatch):
    """Verify gateway ledger display, status badges, and refund execution."""
    monkeypatch.setattr(RefundConfirmationDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(RefundConfirmationDialog, "get_reason", lambda self: "Item returned")
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    view = PaymentGatewayView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    # Ingest a card payment directly through service
    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="CARD",
        amount=Decimal("100.00"),
        merchant_name="Acme Wholesale",
        card_number="4242424242424242",
        card_exp="11/28",
        card_cvv="333",
    )
    settled = banking_service.process_gateway_payment(req)
    assert banking_service.get_account(seed_account).balance == Decimal("1096.80")

    # Switch to ledger tab
    with qtbot.waitSignal(view.vm.payments_loaded, timeout=3000):
        view.tab_widget.setCurrentIndex(1)

    assert view.table.rowCount() == 1
    assert view.table.item(0, 0).text() == settled.payment_id
    assert view.table.item(0, 3).text() == "CARD"
    assert view.table.item(0, 6).text() == "$100.00"
    assert view.table.item(0, 7).text() == "-$3.20"
    assert view.table.item(0, 8).text() == "$96.80"

    # Simulate refund
    with qtbot.waitSignal(view.vm.refund_completed, timeout=4000):
        view._on_refund_requested(settled)

    # Balance reversed
    assert banking_service.get_account(seed_account).balance == Decimal("1000.00")

    # Refresh ledger and verify REFUNDED status
    with qtbot.waitSignal(view.vm.payments_loaded, timeout=3000):
        view.refresh_ledger()

    updated = banking_service.get_gateway_payment(settled.payment_id)
    assert updated.status == "REFUNDED"


def test_gateway_csv_export(qtbot, banking_service, task_runner, seed_account, monkeypatch):
    """Verify CSV export from PaymentGatewayView."""
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    view = PaymentGatewayView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="CARD",
        amount=Decimal("75.00"),
        merchant_name="Export Shop",
        card_number="4242424242424242",
        card_exp="10/28",
        card_cvv="111",
    )
    settled = banking_service.process_gateway_payment(req)

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tf:
        csv_file = tf.name

    with qtbot.waitSignal(view.vm.csv_exported, timeout=3000):
        view.vm.export_csv(csv_file, [settled])

    with open(csv_file, "r", encoding="utf-8") as f:
        content = f.read()

    assert "Payment ID,Date,Account,Channel,Merchant" in content
    assert "Export Shop" in content
    assert "75.00" in content
