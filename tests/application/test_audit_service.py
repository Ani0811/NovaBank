"""Tests for AuditService, SQLAuditRepository, and automated event audit trail."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.audit_dto import AuditEventDTO
from novabank.application.events import (
    AccountClosedEvent,
    AccountOpenedEvent,
    DepositCompletedEvent,
    ProfileUpdatedEvent,
    TransferCompletedEvent,
    WithdrawalCompletedEvent,
)
from novabank.application.services.audit_service import AuditService
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.models import Base
from novabank.infrastructure.repositories.sql_audit_repository import SQLAuditRepository


@pytest.fixture
def session_factory():
    """Create in-memory SQLite database session factory for isolated testing."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def audit_service(session_factory):
    """Create AuditService instance."""
    return AuditService(session_factory=session_factory)


def test_record_explicit_audit_event(audit_service: AuditService) -> None:
    """Verify explicit recording of an audit event with metadata and payload."""
    event = audit_service.record_event(
        event_type="SECURITY_LOGIN",
        entity_type="USER",
        entity_id="admin_01",
        actor="system",
        payload={"ip_address": "127.0.0.1", "status": "SUCCESS"},
    )

    assert isinstance(event, AuditEventDTO)
    assert event.event_id > 0
    assert event.event_type == "SECURITY_LOGIN"
    assert event.entity_type == "USER"
    assert event.entity_id == "admin_01"
    assert event.actor == "system"
    assert event.payload["ip_address"] == "127.0.0.1"
    assert event.payload["status"] == "SUCCESS"
    assert event.formatted_timestamp != ""
    assert '"ip_address": "127.0.0.1"' in event.formatted_json


def test_payload_serialization_with_decimals_and_dates(audit_service: AuditService) -> None:
    """Verify payload serialization safely converts Decimals and datetimes into JSON primitives."""
    now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    complex_payload = {
        "amount": Decimal("1250.75"),
        "fees": [Decimal("5.00"), Decimal("2.50")],
        "nested": {"balance_before": Decimal("1000.00"), "effective_date": now},
    }

    event = audit_service.record_event(
        event_type="FEE_CHARGED",
        entity_type="ACCOUNT",
        entity_id="100000000099",
        actor="billing_cron",
        payload=complex_payload,
    )

    assert event.payload["amount"] == "1250.75"
    assert event.payload["fees"] == ["5.00", "2.50"]
    assert event.payload["nested"]["balance_before"] == "1000.00"
    assert "2026-11-01" in event.payload["nested"]["effective_date"]


def test_handle_domain_events_mapping(audit_service: AuditService) -> None:
    """Verify handle_event properly converts all application lifecycle events into audit records."""
    now = datetime(2026, 11, 1, 10, 0, 0)

    # 1. AccountOpenedEvent
    ev_open = AccountOpenedEvent(
        account_number="100000000001",
        holder_name="Clark Kent",
        phone_number="5551112222",
        initial_deposit=Decimal("500.00"),
        currency="USD",
        timestamp=now,
        actor="manager_bob",
    )
    rec1 = audit_service.handle_event(ev_open)
    assert rec1 is not None
    assert rec1.event_type == AuditService.EVENT_ACCOUNT_CREATED
    assert rec1.entity_id == "100000000001"
    assert rec1.actor == "manager_bob"
    assert rec1.payload["initial_deposit"] == "500.00"

    # 2. ProfileUpdatedEvent
    ev_update = ProfileUpdatedEvent(
        account_number="100000000001",
        phone_number="5559998888",
        city="Metropolis",
        state="NY",
        timestamp=now + timedelta(minutes=5),
        actor="teller_alice",
    )
    rec2 = audit_service.handle_event(ev_update)
    assert rec2 is not None
    assert rec2.event_type == AuditService.EVENT_ACCOUNT_UPDATED
    assert rec2.payload["city"] == "Metropolis"

    # 3. DepositCompletedEvent
    ev_dep = DepositCompletedEvent(
        account_number="100000000001",
        amount=Decimal("300.00"),
        balance_after=Decimal("800.00"),
        currency="USD",
        transaction_ref="DEP-001",
        timestamp=now + timedelta(minutes=10),
        actor="teller_alice",
        description="Cash Deposit",
    )
    rec3 = audit_service.handle_event(ev_dep)
    assert rec3 is not None
    assert rec3.event_type == AuditService.EVENT_DEPOSIT
    assert rec3.entity_id == "DEP-001"
    assert rec3.payload["amount"] == "300.00"

    # 4. WithdrawalCompletedEvent
    ev_wdr = WithdrawalCompletedEvent(
        account_number="100000000001",
        amount=Decimal("150.00"),
        balance_after=Decimal("650.00"),
        currency="USD",
        transaction_ref="WDR-001",
        timestamp=now + timedelta(minutes=15),
        actor="teller_alice",
        description="ATM Withdrawal",
    )
    rec4 = audit_service.handle_event(ev_wdr)
    assert rec4 is not None
    assert rec4.event_type == AuditService.EVENT_WITHDRAWAL
    assert rec4.entity_id == "WDR-001"

    # 5. TransferCompletedEvent
    ev_xfr = TransferCompletedEvent(
        source_account="100000000001",
        destination_account="100000000002",
        amount=Decimal("200.00"),
        source_balance_after=Decimal("450.00"),
        destination_balance_after=Decimal("200.00"),
        currency="USD",
        correlation_id="CORR-777",
        timestamp=now + timedelta(minutes=20),
        actor="system",
        description="Online Transfer",
    )
    rec5 = audit_service.handle_event(ev_xfr)
    assert rec5 is not None
    assert rec5.event_type == AuditService.EVENT_TRANSFER
    assert rec5.entity_id == "CORR-777"
    assert rec5.payload["source_account"] == "100000000001"

    # 6. AccountClosedEvent
    ev_close = AccountClosedEvent(
        account_number="100000000001",
        reason="Customer relocation",
        timestamp=now + timedelta(minutes=25),
        actor="manager_bob",
    )
    rec6 = audit_service.handle_event(ev_close)
    assert rec6 is not None
    assert rec6.event_type == AuditService.EVENT_ACCOUNT_CLOSED
    assert rec6.payload["reason"] == "Customer relocation"


