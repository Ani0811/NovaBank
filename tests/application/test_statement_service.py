"""Comprehensive tests for StatementService and AccountStatementDTO reconciliation."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.statement_dto import AccountStatementDTO
from novabank.application.services.banking_service import BankingService
from novabank.application.services.statement_service import StatementService
from novabank.domain.entities.account import Account
from novabank.domain.entities.transaction import Transaction
from novabank.domain.exceptions import AccountNotFoundError
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType
from novabank.infrastructure.db.models import Base
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_transaction_repository import SQLTransactionRepository


@pytest.fixture
def session_factory():
    """Create in-memory SQLite engine and session factory with StaticPool."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def banking_service(session_factory):
    """Create BankingService configured with test session factory."""
    return BankingService(session_factory=session_factory)


@pytest.fixture
def statement_service(session_factory):
    """Create StatementService configured with test session factory."""
    return StatementService(session_factory=session_factory)


def _create_persisted_account(
    session_factory,
    acc_num: str,
    holder_name: str = "Alice Walker",
    balance: Decimal = Decimal("0.00"),
    is_active: bool = True,
) -> Account:
    with session_factory() as session:
        with session.begin():
            repo = SQLAccountRepository(session)
            acc = Account(
                account_number=AccountNumber(acc_num),
                holder_name=holder_name,
                dob=date(1990, 5, 12),
                address_line="742 Evergreen Terrace",
                city="Springfield",
                state="IL",
                country="USA",
                phone_number="5551234567",
                balance=Money(balance),
                is_active=is_active,
            )
            repo.save(acc)
    return acc


def test_statement_zero_transactions_opened_with_zero_balance(statement_service, session_factory):
    """Verify statement for an account with zero balance and zero transactions."""
    _create_persisted_account(session_factory, "111122223333", balance=Decimal("0.00"))

    statement = statement_service.generate_statement("111122223333")

    assert statement.account_number == "111122223333"
    assert statement.holder_name == "Alice Walker"
    assert statement.account_status == "Active"
    assert statement.opening_balance == Decimal("0.00")
    assert statement.total_credits == Decimal("0.00")
    assert statement.total_debits == Decimal("0.00")
    assert statement.net_change == Decimal("0.00")
    assert statement.closing_balance == Decimal("0.00")
    assert statement.transaction_count == 0
    assert len(statement.entries) == 0
    assert statement.is_reconciled() is True


def test_statement_single_initial_deposit(banking_service, statement_service):
    """Verify statement for account opened with an initial deposit."""
    res = banking_service.open_account(
        holder_name="Bob Builder",
        dob=date(1985, 3, 22),
        address_line="10 Main St",
        city="Denver",
        state="CO",
        country="USA",
        phone_number="5552223333",
        initial_deposit=Decimal("500.00"),
    )
    acc_num = res.account.account_number

    statement = statement_service.generate_statement(acc_num)

    assert statement.opening_balance == Decimal("0.00")
    assert statement.total_credits == Decimal("500.00")
    assert statement.total_debits == Decimal("0.00")
    assert statement.net_change == Decimal("500.00")
    assert statement.closing_balance == Decimal("500.00")
    assert statement.transaction_count == 1
    assert statement.is_reconciled() is True

    entry = statement.entries[0]
    assert entry.transaction_type == "DEPOSIT"
    assert entry.direction == "CREDIT"
    assert entry.amount == Decimal("500.00")
    assert entry.credit_amount == Decimal("500.00")
    assert entry.debit_amount is None
    assert entry.balance_after == Decimal("500.00")
    assert entry.formatted_credit == "+$500.00"
    assert entry.formatted_debit == ""


def test_statement_multiple_transactions_full_reconciliation(banking_service, statement_service):
    """Verify statement for multiple deposits and withdrawals reconciles mathematically."""
    res = banking_service.open_account(
        holder_name="Charlie Brown",
        dob=date(1992, 7, 19),
        address_line="123 Peanuts Lane",
        city="Minneapolis",
        state="MN",
        country="USA",
        phone_number="5553334444",
        initial_deposit=Decimal("1000.00"),
    )
    acc_num = res.account.account_number

    # Execute subsequent transactions
    banking_service.deposit(acc_num, Decimal("200.00"), description="Paycheck bonus")
    banking_service.withdraw(acc_num, Decimal("350.00"), description="Groceries")
    banking_service.deposit(acc_num, Decimal("150.00"), description="Dividend")
    banking_service.withdraw(acc_num, Decimal("50.00"), description="Coffee")

    statement = statement_service.generate_statement(acc_num)

    # Initial Deposit ($1000) + Bonus ($200) + Dividend ($150) = $1350.00
    expected_credits = Decimal("1350.00")
    # Groceries ($350) + Coffee ($50) = $400.00
    expected_debits = Decimal("400.00")
    expected_closing = Decimal("950.00")

    assert statement.opening_balance == Decimal("0.00")
    assert statement.total_credits == expected_credits
    assert statement.total_debits == expected_debits
    assert statement.net_change == Decimal("950.00")
    assert statement.closing_balance == expected_closing
    assert statement.transaction_count == 5
    assert statement.is_reconciled() is True

    # Mathematical identity assertion
    assert (
        statement.opening_balance + statement.total_credits - statement.total_debits
    ) == statement.closing_balance


