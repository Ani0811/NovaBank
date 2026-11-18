"""Tests for SQLLoanRepository."""

from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from novabank.domain.entities.account import Account
from novabank.domain.entities.loan import LoanContract, LoanStatus, LoanType
from novabank.domain.services.amortization_calculator import AmortizationCalculator
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.session import create_session_factory, init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_loan_repository import SQLLoanRepository


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as sess:
        yield sess
        sess.rollback()
    engine.dispose()


def test_loan_repository_save_get_and_list(session: Session) -> None:
    acc_repo = SQLAccountRepository(session)
    loan_repo = SQLLoanRepository(session)

    account = Account(
        account_number=AccountNumber("111122223333"),
        holder_name="Acme Corp",
        dob=date(1985, 5, 20),
        address_line="100 Commercial Blvd",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5559876543",
        balance=Money("25000.00"),
    )
    acc_repo.save(account)
    session.flush()

    principal = Money(Decimal("60000.00"))
    apr = Decimal("7.00")
    term = 12
    schedule = AmortizationCalculator.generate_amortization_schedule(principal, apr, term)
    emi = AmortizationCalculator.calculate_monthly_installment(principal, apr, term)
    total_interest = Money(sum(item.interest_amount.amount for item in schedule))

    loan = LoanContract(
        loan_id="LN-ACME-001",
        account_number=AccountNumber("111122223333"),
        loan_type=LoanType.COMMERCIAL_EQUIPMENT,
        principal_amount=principal,
        interest_rate_apr=apr,
        term_months=term,
        monthly_installment=emi,
        outstanding_balance=principal,
        total_interest=total_interest,
        status=LoanStatus.SUBMITTED,
        schedule=schedule,
        purpose="Machinery Acquisition",
    )
    loan.disburse("officer")
    loan_repo.save(loan)
    session.flush()

    # Fetch by ID
    loaded = loan_repo.get_by_id("LN-ACME-001")
    assert loaded is not None
    assert loaded.loan_id == "LN-ACME-001"
    assert loaded.account_number.value == "111122223333"
    assert loaded.status == LoanStatus.ACTIVE
    assert loaded.principal_amount.amount == Decimal("60000.00")
    assert len(loaded.schedule) == 12

    # Query with filters
    loans, count = loan_repo.list_loans(account_number="111122223333", status="ACTIVE")
    assert count == 1
    assert len(loans) == 1
    assert loans[0].loan_id == "LN-ACME-001"

    # Query non-matching filter
    empty_loans, empty_count = loan_repo.list_loans(status="PAID_OFF")
    assert empty_count == 0
    assert len(empty_loans) == 0
