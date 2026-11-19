"""Unit and integration tests for BankingService Term Deposit & CD Vault workflows."""

import os
import tempfile
from datetime import date, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from novabank.application.dto.term_deposit_dto import OpenCDRequestDTO
from novabank.application.events import (
    DepositCompletedEvent,
    TermDepositEarlyRedeemedEvent,
    TermDepositMaturedEvent,
    TermDepositOpenedEvent,
    WithdrawalCompletedEvent,
)
from novabank.application.services.banking_service import BankingService
from novabank.domain.entities.account import Account
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidTermDepositTermsError,
    TermDepositAlreadyClosedError,
    TermDepositNotFoundError,
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


def test_simulate_term_deposit(db_setup) -> None:
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    quote = service.simulate_term_deposit(
        principal=Decimal("50000.00"),
        tenor_months=12,
        apy_percentage=Decimal("5.50"),
    )
    assert quote.principal == Decimal("50000.00")
    assert quote.tenor_months == 12
    assert quote.projected_interest == Decimal("2750.00")
    assert quote.total_payout_at_maturity == Decimal("52750.00")


def test_open_term_deposit_workflow(db_setup) -> None:
    session_factory, _ = db_setup
    events = []
    service = BankingService(session_factory=session_factory, event_publisher=events.append)

    # Seed funding account
    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            repo.save(
                Account(
                    account_number=AccountNumber("111122223333"),
                    holder_name="Solomon Capital Partners",
                    dob=date(1980, 5, 10),
                    address_line="50 Wall St",
                    city="New York",
                    state="NY",
                    country="USA",
                    phone_number="2125550177",
                    balance=Money("80000.00"),
                )
            )

    req = OpenCDRequestDTO(
        account_number="111122223333",
        principal=Decimal("30000.00"),
        apy_percentage=Decimal("5.00"),
        tenor_months=12,
        payout_frequency="AT_MATURITY",
        rollover_option="PAYOUT_AND_CLOSE",
    )

    cd_dto = service.open_term_deposit(req, actor="head_teller")
    assert cd_dto.cd_id.startswith("CD-")
    assert cd_dto.status == "ACTIVE"
    assert cd_dto.principal_amount == Decimal("30000.00")
    assert cd_dto.projected_interest_at_maturity == Decimal("1500.00")

    # Funding account must be debited ($80,000 - $30,000 = $50,000)
    acc = service.get_account("111122223333")
    assert acc.balance == Decimal("50000.00")

    # Verify events
    with_event = next(e for e in events if isinstance(e, WithdrawalCompletedEvent))
    assert with_event.amount == Decimal("30000.00")

    cd_event = next(e for e in events if isinstance(e, TermDepositOpenedEvent))
    assert cd_event.cd_id == cd_dto.cd_id
    assert cd_event.principal == Decimal("30000.00")


def test_open_term_deposit_insufficient_funds(db_setup) -> None:
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            repo.save(
                Account(
                    account_number=AccountNumber("111122223333"),
                    holder_name="Solomon Capital Partners",
                    dob=date(1980, 5, 10),
                    address_line="50 Wall St",
                    city="New York",
                    state="NY",
                    country="USA",
                    phone_number="2125550177",
                    balance=Money("1000.00"),
                )
            )

    # Attempt to lock $5,000 with only $1,000 balance
    with pytest.raises(InsufficientFundsError):
        service.open_term_deposit(
            OpenCDRequestDTO(
                account_number="111122223333",
                principal=Decimal("5000.00"),
                apy_percentage=Decimal("5.00"),
                tenor_months=12,
            )
        )


def test_redeem_term_deposit_at_maturity(db_setup) -> None:
    session_factory, _ = db_setup
    events = []
    service = BankingService(session_factory=session_factory, event_publisher=events.append)

    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            repo.save(
                Account(
                    account_number=AccountNumber("111122223333"),
                    holder_name="Solomon Capital Partners",
                    dob=date(1980, 5, 10),
                    address_line="50 Wall St",
                    city="New York",
                    state="NY",
                    country="USA",
                    phone_number="2125550177",
                    balance=Money("100000.00"),
                )
            )

    cd_dto = service.open_term_deposit(
        OpenCDRequestDTO(
            account_number="111122223333",
            principal=Decimal("20000.00"),
            apy_percentage=Decimal("5.00"),
            tenor_months=12,
        )
    )
    # Balance after lockup is $80,000.00

    # Maturity payout: $20,000 principal + $1,000 interest = $21,000
    res = service.redeem_term_deposit(cd_dto.cd_id, is_premature=False, actor="system_settler")
    assert res.status == "MATURED"
    assert res.net_payout == Decimal("21000.00")
    assert res.interest_paid == Decimal("1000.00")
    assert res.penalty_deducted == Decimal("0.00")

    # Account balance after redemption is $80,000 + $21,000 = $101,000
    acc = service.get_account("111122223333")
    assert acc.balance == Decimal("101000.00")

    # Verify event
    mat_event = next(e for e in events if isinstance(e, TermDepositMaturedEvent))
    assert mat_event.cd_id == cd_dto.cd_id


def test_redeem_term_deposit_early_liquidation(db_setup) -> None:
    session_factory, _ = db_setup
    events = []
    service = BankingService(session_factory=session_factory, event_publisher=events.append)

    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            repo.save(
                Account(
                    account_number=AccountNumber("111122223333"),
                    holder_name="Solomon Capital Partners",
                    dob=date(1980, 5, 10),
                    address_line="50 Wall St",
                    city="New York",
                    state="NY",
                    country="USA",
                    phone_number="2125550177",
                    balance=Money("50000.00"),
                )
            )

    cd_dto = service.open_term_deposit(
        OpenCDRequestDTO(
            account_number="111122223333",
            principal=Decimal("10000.00"),
            apy_percentage=Decimal("6.00"),
            tenor_months=12,
        )
    )
    # Balance is $40,000

    # Break early on day 180
    today = date.today()
    halfway_date = today + timedelta(days=180)
    preview = service.preview_early_redemption(cd_dto.cd_id, as_of_date=halfway_date)
    assert preview.principal == Decimal("10000.00")
    assert preview.penalty > Decimal("0.00")

    # Execute early redemption
    res = service.redeem_term_deposit(cd_dto.cd_id, is_premature=True, as_of_date=halfway_date)
    assert res.status == "PREMATURELY_CLOSED"
    assert res.penalty_deducted > Decimal("0.00")
    assert res.net_payout > Decimal("9000.00")

    # Trying to redeem again raises TermDepositAlreadyClosedError
    with pytest.raises(TermDepositAlreadyClosedError):
        service.redeem_term_deposit(cd_dto.cd_id)
