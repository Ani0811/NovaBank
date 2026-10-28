"""Unit and integration tests for BankingService withdrawal workflow."""

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from novabank.application.events import WithdrawalCompletedEvent
from novabank.application.services.banking_service import BankingService
from novabank.domain.entities.account import Account
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountNotFoundError,
    DuplicateTransactionRefError,
    InsufficientFundsError,
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
    acc_no: str = "200000000001",
    holder_name: str = "Bob Smith",
    balance: str = "200.00",
    is_active: bool = True,
) -> Account:
    """Helper to seed an account in the database."""
    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            acc = Account(
                account_number=AccountNumber(acc_no),
                holder_name=holder_name,
                dob=date(1985, 3, 15),
                address_line="250 Federal St",
                city="Boston",
                state="MA",
                country="USA",
                phone_number="5559876543",
                is_active=is_active,
                balance=Money(balance),
            )
            repo.save(acc)
    return acc


def test_withdraw_success_path(db_setup):
    """Verify standard cash withdrawal workflow."""
    session_factory, _ = db_setup
    create_account(session_factory, "200000000001", balance="200.00")

    events_received: list[WithdrawalCompletedEvent] = []
    service = BankingService(
        session_factory=session_factory,
        event_publisher=lambda ev: events_received.append(ev),
    )

    dto = service.withdraw(
        account_number="200000000001",
        amount="75.00",
        description="Atm Cash Withdrawal",
        ref="ref-with-001",
        actor="atm_branch_4",
    )

    # Verify DTO
    assert dto.transaction_ref == "ref-with-001"
    assert dto.account_number == "200000000001"
    assert dto.amount == Decimal("75.00")
    assert dto.balance_after == Decimal("125.00")
    assert dto.formatted_amount == "$75.00"
    assert dto.formatted_balance_after == "$125.00"
    assert dto.transaction_type == "WITHDRAWAL"
    assert dto.direction == "DEBIT"
    assert dto.created_by == "atm_branch_4"
    assert dto.description == "Atm Cash Withdrawal"

    # Verify Database state
    with session_factory() as sess:
        account_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        acc = account_repo.get_by_number("200000000001")
        assert acc is not None
        assert acc.balance == Money("125.00")
        assert acc.version == 2

        tx = tx_repo.get_by_ref("ref-with-001")
        assert tx is not None
        assert tx.amount == Money("75.00")
        assert tx.balance_after == Money("125.00")
        assert tx.direction.value == "DEBIT"

    # Verify Event Emitted
    assert len(events_received) == 1
    ev = events_received[0]
    assert ev.account_number == "200000000001"
    assert ev.amount == Decimal("75.00")
    assert ev.balance_after == Decimal("125.00")
    assert ev.transaction_ref == "ref-with-001"
    assert ev.actor == "atm_branch_4"


def test_withdraw_overdraft_insufficient_funds_rejected(db_setup):
    """Verify InsufficientFundsError when withdrawal exceeds available balance."""
    session_factory, _ = db_setup
    create_account(session_factory, "200000000002", balance="50.00")
    service = BankingService(session_factory=session_factory)

    # Attempt to withdraw $50.01 from $50.00 balance
    with pytest.raises(InsufficientFundsError) as exc_info:
        service.withdraw("200000000002", "50.01")

    assert "available balance is $50.00" in str(exc_info.value)
    assert "requested $50.01" in str(exc_info.value)

    # Verify balance was unaltered in database
    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("200000000002")
        assert acc is not None
        assert acc.balance == Money("50.00")
        assert acc.version == 1

        tx_count = SQLTransactionRepository(sess).count_by_account("200000000002")
        assert tx_count == 0


def test_withdraw_account_not_found(db_setup):
    """Verify AccountNotFoundError when account does not exist."""
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    with pytest.raises(AccountNotFoundError) as exc_info:
        service.withdraw("999999999999", "50.00")

    assert "999999999999" in str(exc_info.value)


def test_withdraw_closed_account_rejected(db_setup):
    """Verify AccountClosedError when withdrawing from deactivated account."""
    session_factory, _ = db_setup
    create_account(session_factory, "200000000003", balance="100.00", is_active=False)
    service = BankingService(session_factory=session_factory)

    with pytest.raises(AccountClosedError):
        service.withdraw("200000000003", "20.00")

    # Verify balance unchanged
    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("200000000003")
        assert acc is not None
        assert acc.balance == Money("100.00")


def test_withdraw_non_positive_amount_rejected(db_setup):
    """Verify InvalidAmountError on zero, negative, or invalid amounts."""
    session_factory, _ = db_setup
    create_account(session_factory, "200000000004", balance="100.00")
    service = BankingService(session_factory=session_factory)

    # Zero
    with pytest.raises(InvalidAmountError, match="strictly positive"):
        service.withdraw("200000000004", "0.00")

    # Negative
    with pytest.raises(InvalidAmountError, match="strictly positive"):
        service.withdraw("200000000004", "-30.00")

    # Malformed string
    with pytest.raises(InvalidAmountError, match="Invalid monetary withdrawal amount"):
        service.withdraw("200000000004", "xyz")

    # Verify balance was untouched
    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("200000000004")
        assert acc is not None
        assert acc.balance == Money("100.00")