def test_statement_with_sub_period_and_opening_balance(session_factory, statement_service):
    """Verify opening balance computation when statement specifies a date window."""
    acc_num = "333344445555"
    _create_persisted_account(session_factory, acc_num, holder_name="David Miller")

    # Seed 5 transactions on explicit dates
    base_date = datetime(2026, 4, 1, 10, 0, 0, tzinfo=timezone.utc)
    # Day 1: Deposit 1000 -> bal 1000
    # Day 2: Deposit 500  -> bal 1500
    # Day 3: Withdraw 200 -> bal 1300
    # Day 4: Deposit 400  -> bal 1700
    # Day 5: Withdraw 100 -> bal 1600
    # Day 6: Deposit 300  -> bal 1900
    tx_plan = [
        (
            TransactionType.DEPOSIT,
            TransactionDirection.CREDIT,
            Decimal("1000.00"),
            Decimal("1000.00"),
            "T1",
        ),
        (
            TransactionType.DEPOSIT,
            TransactionDirection.CREDIT,
            Decimal("500.00"),
            Decimal("1500.00"),
            "T2",
        ),
        (
            TransactionType.WITHDRAWAL,
            TransactionDirection.DEBIT,
            Decimal("200.00"),
            Decimal("1300.00"),
            "T3",
        ),
        (
            TransactionType.DEPOSIT,
            TransactionDirection.CREDIT,
            Decimal("400.00"),
            Decimal("1700.00"),
            "T4",
        ),
        (
            TransactionType.WITHDRAWAL,
            TransactionDirection.DEBIT,
            Decimal("100.00"),
            Decimal("1600.00"),
            "T5",
        ),
        (
            TransactionType.DEPOSIT,
            TransactionDirection.CREDIT,
            Decimal("300.00"),
            Decimal("1900.00"),
            "T6",
        ),
    ]

    with session_factory() as session:
        with session.begin():
            acc_repo = SQLAccountRepository(session)
            tx_repo = SQLTransactionRepository(session)
            acc = acc_repo.get_by_number(acc_num)
            for idx, (ttype, direction, amount, bal_after, desc) in enumerate(tx_plan):
                tx = Transaction(
                    account_number=AccountNumber(acc_num),
                    transaction_type=ttype,
                    direction=direction,
                    amount=Money(amount),
                    balance_after=Money(bal_after),
                    description=desc,
                    transaction_ref=f"tx-period-{idx}",
                    created_at=base_date + timedelta(days=idx),
                )
                tx_repo.append(tx)
            acc._balance = Money(Decimal("1900.00"))
            acc_repo.save(acc)

    # Request statement for window [Day 2, Day 4] (2026-04-03 to 2026-04-05)
    # Prior to Day 2 (Day 1, 2026-04-02): Last transaction had balance $1500.00.
    start_dt = base_date + timedelta(days=2)  # Day 2: 2026-04-03 10:00:00
    end_dt = base_date + timedelta(days=4)  # Day 4: 2026-04-05 10:00:00

    statement = statement_service.generate_statement(
        account_number=acc_num,
        start_date=start_dt,
        end_date=end_dt,
    )

    # Opening balance prior to start_dt must equal $1500.00 (from T2 on Day 1)
    assert statement.opening_balance == Decimal("1500.00")

    # In period: T3 (Withdraw 200), T4 (Deposit 400), T5 (Withdraw 100)
    assert statement.transaction_count == 3
    assert statement.total_credits == Decimal("400.00")
    assert statement.total_debits == Decimal("300.00")
    assert statement.net_change == Decimal("100.00")

    # Closing balance = Opening ($1500) + Credits ($400) - Debits ($300) = $1600.00
    assert statement.closing_balance == Decimal("1600.00")
    assert statement.is_reconciled() is True

    # Verify descriptions of entries in period
    assert [e.description for e in statement.entries] == ["T3", "T4", "T5"]


