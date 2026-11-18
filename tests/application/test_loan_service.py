"""Unit and integration tests for BankingService Commercial Loan workflows."""

import os
import tempfile
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from novabank.application.dto.loan_dto import LoanOriginationRequestDTO
from novabank.application.events import (
    DepositCompletedEvent,
    LoanOriginatedEvent,
    LoanPaidOffEvent,
    LoanRepaymentProcessedEvent,
    WithdrawalCompletedEvent,
)
from novabank.application.services.banking_service import BankingService
from novabank.domain.entities.account import Account
from novabank.domain.entities.loan import LoanStatus, LoanType
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidLoanTermsError,
    LoanAlreadyPaidOffError,
    LoanNotFoundError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.session import init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository


@pytest.fixture
def db_setup():
    """Create a temporary SQLite database for clean test isolation."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    engine = create_engine(f"sqlite:///{db_path}?timeout=30")
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
    except OSError:
        pass


def test_calculate_loan_quote(db_setup) -> None:
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    quote = service.calculate_loan_quote(
        principal=Decimal("120000.00"),
        apr_percentage=Decimal("6.00"),
        term_months=12,
    )
    assert quote.principal == Decimal("120000.00")
    assert quote.term_months == 12
    assert quote.monthly_installment > Decimal("10000.00")
    assert quote.total_interest > Decimal("0.00")
    assert quote.total_payable == quote.principal + quote.total_interest


def test_originate_loan_and_disbursement(db_setup) -> None:
    session_factory, _ = db_setup
    events = []
    service = BankingService(session_factory=session_factory, event_publisher=events.append)

    # Seed borrower account
    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            repo.save(
                Account(
                    account_number=AccountNumber("111122223333"),
                    holder_name="Omni Enterprises LLC",
                    dob=date(1990, 1, 1),
                    address_line="500 Innovation Way",
                    city="Dallas",
                    state="TX",
                    country="USA",
                    phone_number="5551112233",
                    balance=Money("5000.00"),
                )
            )

    req = LoanOriginationRequestDTO(
        account_number="111122223333",
        loan_type=LoanType.COMMERCIAL_EQUIPMENT.value,
        principal=Decimal("50000.00"),
        apr_percentage=Decimal("8.00"),
        term_months=12,
        purpose="Factory Equipment",
    )

    loan_dto = service.originate_loan(req, actor="senior_officer")
    assert loan_dto.loan_id.startswith("LN-")
    assert loan_dto.status == "ACTIVE"
    assert loan_dto.principal_amount == Decimal("50000.00")
    assert len(loan_dto.schedule) == 12

    # Verify borrower checking account was credited atomically ($5,000 + $50,000 = $55,000)
    acc = service.get_account("111122223333")
    assert acc.balance == Decimal("55000.00")

    # Verify emitted events
    deposit_event = next(e for e in events if isinstance(e, DepositCompletedEvent))
    assert deposit_event.amount == Decimal("50000.00")

    orig_event = next(e for e in events if isinstance(e, LoanOriginatedEvent))
    assert orig_event.loan_id == loan_dto.loan_id
    assert orig_event.actor == "senior_officer"


def test_originate_loan_rejection_conditions(db_setup) -> None:
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    # Non-existent account
    with pytest.raises(AccountNotFoundError):
        service.originate_loan(
            LoanOriginationRequestDTO(
                account_number="999999999999",
                loan_type="TERM_LOAN",
                principal=Decimal("10000.00"),
                apr_percentage=Decimal("5.0"),
                term_months=12,
            )
        )

    # Invalid APR
    with pytest.raises(InvalidLoanTermsError):
        service.originate_loan(
            LoanOriginationRequestDTO(
                account_number="111122223333",
                loan_type="TERM_LOAN",
                principal=Decimal("10000.00"),
                apr_percentage=Decimal("0.00"),
                term_months=12,
            )
        )


def test_repay_loan_installment_and_full_payoff(db_setup) -> None:
    session_factory, _ = db_setup
    events = []
    service = BankingService(session_factory=session_factory, event_publisher=events.append)

    # Seed borrower account with enough funds
    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            repo.save(
                Account(
                    account_number=AccountNumber("111122223333"),
                    holder_name="Omni Enterprises LLC",
                    dob=date(1990, 1, 1),
                    address_line="500 Innovation Way",
                    city="Dallas",
                    state="TX",
                    country="USA",
                    phone_number="5551112233",
                    balance=Money("20000.00"),
                )
            )

    # Originate short 2-month facility
    req = LoanOriginationRequestDTO(
        account_number="111122223333",
        loan_type=LoanType.WORKING_CAPITAL.value,
        principal=Decimal("2000.00"),
        apr_percentage=Decimal("6.00"),
        term_months=2,
    )
    loan_dto = service.originate_loan(req, actor="officer")
    # Balance is now $20,000 + $2,000 = $22,000

    # Process first installment
    repay_res1 = service.repay_loan_installment(loan_dto.loan_id, actor="teller_1")
    assert repay_res1.installment_number == 1
    assert repay_res1.new_status == "ACTIVE"
    assert repay_res1.remaining_balance > Decimal("0.00")

    # Process second installment (final payoff)
    repay_res2 = service.repay_loan_installment(loan_dto.loan_id, actor="teller_1")
    assert repay_res2.installment_number == 2
    assert repay_res2.new_status == "PAID_OFF"
    assert repay_res2.remaining_balance == Decimal("0.00")

    # Verify LoanPaidOffEvent emitted
    paid_off_event = next(e for e in events if isinstance(e, LoanPaidOffEvent))
    assert paid_off_event.loan_id == loan_dto.loan_id

    # Trying to repay again raises LoanAlreadyPaidOffError
    with pytest.raises(LoanAlreadyPaidOffError):
        service.repay_loan_installment(loan_dto.loan_id)


def test_export_loan_schedule_csv(db_setup) -> None:
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            repo.save(
                Account(
                    account_number=AccountNumber("111122223333"),
                    holder_name="Omni Enterprises LLC",
                    dob=date(1990, 1, 1),
                    address_line="500 Innovation Way",
                    city="Dallas",
                    state="TX",
                    country="USA",
                    phone_number="5551112233",
                    balance=Money("50000.00"),
                )
            )

    req = LoanOriginationRequestDTO(
        account_number="111122223333",
        loan_type=LoanType.COMMERCIAL_MORTGAGE.value,
        principal=Decimal("10000.00"),
        apr_percentage=Decimal("5.50"),
        term_months=6,
    )
    loan_dto = service.originate_loan(req)

    csv_data = service.export_loan_schedule_csv(loan_dto.loan_id)
    assert "# NovaBank Commercial Loan Amortization Schedule" in csv_data
    assert "Installment #" in csv_data
    assert "SCHEDULED" in csv_data
