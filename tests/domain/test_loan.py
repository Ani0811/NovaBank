"""Unit tests for Commercial Loan domain entity, value objects, and amortization calculator."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import pytest

from novabank.domain.entities.loan import (
    AmortizationScheduleEntry,
    LoanContract,
    LoanStatus,
    LoanType,
)
from novabank.domain.exceptions import (
    InvalidLoanTermsError,
    LoanAlreadyPaidOffError,
    LoanDisbursementError,
    LoanError,
)
from novabank.domain.services.amortization_calculator import AmortizationCalculator
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money


def test_amortization_calculator_monthly_installment_standard() -> None:
    """Test standard French annuity EMI calculation."""
    principal = Money(Decimal("100000.00"))
    apr = Decimal("7.50")
    term = 12

    emi = AmortizationCalculator.calculate_monthly_installment(principal, apr, term)
    # Expected EMI for 100k, 7.5%, 12m is approx $8,675.74
    assert emi.amount == Decimal("8675.74")


def test_amortization_calculator_zero_interest() -> None:
    """Test 0% interest rate simply divides principal by term."""
    principal = Money(Decimal("12000.00"))
    apr = Decimal("0.00")
    term = 12

    emi = AmortizationCalculator.calculate_monthly_installment(principal, apr, term)
    assert emi.amount == Decimal("1000.00")


def test_amortization_calculator_invalid_terms() -> None:
    """Ensure invalid terms throw InvalidLoanTermsError."""
    with pytest.raises(InvalidLoanTermsError):
        AmortizationCalculator.calculate_monthly_installment(Money(Decimal("0.00")), Decimal("5.0"), 12)

    with pytest.raises(InvalidLoanTermsError):
        AmortizationCalculator.calculate_monthly_installment(Money(Decimal("-100.00"), allow_negative=True), Decimal("5.0"), 12)

    with pytest.raises(InvalidLoanTermsError):
        AmortizationCalculator.calculate_monthly_installment(Money(Decimal("1000.00")), Decimal("5.0"), 0)

    with pytest.raises(InvalidLoanTermsError):
        AmortizationCalculator.calculate_monthly_installment(Money(Decimal("1000.00")), Decimal("5.0"), 400)

    with pytest.raises(InvalidLoanTermsError):
        AmortizationCalculator.calculate_monthly_installment(Money(Decimal("1000.00")), Decimal("-1.0"), 12)


def test_zero_penny_drift_reconciliation() -> None:
    """Critical financial invariant: sum of principal portions MUST equal original principal down to the exact cent."""
    principal = Money(Decimal("50000.00"))
    apr = Decimal("6.25")
    term = 36

    schedule = AmortizationCalculator.generate_amortization_schedule(principal, apr, term)
    assert len(schedule) == 36

    total_principal_portions = sum((item.principal_amount.amount for item in schedule), Decimal("0.00"))
    assert total_principal_portions == principal.amount

    # Final month remaining balance must be zero
    assert schedule[-1].remaining_balance.amount == Decimal("0.00")


def test_loan_contract_lifecycle_and_repayment() -> None:
    """Test full loan lifecycle: SUBMITTED -> ACTIVE -> installments -> PAID_OFF."""
    principal = Money(Decimal("10000.00"))
    apr = Decimal("6.00")
    term = 3

    schedule = AmortizationCalculator.generate_amortization_schedule(principal, apr, term)
    emi = AmortizationCalculator.calculate_monthly_installment(principal, apr, term)
    total_interest = Money(sum(item.interest_amount.amount for item in schedule))

    loan = LoanContract(
        loan_id="LN-TEST-001",
        account_number=AccountNumber("100000000001"),
        loan_type=LoanType.COMMERCIAL_EQUIPMENT,
        principal_amount=principal,
        interest_rate_apr=apr,
        term_months=term,
        monthly_installment=emi,
        outstanding_balance=principal,
        total_interest=total_interest,
        status=LoanStatus.SUBMITTED,
        schedule=schedule,
    )

    assert loan.status == LoanStatus.SUBMITTED
    loan.disburse(actor="officer")
    assert loan.status == LoanStatus.ACTIVE
    assert loan.next_due_date is not None

    # Process month 1 repayment
    p1, i1 = loan.process_repayment(paid_date=date(2026, 1, 15))
    assert loan.schedule[0].is_paid is True
    assert loan.schedule[0].paid_date == date(2026, 1, 15)
    assert loan.status == LoanStatus.ACTIVE

    # Process month 2 repayment
    loan.process_repayment(paid_date=date(2026, 2, 15))
    assert loan.schedule[1].is_paid is True
    assert loan.status == LoanStatus.ACTIVE

    # Process month 3 repayment (final)
    loan.process_repayment(paid_date=date(2026, 3, 15))
    assert loan.schedule[2].is_paid is True
    assert loan.status == LoanStatus.PAID_OFF
    assert loan.outstanding_balance.is_zero()
    assert loan.next_due_date is None

    # Subsequent repayment must raise LoanAlreadyPaidOffError
    with pytest.raises(LoanAlreadyPaidOffError):
        loan.process_repayment()
