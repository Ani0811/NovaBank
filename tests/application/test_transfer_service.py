"""Unit and integration tests for BankingService account-to-account transfer workflow."""

import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from novabank.application.events import TransferCompletedEvent
from novabank.application.services.banking_service import BankingService
from novabank.domain.entities.account import Account
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountNotFoundError,
    CurrencyMismatchError,
    InsufficientFundsError,
    InvalidAmountError,
    SelfTransferError,
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
    acc_no: str,
    holder_name: str,
    balance: str = "100.00",
    currency: str = "USD",
    is_active: bool = True,
) -> Account:
    """Helper to seed an account in the database."""
    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            acc = Account(
                account_number=AccountNumber(acc_no),
                holder_name=holder_name,
                dob=date(1990, 5, 20),
                address_line="100 Main St",
                city="Boston",
                state="MA",
                country="USA",
                phone_number="5551112233",
                is_active=is_active,
                balance=Money(balance, currency=currency),
            )
            repo.save(acc)
    return acc


def test_transfer_success_path(db_setup):
    """Verify standard account-to-account transfer workflow."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000001", "Alice", balance="300.00")
    create_account(session_factory, "300000000002", "Bob", balance="100.00")

    events: list[TransferCompletedEvent] = []
    service = BankingService(
        session_factory=session_factory,
        event_publisher=lambda ev: events.append(ev),
    )

    result = service.transfer(
        source_account_number="300000000001",
        destination_account_number="300000000002",
        amount="80.00",
        description="Dinner split",
        correlation_id="corr-transfer-001",
        actor="alice_web",
    )

    # Verify Result DTO
    assert result.correlation_id == "corr-transfer-001"
    assert result.amount == Decimal("80.00")
    assert result.currency == "USD"

    # Source Transaction DTO
    src_tx = result.source_transaction
    assert src_tx.account_number == "300000000001"
    assert src_tx.direction == "DEBIT"
    assert src_tx.transaction_type == "TRANSFER_OUT"
    assert src_tx.amount == Decimal("80.00")
    assert src_tx.balance_after == Decimal("220.00")
    assert src_tx.transaction_ref == "corr-transfer-001-out"

    # Destination Transaction DTO
    dst_tx = result.destination_transaction
    assert dst_tx.account_number == "300000000002"
    assert dst_tx.direction == "CREDIT"
    assert dst_tx.transaction_type == "TRANSFER_IN"
    assert dst_tx.amount == Decimal("80.00")
    assert dst_tx.balance_after == Decimal("180.00")
    assert dst_tx.transaction_ref == "corr-transfer-001-in"

    # Verify Database state
    with session_factory() as sess:
        acc_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        acc_a = acc_repo.get_by_number("300000000001")
        acc_b = acc_repo.get_by_number("300000000002")
        assert acc_a.balance == Money("220.00")
        assert acc_b.balance == Money("180.00")
        assert acc_a.version == 2
        assert acc_b.version == 2

        # Verify conservation of total money in system ($300 + $100 = $400)
        assert acc_a.balance + acc_b.balance == Money("400.00")

        # Verify transactions in ledger
        assert tx_repo.get_by_ref("corr-transfer-001-out") is not None
        assert tx_repo.get_by_ref("corr-transfer-001-in") is not None

    # Verify Event Emitted
    assert len(events) == 1
    ev = events[0]
    assert ev.source_account == "300000000001"
    assert ev.destination_account == "300000000002"
    assert ev.amount == Decimal("80.00")
    assert ev.source_balance_after == Decimal("220.00")
    assert ev.destination_balance_after == Decimal("180.00")
    assert ev.correlation_id == "corr-transfer-001"


def test_transfer_self_transfer_rejected(db_setup):
    """Verify SelfTransferError when source and destination accounts are identical."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000003", "Charlie", balance="200.00")
    service = BankingService(session_factory=session_factory)

    with pytest.raises(SelfTransferError) as exc_info:
        service.transfer("300000000003", "300000000003", "50.00")

    assert "300000000003" in str(exc_info.value)

    # Balance remains untouched
    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number("300000000003")
        assert acc.balance == Money("200.00")


def test_transfer_insufficient_funds_rejected(db_setup):
    """Verify InsufficientFundsError when source has inadequate balance."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000004", "Dave", balance="50.00")
    create_account(session_factory, "300000000005", "Eve", balance="100.00")
    service = BankingService(session_factory=session_factory)

    with pytest.raises(InsufficientFundsError) as exc_info:
        service.transfer("300000000004", "300000000005", "50.01")

    assert "available balance is $50.00" in str(exc_info.value)

    # Verify both balances unchanged and zero transactions recorded
    with session_factory() as sess:
        acc_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        assert acc_repo.get_by_number("300000000004").balance == Money("50.00")
        assert acc_repo.get_by_number("300000000005").balance == Money("100.00")
        assert tx_repo.count_by_account("300000000004") == 0
        assert tx_repo.count_by_account("300000000005") == 0


def test_transfer_non_existent_accounts_rejected(db_setup):
    """Verify AccountNotFoundError when either account is missing."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000006", "Frank", balance="100.00")
    service = BankingService(session_factory=session_factory)

    # Missing destination
    with pytest.raises(AccountNotFoundError) as exc_info:
        service.transfer("300000000006", "999999999999", "10.00")
    assert "999999999999" in str(exc_info.value)

    # Missing source
    with pytest.raises(AccountNotFoundError) as exc_info:
        service.transfer("888888888888", "300000000006", "10.00")
    assert "888888888888" in str(exc_info.value)


