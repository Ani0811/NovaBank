"""Tests for AccountDetailView and AccountDetailViewModel."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QLabel, QMessageBox
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.viewmodels.account_detail_viewmodel import AccountDetailViewModel
from novabank.ui.views.account_detail_view import AccountDetailView
from novabank.ui.workers.task_runner import TaskRunner


@pytest.fixture
def banking_service():
    """Create in-memory banking service with StaticPool for cross-thread access."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return BankingService(session_factory=session_factory)


def test_viewmodel_validation() -> None:
    """Verify field validation on mutable customer contact fields."""
    vm = AccountDetailViewModel()

    # Valid
    vm.phone_number = "5551234567"
    vm.address_line = "123 Elm St"
    vm.city = "Seattle"
    vm.state = "WA"
    vm.country = "USA"
    is_valid, errors = vm.validate()
    assert is_valid is True
    assert len(errors) == 0

    # Invalid phone
    vm.phone_number = "123"
    is_valid, errors = vm.validate()
    assert is_valid is False
    assert "phone_number" in errors

    # Empty address
    vm.phone_number = "5551234567"
    vm.address_line = "   "
    is_valid, errors = vm.validate()
    assert is_valid is False
    assert "address_line" in errors


def test_viewmodel_save_profile_flow(qtbot, banking_service) -> None:
    """Verify asynchronous profile updates persist to database."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Diana Prince",
        dob=date(1990, 5, 12),
        address_line="100 Gateway Blvd",
        city="Themyscira",
        state="CA",
        country="USA",
        phone_number="5551112222",
    )

    vm = AccountDetailViewModel(banking_service, task_runner)
    vm.set_account(res.account)

    # Edit contact details
    vm.set_address_line("500 Paradise Island Rd")
    vm.set_city("Metropolis")
    vm.set_state("NY")
    vm.set_phone_number("5559990000")

    updated_events: list[AccountDTO] = []
    vm.profile_updated.connect(lambda dto: updated_events.append(dto))

    with qtbot.waitSignal(vm.profile_updated, timeout=3000):
        vm.save_profile()

    assert len(updated_events) == 1
    updated_acc = updated_events[0]
    assert updated_acc.address_line == "500 Paradise Island Rd"
    assert updated_acc.city == "Metropolis"
    assert updated_acc.state == "NY"
    assert updated_acc.phone_number == "5559990000"

    # Verify database persistence
    db_acc = banking_service.get_account(res.account.account_number)
    assert db_acc is not None
    assert db_acc.address_line == "500 Paradise Island Rd"
    assert db_acc.phone_number == "5559990000"


def test_viewmodel_close_account_zero_balance(qtbot, banking_service) -> None:
    """Verify closing an account with zero balance succeeds."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Bruce Wayne",
        dob=date(1985, 2, 19),
        address_line="1007 Mountain Drive",
        city="Gotham",
        state="NJ",
        country="USA",
        phone_number="5558889999",
        initial_deposit=Decimal("0.00"),
    )

    vm = AccountDetailViewModel(banking_service, task_runner)
    vm.set_account(res.account)

    closed_events: list[AccountDTO] = []
    vm.account_closed.connect(lambda dto: closed_events.append(dto))

    with qtbot.waitSignal(vm.account_closed, timeout=3000):
        vm.close_account(reason="Customer relocation")

    assert len(closed_events) == 1
    assert closed_events[0].is_active is False

    # Check DB
    db_acc = banking_service.get_account(res.account.account_number)
    assert db_acc is not None
    assert db_acc.is_active is False


def test_viewmodel_close_account_non_zero_balance_fails(qtbot, banking_service) -> None:
    """Verify closing an account with non-zero balance triggers operation_error."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Arthur Curry",
        dob=date(1986, 1, 29),
        address_line="Amnesty Bay",
        city="Amnesty Bay",
        state="ME",
        country="USA",
        phone_number="5551234567",
        initial_deposit=Decimal("250.00"),
    )

    vm = AccountDetailViewModel(banking_service, task_runner)
    vm.set_account(res.account)

    error_events: list[str] = []
    vm.operation_error.connect(lambda err: error_events.append(err))

    with qtbot.waitSignal(vm.operation_error, timeout=3000):
        vm.close_account(reason="Closing test")

    assert len(error_events) == 1
    assert "must be zero before closure" in error_events[0]


def test_account_detail_view_rendering_and_discard(qtbot, banking_service) -> None:
    """Verify UI renders account data correctly and discard button resets modifications."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Barry Allen",
        dob=date(1992, 3, 14),
        address_line="456 Central Ave",
        city="Central City",
        state="MO",
        country="USA",
        phone_number="5552223333",
        initial_deposit=Decimal("1250.00"),
    )

    view = AccountDetailView(
        banking_service=banking_service,
        task_runner=task_runner,
    )
    qtbot.addWidget(view)
    view.set_account(res.account)

    # Check rendered headers
    assert "Barry Allen" in view.holder_title.text()
    assert "$1,250.00" in view.balance_card.findChild(QLabel, "kpi_current_balance").text()
    assert view.phone_edit.text() == "5552223333"
    assert view.display_acc_edit.isReadOnly() is True
    assert view.display_name_edit.isReadOnly() is True

    # Mutate field
    view.phone_edit.setText("5559999999")
    assert view.phone_edit.text() == "5559999999"

    # Click Discard Changes
    view.discard_btn.click()
    assert view.phone_edit.text() == "5552223333"


def test_account_detail_view_close_guardrails(qtbot, banking_service, monkeypatch) -> None:
    """Verify close button blocks non-zero balance with warning."""
    task_runner = TaskRunner()
    res = banking_service.open_account(
        holder_name="Hal Jordan",
        dob=date(1989, 7, 10),
        address_line="789 Coast Highway",
        city="Coast City",
        state="CA",
        country="USA",
        phone_number="5554445555",
        initial_deposit=Decimal("100.00"),
    )

    view = AccountDetailView(
        banking_service=banking_service,
        task_runner=task_runner,
    )
    qtbot.addWidget(view)
    view.set_account(res.account)

    warning_mock = MagicMock()
    monkeypatch.setattr(QMessageBox, "warning", warning_mock)

    # Click close button while balance is $100
    view.close_btn.click()

    assert warning_mock.called is True
    args = warning_mock.call_args[0]
    assert "Cannot Close Account" in args[1]
    assert "remaining balance must be withdrawn" in args[2]


def test_account_detail_view_back_requested_signal(qtbot) -> None:
    """Verify back button emits back_requested signal."""
    view = AccountDetailView()
    qtbot.addWidget(view)

    back_called = []
    view.back_requested.connect(lambda: back_called.append(True))

    view.back_btn.click()
    assert back_called == [True]
