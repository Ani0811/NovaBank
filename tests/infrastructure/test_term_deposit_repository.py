"""Tests for SQLTermDepositRepository."""

from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from novabank.domain.entities.account import Account
from novabank.domain.entities.term_deposit import (
    CertificateOfDeposit,
    TermDepositPayoutFrequency,
    TermDepositRolloverOption,
    TermDepositStatus,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.session import create_session_factory, init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_term_deposit_repository import (
    SQLTermDepositRepository,
)


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as sess:
        yield sess
        sess.rollback()
    engine.dispose()


def test_term_deposit_repository_save_get_and_list(session: Session) -> None:
    acc_repo = SQLAccountRepository(session)
    cd_repo = SQLTermDepositRepository(session)

    account = Account(
        account_number=AccountNumber("111122223333"),
        holder_name="Evergreen Trust LLC",
        dob=date(1975, 8, 12),
        address_line="200 Heritage Blvd",
        city="Charlotte",
        state="NC",
        country="USA",
        phone_number="7045550188",
        balance=Money("100000.00"),
    )
    acc_repo.save(account)
    session.flush()

    cd = CertificateOfDeposit(
        cd_id="CD-VAULT-001",
        account_number=AccountNumber("111122223333"),
        principal_amount=Money(Decimal("25000.00")),
        interest_rate_apy=Decimal("5.25"),
        tenor_months=12,
        issue_date=date(2026, 1, 15),
        maturity_date=date(2027, 1, 15),
        payout_frequency=TermDepositPayoutFrequency.AT_MATURITY,
        rollover_option=TermDepositRolloverOption.PAYOUT_AND_CLOSE,
        status=TermDepositStatus.ACTIVE,
    )
    cd_repo.save(cd)
    session.flush()

    # Get by ID
    loaded = cd_repo.get_by_id("CD-VAULT-001")
    assert loaded is not None
    assert loaded.cd_id == "CD-VAULT-001"
    assert loaded.account_number.value == "111122223333"
    assert loaded.principal_amount.amount == Decimal("25000.00")
    assert loaded.interest_rate_apy == Decimal("5.25")
    assert loaded.status == TermDepositStatus.ACTIVE
    assert len(loaded.accruals) == 12

    # Query with filters
    cds, count = cd_repo.list_term_deposits(account_number="111122223333", status="ACTIVE")
    assert count == 1
    assert len(cds) == 1
    assert cds[0].cd_id == "CD-VAULT-001"

    # Query with non-matching status
    empty_cds, empty_count = cd_repo.list_term_deposits(status="MATURED")
    assert empty_count == 0
    assert len(empty_cds) == 0
