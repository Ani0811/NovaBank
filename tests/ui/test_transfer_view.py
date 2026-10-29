"""Tests for TransferView, TransferReceiptDialog, and TransactionViewModel fund transfer workflow."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.transaction_dto import TransactionDTO, TransferResultDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.viewmodels.transaction_viewmodel import TransactionViewModel
from novabank.ui.views.transfer_view import TransferReceiptDialog, TransferView
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


def _make_account_dto(
    acc_num: str, name: str, balance: Decimal, is_active: bool = True
) -> AccountDTO:
    now = datetime.now(timezone.utc)
    return AccountDTO(
        account_number=acc_num,
        holder_name=name,
        dob=date(1990, 1, 1),
        address_line="123 Bank St",
        city="New York",
        state="NY",
        country="USA",
        phone_number="5551234567",
        balance=balance,
        currency="USD",
        is_active=is_active,
        version=1,
        created_at=now,
        updated_at=now,
    )


def test_transaction_viewmodel_transfer_validation() -> None:
    """Verify transfer validation rules including same-account and overdraft prevention."""
    vm = TransactionViewModel(mode="transfer")

    # 1. No accounts -> invalid
    is_valid, errors = vm.validate_transfer()
    assert is_valid is False
    assert "source_account" in errors
    assert "destination_account" in errors

    # 2. Source set, no destination -> invalid
    vm.source_account = _make_account_dto("111122223333", "Alice Smith", Decimal("500.00"))
    is_valid, errors = vm.validate_transfer()
    assert is_valid is False
    assert "destination_account" in errors

    # 3. Same source and destination account -> rejected!
    vm.destination_account = _make_account_dto("111122223333", "Alice Smith", Decimal("500.00"))
    is_valid, errors = vm.validate_transfer()
    assert is_valid is False
    assert "Cannot transfer funds to the same account" in errors["destination_account"]

    # 4. Inactive source account -> rejected!
    vm.source_account = _make_account_dto(
        "111122223333", "Alice Smith", Decimal("500.00"), is_active=False
    )
    vm.destination_account = _make_account_dto(
        "444455556666", "Bob Jones", Decimal("100.00"), is_active=True
    )
    is_valid, errors = vm.validate_transfer()
    assert is_valid is False
    assert "Source account is closed" in errors["source_account"]

    # 5. Inactive destination account -> rejected!
    vm.source_account = _make_account_dto(
        "111122223333", "Alice Smith", Decimal("500.00"), is_active=True
    )
    vm.destination_account = _make_account_dto(
        "444455556666", "Bob Jones", Decimal("100.00"), is_active=False
    )
    is_valid, errors = vm.validate_transfer()
    assert is_valid is False
    assert "Destination account is closed" in errors["destination_account"]

    # 6. Both active, empty amount -> rejected!
    vm.destination_account = _make_account_dto(
        "444455556666", "Bob Jones", Decimal("100.00"), is_active=True
    )
    vm.amount_str = ""
    is_valid, errors = vm.validate_transfer()
    assert is_valid is False
    assert "amount" in errors

    # 7. Amount below minimum ($0.50) -> rejected!
    vm.amount_str = "0.50"
    is_valid, errors = vm.validate_transfer()
    assert is_valid is False
    assert "Minimum transfer amount is $1.00" in errors["amount"]

    # 8. Overdraft: Transfer amount exceeds source balance ($600 > $500) -> rejected!
    vm.amount_str = "600.00"
    is_valid, errors = vm.validate_transfer()
    assert is_valid is False
    assert "Insufficient funds" in errors["amount"]

    # 9. Valid transfer ($150.00 <= $500.00) -> valid!
    vm.amount_str = "150.00"
    is_valid, errors = vm.validate_transfer()
    assert is_valid is True
    assert len(errors) == 0


def test_transaction_viewmodel_transfer_preview() -> None:
    """Verify real-time computation of dual balance changes."""
    vm = TransactionViewModel(mode="transfer")
    vm.source_account = _make_account_dto("111122223333", "Alice Smith", Decimal("500.00"))
    vm.destination_account = _make_account_dto("444455556666", "Bob Jones", Decimal("100.00"))
    vm.amount_str = "125.50"

    src_curr, dst_curr, amt, src_proj, dst_proj = vm.calculate_transfer_preview()
    assert src_curr == Decimal("500.00")
    assert dst_curr == Decimal("100.00")
    assert amt == Decimal("125.50")
    assert src_proj == Decimal("374.50")
    assert dst_proj == Decimal("225.50")


def test_transfer_view_same_account_rejection(qtbot, banking_service) -> None:
    """Verify that picking identical source and destination accounts is rejected in the UI."""
    task_runner = TaskRunner()
    acc = banking_service.open_account(
        holder_name="Single User",
        dob=date(1988, 3, 14),
        address_line="789 Broadway",
        city="New York",
        state="NY",
        country="USA",
        phone_number="5559876543",
        initial_deposit=Decimal("300.00"),
    )

    view = TransferView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    # Enter same account in both source and destination
    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.source_account_edit.setText(acc.account.account_number)

    with qtbot.waitSignal(view.vm.destination_account_found, timeout=3000):
        view.dest_account_edit.setText(acc.account.account_number)

    view.amount_edit.setText("50.00")

    # Assert same account rejection
    assert view.submit_btn.isEnabled() is False
    assert view.dest_account_error.isVisible() is True
    assert "Cannot transfer funds to the same account" in view.dest_account_error.text()


def test_transfer_view_insufficient_funds_rejection(qtbot, banking_service) -> None:
    """Verify UI prevents transfer when source account has insufficient balance."""
    task_runner = TaskRunner()
    src = banking_service.open_account(
        holder_name="Source Holder",
        dob=date(1990, 5, 20),
        address_line="100 First St",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5551112222",
        initial_deposit=Decimal("100.00"),
    )
    dst = banking_service.open_account(
        holder_name="Dest Holder",
        dob=date(1992, 8, 15),
        address_line="200 Second St",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5553334444",
        initial_deposit=Decimal("50.00"),
    )

    view = TransferView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.source_account_edit.setText(src.account.account_number)

    with qtbot.waitSignal(view.vm.destination_account_found, timeout=3000):
        view.dest_account_edit.setText(dst.account.account_number)

    # Enter amount exceeding $100.00
    view.amount_edit.setText("150.00")

    assert view.submit_btn.isEnabled() is False
    assert view.amount_error.isVisible() is True
    assert "Insufficient funds" in view.amount_error.text()


def test_transfer_view_execution_success(qtbot, banking_service, monkeypatch) -> None:
    """Verify end-to-end atomic transfer execution and UI balance refresh."""
    task_runner = TaskRunner()
    src = banking_service.open_account(
        holder_name="Sender Alice",
        dob=date(1985, 4, 10),
        address_line="123 Oak St",
        city="Dallas",
        state="TX",
        country="USA",
        phone_number="5554445555",
        initial_deposit=Decimal("500.00"),
    )
    dst = banking_service.open_account(
        holder_name="Receiver Bob",
        dob=date(1989, 7, 22),
        address_line="456 Pine St",
        city="Austin",
        state="TX",
        country="USA",
        phone_number="5556667777",
        initial_deposit=Decimal("100.00"),
    )

    view = TransferView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    # Avoid modal blocking during headless test
    monkeypatch.setattr(TransferReceiptDialog, "exec", lambda self: 1)

    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.source_account_edit.setText(src.account.account_number)

    with qtbot.waitSignal(view.vm.destination_account_found, timeout=3000):
        view.dest_account_edit.setText(dst.account.account_number)

    view.amount_edit.setText("200.00")
    view.desc_edit.setText("Office Supplies Reimbursement")

    assert view.submit_btn.isEnabled() is True

    # Click transfer
    with qtbot.waitSignal(view.vm.transaction_completed, timeout=5000) as blocker:
        view.submit_btn.click()

    result = blocker.args[0]
    assert isinstance(result, TransferResultDTO)
    assert result.amount == Decimal("200.00")
    assert result.source_transaction.balance_after == Decimal("300.00")
    assert result.destination_transaction.balance_after == Decimal("300.00")

    # Verify underlying database state
    refreshed_src = banking_service.get_account(src.account.account_number)
    refreshed_dst = banking_service.get_account(dst.account.account_number)
    assert refreshed_src is not None and refreshed_src.balance == Decimal("300.00")
    assert refreshed_dst is not None and refreshed_dst.balance == Decimal("300.00")


def test_transfer_view_closed_account_blocked(qtbot, banking_service) -> None:
    """Verify that closed accounts are detected with red badge and transfer is blocked."""
    task_runner = TaskRunner()
    acc_active = banking_service.open_account(
        holder_name="Active Customer",
        dob=date(1990, 1, 1),
        address_line="100 Main St",
        city="Seattle",
        state="WA",
        country="USA",
        phone_number="5550001111",
        initial_deposit=Decimal("200.00"),
    )
    acc_closed = banking_service.open_account(
        holder_name="Closed Customer",
        dob=date(1985, 2, 2),
        address_line="200 Main St",
        city="Seattle",
        state="WA",
        country="USA",
        phone_number="5552223333",
        initial_deposit=Decimal("0.00"),
    )
    # Close the second account
    banking_service.close_account(acc_closed.account.account_number, reason="Customer moved abroad")

    view = TransferView(banking_service, task_runner)
    qtbot.addWidget(view)
    view.show()

    # Set closed account as destination
    with qtbot.waitSignal(view.vm.account_found, timeout=3000):
        view.source_account_edit.setText(acc_active.account.account_number)

    with qtbot.waitSignal(view.vm.destination_account_found, timeout=3000):
        view.dest_account_edit.setText(acc_closed.account.account_number)

    view.amount_edit.setText("50.00")

    # Assert closed destination error and badge
    assert "Closed" in view.dest_banner_badge.text()
    assert view.submit_btn.isEnabled() is False
    assert "Destination account is closed" in view.dest_account_error.text()


def test_transfer_receipt_dialog(qtbot, monkeypatch) -> None:
    """Verify TransferReceiptDialog displays dual transaction records and prints."""
    now = datetime.now(timezone.utc)
    src_tx = TransactionDTO(
        transaction_ref="TX-SRC-123456",
        account_number="111122223333",
        transaction_type="TRANSFER_OUT",
        direction="DEBIT",
        amount=Decimal("150.00"),
        balance_after=Decimal("350.00"),
        currency="USD",
        description="Transfer Out",
        created_at=now,
        created_by="teller",
        formatted_amount="-$150.00",
        formatted_balance_after="$350.00",
    )
    dst_tx = TransactionDTO(
        transaction_ref="TX-DST-789012",
        account_number="444455556666",
        transaction_type="TRANSFER_IN",
        direction="CREDIT",
        amount=Decimal("150.00"),
        balance_after=Decimal("250.00"),
        currency="USD",
        description="Transfer In",
        created_at=now,
        created_by="teller",
        formatted_amount="+$150.00",
        formatted_balance_after="$250.00",
    )
    transfer_result = TransferResultDTO(
        correlation_id="CORR-999-ABC",
        source_transaction=src_tx,
        destination_transaction=dst_tx,
        amount=Decimal("150.00"),
        currency="USD",
        timestamp=now,
    )

    dialog = TransferReceiptDialog(transfer_result)
    qtbot.addWidget(dialog)
    dialog.show()

    assert "CORR-999-ABC" in dialog.transfer_result.correlation_id
    assert dialog.transfer_result.amount == Decimal("150.00")

    # Test print button
    mock_box = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", mock_box)
    dialog._on_print_clicked()
    assert mock_box.called
    assert "CORR-999-ABC" in mock_box.call_args[0][2]


def test_transfer_view_reset_form(qtbot) -> None:
    """Verify reset_form clears all edits, errors, and resets VM state."""
    view = TransferView()
    qtbot.addWidget(view)
    view.show()

    view.source_account_edit.setText("111122223333")
    view.dest_account_edit.setText("444455556666")
    view.amount_edit.setText("100.00")

    view.reset_form()

    assert view.source_account_edit.text() == ""
    assert view.dest_account_edit.text() == ""
    assert view.amount_edit.text() == ""
    assert view.source_banner.isVisible() is False
    assert view.dest_banner.isVisible() is False
    assert view.submit_btn.isEnabled() is False