def test_statement_boundary_dates_exact_timestamps(session_factory, statement_service):
    """Verify inclusive boundary handling on start_date and end_date."""
    acc_num = "555566667777"
    _create_persisted_account(session_factory, acc_num, holder_name="Eva Green")

    t1 = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 6, 5, 12, 0, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 6, 10, 23, 59, 59, 999999, tzinfo=timezone.utc)
    t4 = datetime(2026, 6, 11, 0, 0, 0, tzinfo=timezone.utc)

    with session_factory() as session:
        with session.begin():
            tx_repo = SQLTransactionRepository(session)
            tx1 = Transaction(
                account_number=AccountNumber(acc_num),
                transaction_type=TransactionType.DEPOSIT,
                direction=TransactionDirection.CREDIT,
                amount=Money("100.00"),
                balance_after=Money("100.00"),
                description="T1 Start Boundary",
                transaction_ref="tx-bound-1",
                created_at=t1,
            )
            tx2 = Transaction(
                account_number=AccountNumber(acc_num),
                transaction_type=TransactionType.DEPOSIT,
                direction=TransactionDirection.CREDIT,
                amount=Money("50.00"),
                balance_after=Money("150.00"),
                description="T2 Mid",
                transaction_ref="tx-bound-2",
                created_at=t2,
            )
            tx3 = Transaction(
                account_number=AccountNumber(acc_num),
                transaction_type=TransactionType.WITHDRAWAL,
                direction=TransactionDirection.DEBIT,
                amount=Money("20.00"),
                balance_after=Money("130.00"),
                description="T3 End Boundary",
                transaction_ref="tx-bound-3",
                created_at=t3,
            )
            tx4 = Transaction(
                account_number=AccountNumber(acc_num),
                transaction_type=TransactionType.DEPOSIT,
                direction=TransactionDirection.CREDIT,
                amount=Money("40.00"),
                balance_after=Money("170.00"),
                description="T4 Outside Period",
                transaction_ref="tx-bound-4",
                created_at=t4,
            )
            for t in [tx1, tx2, tx3, tx4]:
                tx_repo.append(t)

    # Filter with date objects: date(2026, 6, 1) to date(2026, 6, 10)
    statement = statement_service.generate_statement(
        account_number=acc_num,
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 10),
    )

    # Must include T1, T2, T3 (up to 2026-06-10 23:59:59.999999) and exclude T4
    assert statement.transaction_count == 3
    assert [e.description for e in statement.entries] == [
        "T1 Start Boundary",
        "T2 Mid",
        "T3 End Boundary",
    ]
    assert statement.opening_balance == Decimal("0.00")
    assert statement.total_credits == Decimal("150.00")
    assert statement.total_debits == Decimal("20.00")
    assert statement.closing_balance == Decimal("130.00")
    assert statement.is_reconciled() is True


def test_statement_empty_period_between_existing_transactions(session_factory, statement_service):
    """Verify statement for a date range with zero transactions between existing activity."""
    acc_num = "777788889999"
    _create_persisted_account(session_factory, acc_num, holder_name="Frank Sinatra")

    t_jan = datetime(2026, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    t_mar = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)

    with session_factory() as session:
        with session.begin():
            tx_repo = SQLTransactionRepository(session)
            tx_repo.append(
                Transaction(
                    account_number=AccountNumber(acc_num),
                    transaction_type=TransactionType.DEPOSIT,
                    direction=TransactionDirection.CREDIT,
                    amount=Money("800.00"),
                    balance_after=Money("800.00"),
                    description="January Deposit",
                    transaction_ref="tx-jan",
                    created_at=t_jan,
                )
            )
            tx_repo.append(
                Transaction(
                    account_number=AccountNumber(acc_num),
                    transaction_type=TransactionType.DEPOSIT,
                    direction=TransactionDirection.CREDIT,
                    amount=Money("200.00"),
                    balance_after=Money("1000.00"),
                    description="March Deposit",
                    transaction_ref="tx-mar",
                    created_at=t_mar,
                )
            )

    # Request February statement
    statement = statement_service.generate_statement(
        account_number=acc_num,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )

    assert statement.transaction_count == 0
    assert len(statement.entries) == 0
    assert statement.opening_balance == Decimal("800.00")
    assert statement.total_credits == Decimal("0.00")
    assert statement.total_debits == Decimal("0.00")
    assert statement.net_change == Decimal("0.00")
    assert statement.closing_balance == Decimal("800.00")
    assert statement.is_reconciled() is True


