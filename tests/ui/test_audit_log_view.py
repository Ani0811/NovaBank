"""Tests for AuditLogView and AuditLogViewModel compliance audit features."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.services.audit_service import AuditService
from novabank.infrastructure.db.models import Base
from novabank.ui.viewmodels.audit_log_viewmodel import AuditLogViewModel
from novabank.ui.views.audit_log_view import AuditLogView
from novabank.ui.workers.task_runner import TaskRunner


@pytest.fixture
def audit_service_with_events():
    """Create in-memory SQLite audit service pre-populated with audit events."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    service = AuditService(session_factory=session_factory)

    base_time = datetime(2026, 11, 1, 9, 0, 0, tzinfo=timezone.utc)

    # 1. Account Creation
    service.record_event(
        event_type=AuditService.EVENT_ACCOUNT_CREATED,
        entity_type="ACCOUNT",
        entity_id="100000000001",
        actor="manager_alice",
        payload={
            "holder_name": "Oliver Queen",
            "initial_deposit": "5000.00",
            "phone_number": "5554443333",
            "currency": "USD",
        },
        timestamp=base_time,
    )

    # 2. Cash Deposit
    service.record_event(
        event_type=AuditService.EVENT_DEPOSIT,
        entity_type="TRANSACTION",
        entity_id="TXN-DEP-001",
        actor="teller_bob",
        payload={
            "account_number": "100000000001",
            "amount": "1200.00",
            "balance_after": "6200.00",
            "currency": "USD",
        },
        timestamp=base_time + timedelta(hours=1),
    )

    # 3. Cash Withdrawal
    service.record_event(
        event_type=AuditService.EVENT_WITHDRAWAL,
        entity_type="TRANSACTION",
        entity_id="TXN-WDR-001",
        actor="teller_bob",
        payload={
            "account_number": "100000000001",
            "amount": "300.00",
            "balance_after": "5900.00",
            "currency": "USD",
        },
        timestamp=base_time + timedelta(hours=2),
    )

    return service


def test_viewmodel_initial_state() -> None:
    """Verify initial state of AuditLogViewModel."""
    vm = AuditLogViewModel()
    assert vm.event_type_filter == "ALL"
    assert vm.entity_id_search == ""
    assert vm.current_page == 1
    assert vm.total_count == 0
    assert vm.total_pages == 1
    assert len(vm.events) == 0
    assert vm.selected_event is None


def test_viewmodel_pagination_logic() -> None:
    """Verify page navigation calculations."""
    vm = AuditLogViewModel()
    vm.total_count = 60
    vm.page_size = 25
    assert vm.total_pages == 3

    # Next page
    vm.next_page()
    assert vm.current_page == 2
    vm.next_page()
    assert vm.current_page == 3
    # Clamped
    vm.next_page()
    assert vm.current_page == 3

    # Prev page
    vm.prev_page()
    assert vm.current_page == 2
    vm.prev_page()
    assert vm.current_page == 1
    # Clamped
    vm.prev_page()
    assert vm.current_page == 1


def test_audit_log_view_table_population(qtbot, audit_service_with_events) -> None:
    """Verify table is populated with loaded audit events."""
    task_runner = TaskRunner()
    view = AuditLogView(audit_service=audit_service_with_events, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    # Wait until all 3 events populate table
    qtbot.waitUntil(lambda: view.table.rowCount() == 3, timeout=3000)

    assert "3 total audit events" in view.total_badge.text()
    assert "Page 1 of 1" in view.page_info_label.text()

    # Verify rows (ordered latest first)
    # Row 0: WITHDRAWAL
    assert view.table.item(0, 1).text() == "WITHDRAWAL"
    assert view.table.item(0, 3).text() == "TXN-WDR-001"
    assert view.table.item(0, 4).text() == "teller_bob"

    # Row 1: DEPOSIT
    assert view.table.item(1, 1).text() == "DEPOSIT"
    assert view.table.item(1, 3).text() == "TXN-DEP-001"

    # Row 2: ACCOUNT_CREATED
    assert view.table.item(2, 1).text() == "ACCOUNT_CREATED"
    assert view.table.item(2, 3).text() == "100000000001"
    assert view.table.item(2, 4).text() == "manager_alice"


def test_audit_log_view_diff_inspector_display(qtbot, audit_service_with_events) -> None:
    """Verify selecting an audit event displays its metadata and JSON diff inspector."""
    task_runner = TaskRunner()
    view = AuditLogView(audit_service=audit_service_with_events, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    qtbot.waitUntil(lambda: view.table.rowCount() == 3, timeout=3000)

    # Initial selection: Row 0 (WITHDRAWAL)
    assert "Event #" in view.inspector_title.text()
    assert "WITHDRAWAL" in view.inspector_title.text()
    assert "teller_bob" in view.inspector_meta.text()
    assert '"amount": "300.00"' in view.json_viewer.toPlainText()

    # Select Row 2 (ACCOUNT_CREATED)
    view.table.selectRow(2)
    assert "ACCOUNT_CREATED" in view.inspector_title.text()
    assert "manager_alice" in view.inspector_meta.text()
    assert '"holder_name": "Oliver Queen"' in view.json_viewer.toPlainText()
    assert '"initial_deposit": "5000.00"' in view.json_viewer.toPlainText()


def test_audit_log_view_category_filtering(qtbot, audit_service_with_events) -> None:
    """Verify changing category filter narrows down table results."""
    task_runner = TaskRunner()
    view = AuditLogView(audit_service=audit_service_with_events, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    qtbot.waitUntil(lambda: view.table.rowCount() == 3, timeout=3000)

    # Filter by Cash Deposit
    idx = view.category_combo.findData("DEPOSIT")
    assert idx >= 0
    view.category_combo.setCurrentIndex(idx)

    qtbot.waitUntil(lambda: view.table.rowCount() == 1, timeout=3000)
    assert view.table.item(0, 1).text() == "DEPOSIT"
    assert view.table.item(0, 3).text() == "TXN-DEP-001"
    assert "1 total audit events" in view.total_badge.text()


def test_audit_log_view_search_filtering(qtbot, audit_service_with_events) -> None:
    """Verify filtering by entity ID."""
    task_runner = TaskRunner()
    view = AuditLogView(audit_service=audit_service_with_events, task_runner=task_runner)
    qtbot.addWidget(view)
    view.show()

    qtbot.waitUntil(lambda: view.table.rowCount() == 3, timeout=3000)

    # Search for account number
    view.search_edit.setText("100000000001")
    qtbot.waitUntil(lambda: view.table.rowCount() == 1, timeout=3000)
    assert view.table.item(0, 3).text() == "100000000001"

    # Search for non-existent ref
    view.search_edit.setText("TXN-UNKNOWN-999")
    qtbot.waitUntil(lambda: view.table.rowCount() == 0, timeout=3000)
    assert "0 total audit events" in view.total_badge.text()
    assert "No audit events found" in view.inspector_meta.text()
    assert view.json_viewer.toPlainText() == ""