def test_withdraw_rollback_on_database_failure(db_setup, monkeypatch):
    """Verify rollback on exception: neither balance decrement nor transaction persists."""
    session_factory, _ = db_setup
    create_account(session_factory, "200000000005", balance="100.00")
    service = BankingService(session_factory=session_factory)

    def mock_append_failure(self, tx):
        raise RuntimeError("Simulated failure during ledger append")

    monkeypatch.setattr(SQLTransactionRepository, "append", mock_append_failure)

    with pytest.raises(RuntimeError, match="Simulated failure"):
        service.withdraw("200000000005", "40.00", ref="rollback-with-1")

    # Verify rollback: balance must still be $100.00, no transaction recorded
    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("200000000005")
        assert acc is not None
        assert acc.balance == Money("100.00")
        assert acc.version == 1

        tx = SQLTransactionRepository(sess).get_by_ref("rollback-with-1")
        assert tx is None


def test_withdraw_duplicate_reference_rejection(db_setup):
    """Verify idempotency violation raises DuplicateTransactionRefError."""
    session_factory, _ = db_setup
    create_account(session_factory, "200000000006", balance="100.00")
    service = BankingService(session_factory=session_factory)

    service.withdraw("200000000006", "20.00", ref="dup-with-ref")

    with pytest.raises(DuplicateTransactionRefError):
        service.withdraw("200000000006", "20.00", ref="dup-with-ref")

    # Balance must only have decremented once ($80.00, not $60.00)
    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("200000000006")
        assert acc is not None
        assert acc.balance == Money("80.00")


def test_withdraw_concurrent_double_spend_prevention(db_setup):
    """Verify concurrency: two simultaneous $100 withdrawals on $150 balance result in 1 success, 1 failure."""
    session_factory, _ = db_setup
    create_account(session_factory, "200000000007", balance="150.00")

    events: list[WithdrawalCompletedEvent] = []
    service = BankingService(session_factory=session_factory)
    service.subscribe(lambda ev: events.append(ev))

    def attempt_withdrawal(worker_id: int):
        try:
            return service.withdraw(
                account_number="200000000007",
                amount=Decimal("100.00"),
                description=f"Double-spend attempt from worker {worker_id}",
                ref=f"tx-double-{worker_id}",
                actor=f"worker_{worker_id}",
            )
        except InsufficientFundsError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(attempt_withdrawal, [1, 2]))

    # Exactly one result must be a TransactionDTO, and exactly one must be InsufficientFundsError
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, InsufficientFundsError)]

    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(failures) == 1, f"Expected 1 failure, got {len(failures)}"

    # Verify final balance is exactly $50.00 (150 - 100), never negative!
    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("200000000007")
        assert acc is not None
        assert acc.balance == Money("50.00")
        assert acc.version == 2

        tx_count = SQLTransactionRepository(sess).count_by_account("200000000007")
        assert tx_count == 1

    assert len(events) == 1


def test_withdraw_with_value_objects_and_faulty_listener(db_setup):
    """Verify withdraw accepts AccountNumber/Money VOs and listener exceptions do not disrupt commit."""
    session_factory, _ = db_setup
    create_account(session_factory, "200000000008", balance="100.00")

    def faulty_listener(event):
        raise RuntimeError("Faulty external analytics listener crash")

    service = BankingService(session_factory=session_factory)
    service.subscribe(faulty_listener)

    # Pass AccountNumber and Money instances directly
    dto = service.withdraw(
        account_number=AccountNumber("200000000008"),
        amount=Money("35.00"),
        description="VO withdrawal",
    )

    assert dto.amount == Decimal("35.00")
    assert dto.balance_after == Decimal("65.00")

    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("200000000008")
        assert acc is not None
        assert acc.balance == Money("65.00")


def test_withdraw_multi_threaded_simultaneous_valid_withdrawals(db_setup):
    """Verify multiple concurrent valid withdrawals serialize cleanly and sum precisely."""
    session_factory, _ = db_setup
    create_account(session_factory, "200000000009", balance="500.00")

    service = BankingService(session_factory=session_factory)

    # 10 workers each withdraw $40.00 -> total $400.00 withdrawn, expected final balance $100.00
    def perform_withdraw(idx):
        return service.withdraw(
            account_number="200000000009",
            amount=Decimal("40.00"),
            description=f"Concurrent withdraw {idx}",
            ref=f"tx-multi-with-{idx}",
            actor=f"atm_{idx}",
        )

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(perform_withdraw, range(10)))

    assert len(results) == 10

    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("200000000009")
        assert acc is not None
        assert acc.balance == Money("100.00")
        assert acc.version == 11

        tx_count = SQLTransactionRepository(sess).count_by_account("200000000009")
        assert tx_count == 10
