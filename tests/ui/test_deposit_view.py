"""Tests for DepositView and TransactionViewModel cash deposit workflow."""

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
from novabank.ui.views.deposit_view import DepositView
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


def test_transaction_viewmodel_deposit_validation() -> None:
    """Verify field validation rules for cash deposit."""
    vm = TransactionViewModel()

    # No account verified -> invalid
    is_valid, errors = vm.validate_deposit()
    assert is_valid is False
    assert "account" in errors

    # Mock an active source account
    from datetime import datetime, timezone

    from novabank.application.dto.account_dto import AccountDTO

    vm.source_account = AccountDTO(
        account_number="111122223333",
        holder_name="Test Customer",
        dob=date(1990, 1, 1),
        address_line="123 Main St",
        city="Denver",
        state="CO",
        country="USA",
        phone_number="5551234567",
        balance=Decimal("100.00"),
        currency="USD",
        is_active=True,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    # Empty amount -> invalid
    vm.amount_str = ""
    is_valid, errors = vm.validate_deposit()
    assert is_valid is False
    assert "amount" in errors

    # Non-numeric -> invalid
    vm.amount_str = "abc"
    is_valid, errors = vm.validate_deposit()
    assert is_valid is False
    assert "amount" in errors

    # Below min ($0.50) -> invalid
    vm.amount_str = "0.50"
    is_valid, errors = vm.validate_deposit()
    assert is_valid is False
    assert "Minimum" in errors["amount"]

    # Exceeds 2 decimals -> invalid
    vm.amount_str = "10.555"
    is_valid, errors = vm.validate_deposit()
    assert is_valid is False
    assert "2 decimal places" in errors["amount"]

    # Exceeds max counter limit -> invalid
    vm.amount_str = "2000000.00"
    is_valid, errors = vm.validate_deposit()
    assert is_valid is False
    assert "maximum limit" in errors["amount"]

    # Valid deposit
    vm.amount_str = "250.75"
    is_valid, errors = vm.validate_deposit()
    assert is_valid is True
    assert len(errors) == 0


def test_transaction_viewmodel_preview_calculation() -> None:
    """Verify live calculation of deposit projection."""
    vm = TransactionViewModel()
    from datetime import datetime, timezone

    from novabank.application.dto.account_dto import AccountDTO

    vm.source_account = AccountDTO(
        account_number="111122223333",
        holder_name="Test Customer",
        dob=date(1990, 1, 1),
        address_line="123 Main St",
        city="Denver",
        state="CO",
        country="USA",
        phone_number="5551234567",
        balance=Decimal("1000.00"),
        currency="USD",
        is_active=True,
        version=1,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    vm.amount_str = "350.25"
    curr, dep, proj = vm.calculate_deposit_preview()
    assert curr == Decimal("1000.00")
    assert dep == Decimal("350.25")
    assert proj == Decimal("1350.25")


def test_deposit_view_lookup_and_submission(qtbot, banking_service, monkeypatch) -> None:
    """Verify end-to-end lookup, deposit execution, and digital receipt modal."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Arthur Dent",
        dob=date(1980, 4, 23),
        address_line="Cottington Cottage",
        city="London",
        state="UK",
        country="UK",
        phone_number="5559876543",
        initial_deposit=Decimal("200.00"),
    )
    acc_num = res.account.account_number

    view = DepositView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    # Mock receipt dialog
    info_mock = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", info_mock)

    # Enter account number
    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.account_edit.setText(acc_num)

    assert view.account_banner.isVisible() is True
    assert "Arthur Dent" in view.banner_name.text()
    assert "$200.00" in view.banner_details.text()

    # Enter deposit amount
    view.amount_edit.setText("300.00")
    assert view.submit_btn.isEnabled() is True

    tx_events: list[TransactionDTO] = []
    view.vm.transaction_completed.connect(lambda dto: tx_events.append(dto))

    with qtbot.waitSignal(view.vm.transaction_completed, timeout=3000):
        view.submit_btn.click()

    assert len(tx_events) == 1
    tx = tx_events[0]
    assert tx.amount == Decimal("300.00")
    assert tx.balance_after == Decimal("500.00")

    # Receipt displayed
    assert info_mock.called is True
    receipt_args = info_mock.call_args[0]
    assert "DEPOSIT RECEIPT" in receipt_args[2]
    assert "+$300.00" in receipt_args[2]
    assert "$500.00" in receipt_args[2]

    # Verify DB update
    updated_acc = banking_service.get_account(acc_num)
    assert updated_acc is not None
    assert updated_acc.balance == Decimal("500.00")


def test_deposit_view_closed_account_rejection(qtbot, banking_service) -> None:
    """Verify inactive/closed account lookup blocks deposit execution."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Ford Prefect",
        dob=date(1978, 6, 11),
        address_line="Betelgeuse Five",
        city="Guildford",
        state="UK",
        country="UK",
        phone_number="5556543210",
        initial_deposit=Decimal("0.00"),
    )
    banking_service.close_account(res.account.account_number)

    view = DepositView(banking_service=banking_service, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.account_edit.setText(res.account.account_number)

    assert "Closed" in view.banner_badge.text()
    view.amount_edit.setText("100.00")

    # Submit button must be disabled for closed accounts
    assert view.submit_btn.isEnabled() is False
    assert view.account_error.isVisible() is True
    assert "inactive/closed" in view.account_error.text()