def test_statement_non_existent_account_raises_account_not_found(statement_service):
    """Verify attempting to generate statement for non-existent account raises AccountNotFoundError."""
    with pytest.raises(AccountNotFoundError, match="Account '999999999999' not found"):
        statement_service.generate_statement("999999999999")


def test_statement_invalid_date_range_raises_value_error(statement_service, session_factory):
    """Verify passing start_date after end_date raises ValueError."""
    acc_num = "121212121212"
    _create_persisted_account(session_factory, acc_num)

    with pytest.raises(ValueError, match="cannot be after end date"):
        statement_service.generate_statement(
            account_number=acc_num,
            start_date=date(2026, 12, 31),
            end_date=date(2026, 1, 1),
        )


def test_statement_formatting_and_properties(banking_service, statement_service):
    """Verify formatted property strings for currency display and net changes."""
    res = banking_service.open_account(
        holder_name="Grace Hopper",
        dob=date(1995, 12, 9),
        address_line="50 Tech Way",
        city="Arlington",
        state="VA",
        country="USA",
        phone_number="5559998888",
        initial_deposit=Decimal("1234.56"),
    )
    acc_num = res.account.account_number

    banking_service.withdraw(acc_num, Decimal("234.56"), description="Hardware Purchase")

    statement = statement_service.generate_statement(acc_num)

    assert statement.formatted_opening_balance == "$0.00 USD"
    assert statement.formatted_total_credits == "$1,234.56 USD"
    assert statement.formatted_total_debits == "$234.56 USD"
    assert statement.formatted_net_change == "+$1,000.00 USD"
    assert statement.formatted_closing_balance == "$1,000.00 USD"


def test_banking_service_get_statement_delegation(banking_service):
    """Verify BankingService.get_statement convenience method delegates correctly."""
    res = banking_service.open_account(
        holder_name="Henry Ford",
        dob=date(1980, 7, 30),
        address_line="100 Motor Blvd",
        city="Detroit",
        state="MI",
        country="USA",
        phone_number="5554443333",
        initial_deposit=Decimal("3000.00"),
    )
    acc_num = res.account.account_number

    banking_service.withdraw(acc_num, Decimal("500.00"), description="Part Order")

    statement = banking_service.get_statement(acc_num)

    assert isinstance(statement, AccountStatementDTO)
    assert statement.account_number == acc_num
    assert statement.closing_balance == Decimal("2500.00")
    assert statement.transaction_count == 2
    assert statement.is_reconciled() is True


def test_statement_transfer_transactions_debit_and_credit_mapping(
    banking_service, statement_service
):
    """Verify transfer transactions properly map to debit and credit entries in statements."""
    src = banking_service.open_account(
        holder_name="Sender Sarah",
        dob=date(1991, 1, 1),
        address_line="100 West St",
        city="San Jose",
        state="CA",
        country="USA",
        phone_number="5551231111",
        initial_deposit=Decimal("800.00"),
    )
    dst = banking_service.open_account(
        holder_name="Receiver Ray",
        dob=date(1993, 2, 2),
        address_line="200 East St",
        city="San Jose",
        state="CA",
        country="USA",
        phone_number="5551232222",
        initial_deposit=Decimal("100.00"),
    )

    banking_service.transfer(
        source_account_number=src.account.account_number,
        destination_account_number=dst.account.account_number,
        amount=Decimal("250.00"),
        description="Consulting Fee",
    )

    # Source statement: Initial Deposit $800 (CREDIT) + Transfer Out $250 (DEBIT)
    src_statement = statement_service.generate_statement(src.account.account_number)
    assert src_statement.closing_balance == Decimal("550.00")
    assert src_statement.total_credits == Decimal("800.00")
    assert src_statement.total_debits == Decimal("250.00")
    assert src_statement.entries[1].transaction_type == "TRANSFER_OUT"
    assert src_statement.entries[1].direction == "DEBIT"
    assert src_statement.entries[1].debit_amount == Decimal("250.00")
    assert src_statement.entries[1].credit_amount is None
    assert src_statement.is_reconciled() is True

    # Destination statement: Initial Deposit $100 (CREDIT) + Transfer In $250 (CREDIT)
    dst_statement = statement_service.generate_statement(dst.account.account_number)
    assert dst_statement.closing_balance == Decimal("350.00")
    assert dst_statement.total_credits == Decimal("350.00")
    assert dst_statement.total_debits == Decimal("0.00")
    assert dst_statement.entries[1].transaction_type == "TRANSFER_IN"
    assert dst_statement.entries[1].direction == "CREDIT"
    assert dst_statement.entries[1].credit_amount == Decimal("250.00")
    assert dst_statement.entries[1].debit_amount is None
    assert dst_statement.is_reconciled() is True
