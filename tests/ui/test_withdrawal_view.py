"""Tests for WithdrawalView and TransactionViewModel cash withdrawal workflow."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.transaction_dto import TransactionDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.viewmodels.transaction_viewmodel import TransactionViewModel
from novabank.ui.views.withdrawal_view import WithdrawalView
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


def test_transaction_viewmodel_withdrawal_validation() -> None:
    """Verify validation rules including mathematical overdraft prevention."""
    vm = TransactionViewModel()

    # No account -> invalid
    is_valid, errors = vm.validate_withdrawal()
    assert is_valid is False
    assert "account" in errors

    # Mock active account with $200.00 balance
    from datetime import datetime, timezone

    from novabank.application.dto.account_dto import AccountDTO

    vm.source_account = AccountDTO(
        account_number="222233334444",
        holder_name="Jane Doe",
        dob=date(1991, 2, 2),
        address_line="456 Elm St",
        city="Boston",
        state="MA",
        country="USA",
        phone_number="5551234567",
        balance=Decimal("200.00"),
        currency="USD",
        is_active=True,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Empty amount -> invalid
    vm.amount_str = ""
    is_valid, errors = vm.validate_withdrawal()
    assert is_valid is False
    assert "amount" in errors

    # Below min ($0.50) -> invalid
    vm.amount_str = "0.50"
    is_valid, errors = vm.validate_withdrawal()
    assert is_valid is False
    assert "Minimum" in errors["amount"]

    # Exceeds counter limit ($60,000.00) -> invalid
    vm.amount_str = "60000.00"
    is_valid, errors = vm.validate_withdrawal()
    assert is_valid is False
    assert "maximum limit" in errors["amount"]

    # Overdraft: Requested $250.00 when balance is $200.00 -> invalid!
    vm.amount_str = "250.00"
    is_valid, errors = vm.validate_withdrawal()
    assert is_valid is False
    assert "Insufficient funds" in errors["amount"]

    # Valid withdrawal within balance ($50.00) -> valid!
    vm.amount_str = "50.00"
    is_valid, errors = vm.validate_withdrawal()
    assert is_valid is True
    assert len(errors) == 0


def test_transaction_viewmodel_withdrawal_preview() -> None:
    """Verify live withdrawal calculation preview."""
    vm = TransactionViewModel()
    from datetime import datetime, timezone

    from novabank.application.dto.account_dto import AccountDTO

    vm.source_account = AccountDTO(
        account_number="222233334444",
        holder_name="Jane Doe",
        dob=date(1991, 2, 2),
        address_line="456 Elm St",
        city="Boston",
        state="MA",
        country="USA",
        phone_number="5551234567",
        balance=Decimal("500.00"),
        currency="USD",
        is_active=True,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    vm.amount_str = "125.50"
    curr, with_amt, proj = vm.calculate_withdrawal_preview()
    assert curr == Decimal("500.00")
    assert with_amt == Decimal("125.50")
    assert proj == Decimal("374.50")


def test_withdrawal_view_overdraft_prevention_ui(qtbot, banking_service) -> None:
    """Verify entering amount exceeding balance disables submit button and alerts user."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Peter Parker",
        dob=date(1995, 8, 10),
        address_line="20 Ingram St",
        city="New York",
        state="NY",
        country="USA",
        phone_number="5551239876",
        initial_deposit=Decimal("150.00"),
    )
    acc_num = res.account.account_number

    view = WithdrawalView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.account_edit.setText(acc_num)

    # Enter overdraft amount ($200.00 when balance is $150.00)
    view.amount_edit.setText("200.00")

    assert view.submit_btn.isEnabled() is False
    assert view.amount_error.isVisible() is True
    assert "Insufficient funds" in view.amount_error.text()

    # Reduce to valid amount ($100.00)
    view.amount_edit.setText("100.00")
    assert view.submit_btn.isEnabled() is True
    assert view.amount_error.isVisible() is False


def test_withdrawal_view_execution_success(qtbot, banking_service, monkeypatch) -> None:
    """Verify successful withdrawal dispenses funds and displays receipt."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Tony Stark",
        dob=date(1975, 5, 29),
        address_line="10880 Malibu Point",
        city="Malibu",
        state="CA",
        country="USA",
        phone_number="5559991111",
        initial_deposit=Decimal("1000.00"),
    )
    acc_num = res.account.account_number

    view = WithdrawalView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    info_mock = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", info_mock)

    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.account_edit.setText(acc_num)

    view.amount_edit.setText("350.00")
    assert view.submit_btn.isEnabled() is True

    tx_events: list[TransactionDTO] = []
    view.vm.transaction_completed.connect(lambda dto: tx_events.append(dto))

    with qtbot.waitSignal(view.vm.transaction_completed, timeout=3000):
        view.submit_btn.click()

    assert len(tx_events) == 1
    tx = tx_events[0]
    assert tx.amount == Decimal("350.00")
    assert tx.balance_after == Decimal("650.00")

    # Receipt displayed
    assert info_mock.called is True
    receipt_args = info_mock.call_args[0]
    assert "WITHDRAWAL RECEIPT" in receipt_args[2]
    assert "-$350.00" in receipt_args[2]
    assert "$650.00" in receipt_args[2]

    # Verify DB update
    updated_acc = banking_service.get_account(acc_num)
    assert updated_acc is not None
    assert updated_acc.balance == Decimal("650.00")


def test_withdrawal_view_closed_account_blocked(qtbot, banking_service) -> None:
    """Verify closed accounts block withdrawal."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Steve Rogers",
        dob=date(1920, 7, 4),
        address_line="569 Leaman Place",
        city="Brooklyn",
        state="NY",
        country="USA",
        phone_number="5557773333",
        initial_deposit=Decimal("0.00"),
    )
    banking_service.close_account(res.account.account_number)

    view = WithdrawalView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.account_edit.setText(res.account.account_number)

    assert "Closed" in view.banner_badge.text()
    view.amount_edit.setText("50.00")

    assert view.submit_btn.isEnabled() is False
    assert view.account_error.isVisible() is True
    assert "inactive/closed" in view.account_error.text()
