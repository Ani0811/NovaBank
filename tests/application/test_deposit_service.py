"""Unit and integration tests for BankingService deposit workflow."""

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from novabank.application.events import DepositCompletedEvent
from novabank.application.services.banking_service import BankingService
from novabank.domain.entities.account import Account
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountNotFoundError,
    DuplicateTransactionRefError,
    InvalidAmountError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.session import init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_transaction_repository import SQLTransactionRepository


@pytest.fixture
def db_setup():
    """Create a temporary SQLite database for clean multi-threaded testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    engine = create_engine(
        f"sqlite:///{db_path}?timeout=30",
        pool_size=10,
        max_overflow=20,
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    init_database(engine)
    session_factory = sessionmaker(bind=engine)

    yield session_factory, engine

    engine.dispose()
    try:
        os.remove(db_path)
        for ext in ["-wal", "-shm"]:
            if os.path.exists(db_path + ext):
                os.remove(db_path + ext)
    except Exception:
        pass


def create_account(
    session_factory: sessionmaker[Session],
    acc_no: str = "100000000001",
    holder_name: str = "Alice Walker",
    balance: str = "100.00",
    is_active: bool = True,
) -> Account:
    """Helper to seed an account in the database."""
    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            acc = Account(
                account_number=AccountNumber(acc_no),
                holder_name=holder_name,
                dob=date(1992, 4, 10),
                address_line="10 Beacon St",
                city="Boston",
                state="MA",
                country="USA",
                phone_number="1234567890",
                is_active=is_active,
                balance=Money(balance),
            )
            repo.save(acc)
    return acc


def test_deposit_success_path(db_setup):
    """Verify standard cash deposit workflow."""
    session_factory, _ = db_setup
    create_account(session_factory, "100000000001", balance="100.00")

    events_received: list[DepositCompletedEvent] = []
    service = BankingService(
        session_factory=session_factory,
        event_publisher=lambda ev: events_received.append(ev),
    )

    dto = service.deposit(
        account_number="100000000001",
        amount="50.00",
        description="Atm Deposit",
        ref="ref-dep-001",
        actor="teller_7",
    )

    # Verify DTO
    assert dto.transaction_ref == "ref-dep-001"
    assert dto.account_number == "100000000001"
    assert dto.amount == Decimal("50.00")
    assert dto.balance_after == Decimal("150.00")
    assert dto.formatted_amount == "$50.00"
    assert dto.formatted_balance_after == "$150.00"
    assert dto.transaction_type == "DEPOSIT"
    assert dto.direction == "CREDIT"
    assert dto.created_by == "teller_7"
    assert dto.description == "Atm Deposit"

    # Verify Database state
    with session_factory() as sess:
        account_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        acc = account_repo.get_by_number("100000000001")
        assert acc is not None
        assert acc.balance == Money("150.00")
        assert acc.version == 2

        tx = tx_repo.get_by_ref("ref-dep-001")
        assert tx is not None
        assert tx.amount == Money("50.00")
        assert tx.balance_after == Money("150.00")

    # Verify Event Emitted
    assert len(events_received) == 1
    ev = events_received[0]
    assert ev.account_number == "100000000001"
    assert ev.amount == Decimal("50.00")
    assert ev.balance_after == Decimal("150.00")
    assert ev.transaction_ref == "ref-dep-001"
    assert ev.actor == "teller_7"


def test_deposit_account_not_found(db_setup):
    """Verify AccountNotFoundError is raised for non-existent accounts."""
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    with pytest.raises(AccountNotFoundError) as exc_info:
        service.deposit("999999999999", "100.00")

    assert "999999999999" in str(exc_info.value)


def test_deposit_closed_account_rejected(db_setup):
    """Verify AccountClosedError is raised on deactivated accounts."""
    session_factory, _ = db_setup
    create_account(session_factory, "100000000002", balance="0.00", is_active=False)

    service = BankingService(session_factory=session_factory)

    with pytest.raises(AccountClosedError):
        service.deposit("100000000002", "50.00")

    # Balance must remain unchanged
    with session_factory() as sess:
        repo = SQLAccountRepository(sess)
        acc = repo.get_by_number("100000000002")
        assert acc is not None
        assert acc.balance == Money("0.00")


def test_deposit_non_positive_amount_rejected(db_setup):
    """Verify InvalidAmountError on zero, negative, or unparseable amounts."""
    session_factory, _ = db_setup
    create_account(session_factory, "100000000003", balance="100.00")
    service = BankingService(session_factory=session_factory)

    # Zero amount
    with pytest.raises(InvalidAmountError, match="strictly positive"):
        service.deposit("100000000003", "0.00")

    # Negative amount
    with pytest.raises(InvalidAmountError, match="strictly positive"):
        service.deposit("100000000003", "-25.00")

    # Invalid string
    with pytest.raises(InvalidAmountError, match="Invalid monetary deposit amount"):
        service.deposit("100000000003", "not-a-number")

    # Verify balance was untouched
    with session_factory() as sess:
        repo = SQLAccountRepository(sess)
        acc = repo.get_by_number("100000000003")
        assert acc is not None
        assert acc.balance == Money("100.00")


def test_deposit_rollback_on_database_failure(db_setup, monkeypatch):
    """Verify rollback on exception: neither balance change nor transaction record persists."""
    session_factory, _ = db_setup
    create_account(session_factory, "100000000004", balance="100.00")
    service = BankingService(session_factory=session_factory)

    def mock_append_failure(self, tx):
        raise RuntimeError("Simulated database failure during ledger append")

    monkeypatch.setattr(SQLTransactionRepository, "append", mock_append_failure)

    with pytest.raises(RuntimeError, match="Simulated database failure"):
        service.deposit("100000000004", "50.00", ref="rollback-ref-1")

    # Verify rollback: balance must still be $100.00, no transaction recorded
    with session_factory() as sess:
        account_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        acc = account_repo.get_by_number("100000000004")
        assert acc is not None
        assert acc.balance == Money("100.00")
        assert acc.version == 1

        tx = tx_repo.get_by_ref("rollback-ref-1")
        assert tx is None


def test_deposit_duplicate_reference_rejection(db_setup):
    """Verify idempotency violation raises DuplicateTransactionRefError."""
    session_factory, _ = db_setup
    create_account(session_factory, "100000000005", balance="100.00")
    service = BankingService(session_factory=session_factory)

    service.deposit("100000000005", "25.00", ref="duplicate-test-ref")

    with pytest.raises(DuplicateTransactionRefError):
        service.deposit("100000000005", "25.00", ref="duplicate-test-ref")

    # Balance must only have updated once ($125.00, not $150.00)
    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("100000000005")
        assert acc is not None
        assert acc.balance == Money("125.00")


def test_multi_threaded_concurrent_deposits(db_setup):
    """Verify concurrent deposits serialize cleanly with exact total."""
    session_factory, _ = db_setup
    create_account(session_factory, "100000000006", balance="100.00")

    events: list[DepositCompletedEvent] = []
    service = BankingService(session_factory=session_factory)
    service.subscribe(lambda ev: events.append(ev))

    deposit_amounts = [
        Decimal("10.00"),
        Decimal("20.00"),
        Decimal("30.00"),
        Decimal("40.00"),
        Decimal("50.00"),
    ] * 2
    # 10 deposits totaling $300.00. Starting balance $100.00 -> Expected $400.00.

    def perform_deposit(idx_amount):
        idx, amt = idx_amount
        return service.deposit(
            account_number="100000000006",
            amount=amt,
            description=f"Concurrent Deposit {idx}",
            ref=f"tx-concurrent-{idx}",
            actor=f"worker_{idx}",
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(perform_deposit, enumerate(deposit_amounts)))

    assert len(results) == 10

    # Verify final balance in database
    with session_factory() as sess:
        account_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        acc = account_repo.get_by_number("100000000006")
        assert acc is not None
        assert acc.balance == Money("400.00")
        assert acc.version == 11  # 1 initial + 10 updates

        tx_count = tx_repo.count_by_account("100000000006")
        assert tx_count == 10

    assert len(events) == 10


def test_deposit_with_value_objects_and_faulty_listener(db_setup):
    """Verify deposit accepts AccountNumber/Money VOs and listener exceptions do not disrupt commit."""
    session_factory, _ = db_setup
    create_account(session_factory, "100000000007", balance="100.00")

    def faulty_listener(event):
        raise RuntimeError("Faulty external analytics listener crash")

    service = BankingService(session_factory=session_factory)
    service.subscribe(faulty_listener)

    # Pass AccountNumber and Money instances directly
    dto = service.deposit(
        account_number=AccountNumber("100000000007"),
        amount=Money("75.00"),
        description="VO deposit",
    )

    assert dto.amount == Decimal("75.00")
    assert dto.balance_after == Decimal("175.00")

    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("100000000007")
        assert acc is not None
        assert acc.balance == Money("175.00")
