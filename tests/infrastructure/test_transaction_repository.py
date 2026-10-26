"""Integration and unit tests for SQLTransactionRepository."""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from novabank.domain.entities.account import Account
from novabank.domain.entities.transaction import Transaction
from novabank.domain.exceptions import DuplicateTransactionRefError
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType
from novabank.infrastructure.db.session import create_session_factory, init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_transaction_repository import SQLTransactionRepository


@pytest.fixture
def session() -> Session:
    """Create in-memory SQLite database session for repository testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as sess:
        yield sess
        sess.rollback()
    engine.dispose()


@pytest.fixture
def account_repo(session: Session) -> SQLAccountRepository:
    """Create a SQLAccountRepository instance bound to the test session."""
    return SQLAccountRepository(session)


@pytest.fixture
def tx_repo(session: Session) -> SQLTransactionRepository:
    """Create a SQLTransactionRepository instance bound to the test session."""
    return SQLTransactionRepository(session)


def create_persisted_account(
    account_repo: SQLAccountRepository,
    session: Session,
    acc_no: str = "100000000001",
) -> Account:
    """Helper to persist an Account entity to satisfy foreign key relationships."""
    acc = Account(
        account_number=AccountNumber(acc_no),
        holder_name="Jane Doe",
        dob=date(1990, 1, 1),
        address_line="100 Main St",
        city="Boston",
        state="MA",
        country="USA",
        phone_number="5551234567",
        balance=Money("500.00"),
    )
    account_repo.save(acc)
    session.commit()
    return acc


def test_append_and_get_by_ref(
    tx_repo: SQLTransactionRepository,
    account_repo: SQLAccountRepository,
    session: Session,
):
    """Verify appending a transaction and retrieving it by unique reference."""
    create_persisted_account(account_repo, session, "100000000001")

    tx = Transaction(
        account_number=AccountNumber("100000000001"),
        transaction_type=TransactionType.DEPOSIT,
        direction=TransactionDirection.CREDIT,
        amount=Money("150.00"),
        balance_after=Money("650.00"),
        description="Payroll direct deposit",
        transaction_ref="tx-ref-001",
        created_by="payroll_system",
    )

    tx_repo.append(tx)
    session.commit()

    retrieved = tx_repo.get_by_ref("tx-ref-001")
    assert retrieved is not None
    assert retrieved.transaction_ref == "tx-ref-001"
    assert retrieved.account_number.value == "100000000001"
    assert retrieved.transaction_type == TransactionType.DEPOSIT
    assert retrieved.direction == TransactionDirection.CREDIT
    assert retrieved.amount == Money("150.00")
    assert retrieved.balance_after == Money("650.00")
    assert retrieved.description == "Payroll direct deposit"
    assert retrieved.created_by == "payroll_system"
    assert retrieved.transaction_id is not None

    # Non-existent reference returns None
    assert tx_repo.get_by_ref("non-existent-ref") is None


def test_duplicate_transaction_ref_raises_duplicate_error(
    tx_repo: SQLTransactionRepository,
    account_repo: SQLAccountRepository,
    session: Session,
):
    """Verify idempotency: duplicate transaction_ref raises DuplicateTransactionRefError."""
    create_persisted_account(account_repo, session, "100000000001")

    tx1 = Transaction(
        account_number=AccountNumber("100000000001"),
        transaction_type=TransactionType.DEPOSIT,
        direction=TransactionDirection.CREDIT,
        amount=Money("50.00"),
        balance_after=Money("550.00"),
        transaction_ref="tx-duplicate-test",
    )
    tx_repo.append(tx1)
    session.commit()

    # Second transaction with identical transaction_ref
    tx2 = Transaction(
        account_number=AccountNumber("100000000001"),
        transaction_type=TransactionType.WITHDRAWAL,
        direction=TransactionDirection.DEBIT,
        amount=Money("20.00"),
        balance_after=Money("530.00"),
        transaction_ref="tx-duplicate-test",
    )

    with pytest.raises(DuplicateTransactionRefError, match="tx-duplicate-test"):
        tx_repo.append(tx2)


def test_list_by_account_ordering_and_pagination(
    tx_repo: SQLTransactionRepository,
    account_repo: SQLAccountRepository,
    session: Session,
):
    """Verify pagination and chronological ordering."""
    create_persisted_account(account_repo, session, "100000000002")
    base_time = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)

    for i in range(5):
        tx = Transaction(
            account_number=AccountNumber("100000000002"),
            transaction_type=TransactionType.DEPOSIT,
            direction=TransactionDirection.CREDIT,
            amount=Money(f"{10 * (i + 1)}.00"),
            balance_after=Money("500.00"),
            description=f"Transaction {i}",
            transaction_ref=f"tx-page-{i}",
            created_at=base_time + timedelta(hours=i),
        )
        tx_repo.append(tx)
    session.commit()

    # Total count
    assert tx_repo.count_by_account("100000000002") == 5
    assert tx_repo.count_by_account(AccountNumber("100000000002")) == 5

    # Descending list (newest first)
    desc_list = tx_repo.list_by_account("100000000002", limit=3, offset=0, descending=True)
    assert len(desc_list) == 3
    assert desc_list[0].description == "Transaction 4"
    assert desc_list[1].description == "Transaction 3"
    assert desc_list[2].description == "Transaction 2"

    # Offset 3 descending
    desc_tail = tx_repo.list_by_account("100000000002", limit=3, offset=3, descending=True)
    assert len(desc_tail) == 2
    assert desc_tail[0].description == "Transaction 1"
    assert desc_tail[1].description == "Transaction 0"

    # Ascending list (oldest first)
    asc_list = tx_repo.list_by_account("100000000002", limit=2, offset=0, descending=False)
    assert len(asc_list) == 2
    assert asc_list[0].description == "Transaction 0"
    assert asc_list[1].description == "Transaction 1"


def test_list_and_count_by_account_date_filtering(
    tx_repo: SQLTransactionRepository,
    account_repo: SQLAccountRepository,
    session: Session,
):
    """Verify transactions can be filtered by start_date and end_date."""
    create_persisted_account(account_repo, session, "100000000003")

    t1 = datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 3, 30, 12, 0, 0, tzinfo=timezone.utc)

    for idx, t in enumerate([t1, t2, t3]):
        tx = Transaction(
            account_number=AccountNumber("100000000003"),
            transaction_type=TransactionType.TRANSFER_OUT,
            direction=TransactionDirection.DEBIT,
            amount=Money("25.00"),
            balance_after=Money("475.00"),
            description=f"Transfer {idx}",
            transaction_ref=f"tx-date-{idx}",
            created_at=t,
        )
        tx_repo.append(tx)
    session.commit()

    # Filter with start_date only
    after_mid_march = tx_repo.list_by_account(
        "100000000003",
        start_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )
    assert len(after_mid_march) == 2
    assert (
        tx_repo.count_by_account(
            "100000000003",
            start_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
        )
        == 2
    )

    # Filter with end_date only
    before_mid_march = tx_repo.list_by_account(
        "100000000003",
        end_date=datetime(2026, 3, 20, tzinfo=timezone.utc),
    )
    assert len(before_mid_march) == 2
    assert (
        tx_repo.count_by_account(
            "100000000003",
            end_date=datetime(2026, 3, 20, tzinfo=timezone.utc),
        )
        == 2
    )

    # Filter with both start_date and end_date
    window = tx_repo.list_by_account(
        "100000000003",
        start_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
        end_date=datetime(2026, 3, 20, tzinfo=timezone.utc),
    )
    assert len(window) == 1
    assert window[0].description == "Transfer 1"
    assert (
        tx_repo.count_by_account(
            "100000000003",
            start_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
            end_date=datetime(2026, 3, 20, tzinfo=timezone.utc),
        )
        == 1
    )


def test_transaction_entity_equality_and_hashing():
    """Verify Transaction entity equality and hashing based on transaction_ref."""
    acc_no = AccountNumber("100000000001")
    tx1 = Transaction(
        account_number=acc_no,
        transaction_type=TransactionType.DEPOSIT,
        direction=TransactionDirection.CREDIT,
        amount=Money("10.00"),
        balance_after=Money("100.00"),
        transaction_ref="ref-xyz-123",
    )
    tx2 = Transaction(
        account_number=acc_no,
        transaction_type=TransactionType.WITHDRAWAL,
        direction=TransactionDirection.DEBIT,
        amount=Money("20.00"),
        balance_after=Money("80.00"),
        transaction_ref="ref-xyz-123",
    )
    tx3 = Transaction(
        account_number=acc_no,
        transaction_type=TransactionType.DEPOSIT,
        direction=TransactionDirection.CREDIT,
        amount=Money("10.00"),
        balance_after=Money("100.00"),
        transaction_ref="ref-xyz-999",
    )

    assert tx1 == tx2  # Same transaction_ref
    assert tx1 != tx3  # Different transaction_ref
    assert tx1 != "not_a_tx"
    assert hash(tx1) == hash(tx2)


def test_append_integrity_error_triggers_duplicate_error(
    tx_repo: SQLTransactionRepository,
    account_repo: SQLAccountRepository,
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
):
    """Verify concurrency edge-case where DB flush raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    create_persisted_account(account_repo, session, "100000000004")

    tx = Transaction(
        account_number=AccountNumber("100000000004"),
        transaction_type=TransactionType.DEPOSIT,
        direction=TransactionDirection.CREDIT,
        amount=Money("10.00"),
        balance_after=Money("510.00"),
        transaction_ref="tx-integrity-race",
    )

    def mock_flush():
        raise IntegrityError("mock statement", {}, Exception("Duplicate key"))

    monkeypatch.setattr(session, "flush", mock_flush)

    with pytest.raises(DuplicateTransactionRefError, match="tx-integrity-race"):
        tx_repo.append(tx)