def test_automatic_audit_integration_with_banking_service(session_factory) -> None:
    """Verify BankingService workflows automatically write audit logs when listener registered."""
    banking_service = BankingService(session_factory=session_factory)
    audit_service = AuditService(session_factory=session_factory)

    # Register audit listener with banking service
    banking_service.register_listener(audit_service.handle_event)

    # 1. Open account
    res = banking_service.open_account(
        holder_name="Diana Prince",
        dob=date(1990, 8, 12),
        address_line="100 Gateway Blvd",
        city="Paradise Island",
        state="FL",
        country="USA",
        phone_number="5558889999",
        initial_deposit=Decimal("1500.00"),
        actor="branch_manager",
    )
    acc_num = res.account.account_number

    # 2. Deposit
    banking_service.deposit(acc_num, Decimal("500.00"), actor="teller_1")

    # 3. Withdraw
    banking_service.withdraw(acc_num, Decimal("200.00"), actor="teller_2")

    # 4. Update profile
    banking_service.update_account_profile(
        account_number=acc_num,
        address_line="200 Temple Way",
        city="Themyscira",
        state="FL",
        country="USA",
        phone_number="5550001111",
        actor="teller_1",
    )

    # Query audit logs
    events, total = audit_service.query_events(limit=50)
    assert total == 4

    types = [e.event_type for e in events]
    assert AuditService.EVENT_ACCOUNT_UPDATED in types
    assert AuditService.EVENT_WITHDRAWAL in types
    assert AuditService.EVENT_DEPOSIT in types
    assert AuditService.EVENT_ACCOUNT_CREATED in types


def test_query_events_filtering_and_pagination(audit_service: AuditService) -> None:
    """Verify filtering by event_type, actor, entity_id, date range, and pagination."""
    t0 = datetime(2026, 10, 1, 10, 0, 0)
    for i in range(10):
        ev_type = AuditService.EVENT_DEPOSIT if i % 2 == 0 else AuditService.EVENT_WITHDRAWAL
        actor_name = "alice" if i < 5 else "bob"
        audit_service.record_event(
            event_type=ev_type,
            entity_type="TRANSACTION",
            entity_id=f"TXN-{i:03d}",
            actor=actor_name,
            payload={"index": i},
            timestamp=t0 + timedelta(days=i),
        )

    # Filter by event_type
    dep_events, dep_count = audit_service.query_events(event_type="DEPOSIT")
    assert dep_count == 5
    assert all(e.event_type == "DEPOSIT" for e in dep_events)

    # Filter by actor
    alice_events, alice_count = audit_service.query_events(actor="alice")
    assert alice_count == 5
    assert all(e.actor == "alice" for e in alice_events)

    # Filter by entity_id
    single_event, single_count = audit_service.query_events(entity_id="TXN-003")
    assert single_count == 1
    assert single_event[0].entity_id == "TXN-003"

    # Filter by date range (days 2 to 5 inclusive)
    range_events, range_count = audit_service.query_events(
        start_date=t0 + timedelta(days=2),
        end_date=t0 + timedelta(days=5),
    )
    assert range_count == 4

    # Pagination: limit=3, offset=0
    page1, total = audit_service.query_events(limit=3, offset=0)
    assert total == 10
    assert len(page1) == 3

    # Pagination: limit=3, offset=3
    page2, _ = audit_service.query_events(limit=3, offset=3)
    assert len(page2) == 3
    assert page1[0].event_id != page2[0].event_id


def test_get_event_by_id(audit_service: AuditService) -> None:
    """Verify fetching single event by ID or returning None if missing."""
    event = audit_service.record_event(
        event_type="TEST_EVENT",
        entity_type="SYSTEM",
        entity_id="SYS-1",
        actor="root",
    )

    found = audit_service.get_event(event.event_id)
    assert found is not None
    assert found.event_id == event.event_id
    assert found.event_type == "TEST_EVENT"

    not_found = audit_service.get_event(999999)
    assert not_found is None


def test_audit_immutability_no_delete_or_update_methods() -> None:
    """Verify AuditRepository and AuditService adhere strictly to append-only immutability."""
    for cls in (AuditService, SQLAuditRepository):
        assert not hasattr(cls, "delete")
        assert not hasattr(cls, "delete_by_id")
        assert not hasattr(cls, "remove")
        assert not hasattr(cls, "update")
        assert not hasattr(cls, "modify")