def test_transfer_closed_account_rejected(db_setup):
    """Verify AccountClosedError when source or destination is inactive."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000007", "Grace", balance="100.00", is_active=False)
    create_account(session_factory, "300000000008", "Heidi", balance="100.00", is_active=True)
    service = BankingService(session_factory=session_factory)

    # Closed source
    with pytest.raises(AccountClosedError):
        service.transfer("300000000007", "300000000008", "20.00")

    # Closed destination
    with pytest.raises(AccountClosedError):
        service.transfer("300000000008", "300000000007", "20.00")


def test_transfer_non_positive_amount_rejected(db_setup):
    """Verify InvalidAmountError on zero, negative, or unparseable amount."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000009", "Ivan", balance="100.00")
    create_account(session_factory, "300000000010", "Judy", balance="100.00")
    service = BankingService(session_factory=session_factory)

    with pytest.raises(InvalidAmountError, match="strictly positive"):
        service.transfer("300000000009", "300000000010", "0.00")

    with pytest.raises(InvalidAmountError, match="strictly positive"):
        service.transfer("300000000009", "300000000010", "-5.00")

    with pytest.raises(InvalidAmountError, match="Invalid monetary transfer amount"):
        service.transfer("300000000009", "300000000010", "invalid")


def test_transfer_currency_mismatch_rejected(db_setup):
    """Verify CurrencyMismatchError when source and destination currencies differ."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000011", "Ken", balance="100.00", currency="USD")
    create_account(session_factory, "300000000012", "Leo", balance="100.00", currency="EUR")
    service = BankingService(session_factory=session_factory)

    with pytest.raises(CurrencyMismatchError, match="does not match destination currency"):
        service.transfer("300000000011", "300000000012", "10.00")


def test_transfer_rollback_on_partial_failure(db_setup, monkeypatch):
    """Verify atomic rollback if destination ledger recording fails."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000013", "Mallory", balance="200.00")
    create_account(session_factory, "300000000014", "Niaj", balance="100.00")
    service = BankingService(session_factory=session_factory)

    original_append = SQLTransactionRepository.append

    def mock_append(self, tx):
        # Fail only on the second transaction append (destination)
        if tx.transaction_type.value == "TRANSFER_IN":
            raise RuntimeError("Simulated crash writing destination transaction ledger")
        return original_append(self, tx)

    monkeypatch.setattr(SQLTransactionRepository, "append", mock_append)

    with pytest.raises(RuntimeError, match="Simulated crash"):
        service.transfer("300000000013", "300000000014", "50.00")

    # Verify both accounts rolled back completely; zero transactions committed
    with session_factory() as sess:
        acc_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        assert acc_repo.get_by_number("300000000013").balance == Money("200.00")
        assert acc_repo.get_by_number("300000000014").balance == Money("100.00")
        assert tx_repo.count_by_account("300000000013") == 0
        assert tx_repo.count_by_account("300000000014") == 0


def test_transfer_reverse_concurrent_transfers_deadlock_prevention(db_setup):
    """Verify simultaneous reverse transfers between A and B execute without deadlock."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000015", "Account A", balance="1000.00")
    create_account(session_factory, "300000000016", "Account B", balance="1000.00")

    service = BankingService(session_factory=session_factory)

    # 10 transfers A -> B ($10 each) and 10 transfers B -> A ($10 each) concurrently
    def transfer_task(args):
        idx, direction = args
        if direction == "A_TO_B":
            return service.transfer(
                source_account_number="300000000015",
                destination_account_number="300000000016",
                amount=Decimal("10.00"),
                description=f"A to B transfer {idx}",
                correlation_id=f"corr-atob-{idx}",
            )
        else:
            return service.transfer(
                source_account_number="300000000016",
                destination_account_number="300000000015",
                amount=Decimal("10.00"),
                description=f"B to A transfer {idx}",
                correlation_id=f"corr-btoa-{idx}",
            )

    tasks = [(i, "A_TO_B") for i in range(10)] + [(i, "B_TO_A") for i in range(10)]

    # Run with 10 concurrent worker threads
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = list(executor.map(transfer_task, tasks))

    assert len(results) == 20

    # Total balances must remain exact: $1000 and $1000 (net $0 change, total $2000 conserved)
    with session_factory() as sess:
        acc_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        acc_a = acc_repo.get_by_number("300000000015")
        acc_b = acc_repo.get_by_number("300000000016")

        assert acc_a.balance == Money("1000.00")
        assert acc_b.balance == Money("1000.00")
        assert acc_a.balance + acc_b.balance == Money("2000.00")

        # 10 debits + 10 credits = 20 transactions per account
        assert tx_repo.count_by_account("300000000015") == 20
        assert tx_repo.count_by_account("300000000016") == 20


def test_transfer_with_value_objects(db_setup):
    """Verify transfer accepts AccountNumber and Money instances directly."""
    session_factory, _ = db_setup
    create_account(session_factory, "300000000017", "Oscar", balance="150.00")
    create_account(session_factory, "300000000018", "Pam", balance="50.00")

    service = BankingService(session_factory=session_factory)

    result = service.transfer(
        source_account_number=AccountNumber("300000000017"),
        destination_account_number=AccountNumber("300000000018"),
        amount=Money("25.00"),
    )

    assert result.amount == Decimal("25.00")
    assert result.source_transaction.balance_after == Decimal("125.00")
    assert result.destination_transaction.balance_after == Decimal("75.00")
