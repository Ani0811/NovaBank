"""Tests for AccountListView and AccountListViewModel."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.ui.viewmodels.account_list_viewmodel import AccountListViewModel
from novabank.ui.views.account_list_view import AccountListView
from novabank.ui.workers.task_runner import TaskRunner


@pytest.fixture
def banking_service_with_accounts():
    """Create in-memory banking service populated with test customer accounts."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    service = BankingService(session_factory=session_factory)

    # Populate 3 accounts: 2 active, 1 inactive/closed
    service.open_account(
        holder_name="Alice Anderson",
        dob=date(1990, 1, 15),
        address_line="100 First Ave",
        city="Boston",
        state="MA",
        country="USA",
        phone_number="5551112222",
        initial_deposit=Decimal("1500.00"),
    )

    service.open_account(
        holder_name="Bob Builder",
        dob=date(1985, 5, 20),
        address_line="200 Second St",
        city="Austin",
        state="TX",
        country="USA",
        phone_number="5553334444",
        initial_deposit=Decimal("250.50"),
    )

    res3 = service.open_account(
        holder_name="Charlie Chaplin",
        dob=date(1975, 8, 10),
        address_line="300 Third Blvd",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5555556666",
        initial_deposit=Decimal("0.00"),
    )

    # Deactivate charlie's account to test status filter
    with session_factory() as session:
        from novabank.infrastructure.db.models import AccountModel

        model = session.get(AccountModel, res3.account.account_number)
        if model:
            model.is_active = False
            session.commit()

    return service


def test_viewmodel_initial_state() -> None:
    """Verify default initial state of AccountListViewModel."""
    vm = AccountListViewModel()
    assert vm.search_query == ""
    assert vm.status_filter == "ALL"
    assert vm.current_page == 1
    assert vm.page_size == 25
    assert vm.total_count == 0
    assert len(vm.accounts) == 0


def test_viewmodel_status_filter_validation() -> None:
    """Verify status filter setting validates and normalizes inputs."""
    vm = AccountListViewModel()
    vm.set_status_filter("active")
    assert vm.status_filter == "ACTIVE"

    vm.set_status_filter("closed")
    assert vm.status_filter == "CLOSED"

    vm.set_status_filter("invalid_filter")
    assert vm.status_filter == "CLOSED"  # Remains unchanged


def test_viewmodel_pagination_logic() -> None:
    """Verify page navigation boundary calculations."""
    vm = AccountListViewModel()
    vm.total_pages = 3
    vm.current_page = 1

    # Next page
    vm.next_page()
    assert vm.current_page == 2

    vm.next_page()
    assert vm.current_page == 3

    # Clamped at last page
    vm.next_page()
    assert vm.current_page == 3

    # Prev page
    vm.prev_page()
    assert vm.current_page == 2

    vm.prev_page()
    assert vm.current_page == 1

    # Clamped at first page
    vm.prev_page()
    assert vm.current_page == 1


def test_account_list_view_population(qtbot, banking_service_with_accounts) -> None:
    """Verify table is populated with loaded accounts."""
    task_runner = TaskRunner()
    view = AccountListView(
        banking_service=banking_service_with_accounts,
        task_runner=task_runner,
    )
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.vm.accounts_loaded, timeout=3000):
        view.vm.load_data()

    assert view.table.rowCount() == 3
    assert "3 accounts" in view.total_badge.text()
    assert "Page 1 of 1" in view.page_info_label.text()

    # Verify column content of first row (Alice Anderson sorted ascending)
    name_item = view.table.item(0, 1)
    assert name_item.text() == "Alice Anderson"

    balance_item = view.table.item(0, 5)
    assert "$1,500.00 USD" in balance_item.text()


def test_account_list_view_search_filtering(qtbot, banking_service_with_accounts) -> None:
    """Verify search filter narrows down table results."""
    task_runner = TaskRunner()
    view = AccountListView(
        banking_service=banking_service_with_accounts,
        task_runner=task_runner,
    )
    qtbot.addWidget(view)

    # Wait for initial load
    with qtbot.waitSignal(view.vm.accounts_loaded, timeout=3000):
        pass
    assert view.table.rowCount() == 3

    # Search for "Austin" (city of Bob Builder)
    with qtbot.waitSignal(view.vm.accounts_loaded, timeout=3000):
        view.search_edit.setText("Austin")

    assert view.table.rowCount() == 1
    assert view.table.item(0, 1).text() == "Bob Builder"
    assert "1 account" in view.total_badge.text()

    # Clear search
    with qtbot.waitSignal(view.vm.accounts_loaded, timeout=3000):
        view.search_edit.clear()

    assert view.table.rowCount() == 3


def test_account_list_view_status_filtering(qtbot, banking_service_with_accounts) -> None:
    """Verify Active Only and Closed Only filters update table."""
    task_runner = TaskRunner()
    view = AccountListView(
        banking_service=banking_service_with_accounts,
        task_runner=task_runner,
    )
    qtbot.addWidget(view)

    # Wait for initial load
    with qtbot.waitSignal(view.vm.accounts_loaded, timeout=3000):
        pass

    # Filter: Active Only (Alice and Bob)
    with qtbot.waitSignal(view.vm.accounts_loaded, timeout=3000):
        view.btn_active.click()

    assert view.table.rowCount() == 2
    for row in range(view.table.rowCount()):
        assert "Active" in view.table.item(row, 4).text()

    # Filter: Closed Only (Charlie)
    with qtbot.waitSignal(view.vm.accounts_loaded, timeout=3000):
        view.btn_closed.click()

    assert view.table.rowCount() == 1
    assert view.table.item(0, 1).text() == "Charlie Chaplin"
    assert "Closed" in view.table.item(0, 4).text()


def test_account_list_view_double_click_row(qtbot, banking_service_with_accounts) -> None:
    """Verify double-clicking a table row emits account_detail_requested signal."""
    task_runner = TaskRunner()
    view = AccountListView(
        banking_service=banking_service_with_accounts,
        task_runner=task_runner,
    )
    qtbot.addWidget(view)

    with qtbot.waitSignal(view.vm.accounts_loaded, timeout=3000):
        pass

    selected_accounts: list[AccountDTO] = []
    view.account_detail_requested.connect(lambda acc: selected_accounts.append(acc))

    # Double-click row 0
    view.table.cellDoubleClicked.emit(0, 0)

    assert len(selected_accounts) == 1
    assert selected_accounts[0].holder_name == "Alice Anderson"
