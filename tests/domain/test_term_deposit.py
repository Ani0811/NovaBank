"""Unit tests for Term Deposit & Certificate of Deposit (CD) domain entity and calculator."""

from datetime import date, timedelta
from decimal import Decimal
import pytest

from novabank.domain.entities.term_deposit import (
    CDAccrualMilestone,
    CertificateOfDeposit,
    TermDepositPayoutFrequency,
    TermDepositRolloverOption,
    TermDepositStatus,
)
from novabank.domain.exceptions import (
    InvalidTermDepositTermsError,
    TermDepositAlreadyClosedError,
)
from novabank.domain.services.term_deposit_calculator import TermDepositCalculator
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money


def test_term_deposit_calculator_one_year_compounding() -> None:
    """Test 12-month standard APY compound interest."""
    principal = Money(Decimal("10000.00"))
    apy = Decimal("5.00")
    tenor = 12

    interest = TermDepositCalculator.calculate_projected_interest(principal, apy, tenor)
    # At 5.00% APY for exactly 1 year, interest earned is $500.00
    assert interest.amount == Decimal("500.00")


def test_term_deposit_calculator_multi_year_compounding() -> None:
    """Test multi-year compounding growth: $10,000 at 5% APY for 2 years."""
    principal = Money(Decimal("10000.00"))
    apy = Decimal("5.00")
    tenor = 24

    interest = TermDepositCalculator.calculate_projected_interest(principal, apy, tenor)
    # $10,000 * (1.05)^2 = $11,025.00 => Interest = $1,025.00
    assert interest.amount == Decimal("1025.00")


def test_term_deposit_calculator_penalty_calculation() -> None:
    """Test early withdrawal penalty calculation (3 months of simple interest)."""
    principal = Money(Decimal("10000.00"))
    apy = Decimal("6.00")
    penalty_months = 3

    penalty = TermDepositCalculator.calculate_early_withdrawal_penalty(principal, apy, penalty_months)
    # 10,000 * 0.06 * (3/12) = $150.00
    assert penalty.amount == Decimal("150.00")


def test_term_deposit_invalid_terms() -> None:
    """Ensure invalid terms throw InvalidTermDepositTermsError."""
    # Principal below minimum $500
    with pytest.raises(InvalidTermDepositTermsError):
        CertificateOfDeposit(
            cd_id="CD-TEST-001",
            account_number=AccountNumber("111122223333"),
            principal_amount=Money(Decimal("300.00")),
            interest_rate_apy=Decimal("5.00"),
            tenor_months=12,
            issue_date=date(2026, 1, 1),
            maturity_date=date(2027, 1, 1),
        )

    # Invalid Tenor
    with pytest.raises(InvalidTermDepositTermsError):
        CertificateOfDeposit(
            cd_id="CD-TEST-001",
            account_number=AccountNumber("111122223333"),
            principal_amount=Money(Decimal("1000.00")),
            interest_rate_apy=Decimal("5.00"),
            tenor_months=0,
            issue_date=date(2026, 1, 1),
            maturity_date=date(2027, 1, 1),
        )

    # Invalid APY
    with pytest.raises(InvalidTermDepositTermsError):
        CertificateOfDeposit(
            cd_id="CD-TEST-001",
            account_number=AccountNumber("111122223333"),
            principal_amount=Money(Decimal("1000.00")),
            interest_rate_apy=Decimal("0.00"),
            tenor_months=12,
            issue_date=date(2026, 1, 1),
            maturity_date=date(2027, 1, 1),
        )


def test_certificate_of_deposit_maturity_workflow() -> None:
    """Test standard maturity lifecycle: ACTIVE -> MATURED with full principal and interest."""
    principal = Money(Decimal("20000.00"))
    apy = Decimal("5.00")
    tenor = 12
    issue_d = date(2026, 1, 1)
    mat_d = date(2027, 1, 1)

    cd = CertificateOfDeposit(
        cd_id="CD-MATURE-01",
        account_number=AccountNumber("111122223333"),
        principal_amount=principal,
        interest_rate_apy=apy,
        tenor_months=tenor,
        issue_date=issue_d,
        maturity_date=mat_d,
    )

    assert cd.status == TermDepositStatus.ACTIVE
    assert cd.projected_interest_at_maturity.amount == Decimal("1000.00")
    assert len(cd.accruals) == 12

    # Mature CD
    total_payout = cd.mature(as_of_date=mat_d)
    assert cd.status == TermDepositStatus.MATURED
    assert total_payout.amount == Decimal("21000.00")
    assert cd.closed_at is not None

    # Subsequent maturity call raises TermDepositAlreadyClosedError
    with pytest.raises(TermDepositAlreadyClosedError):
        cd.mature()


def test_certificate_of_deposit_early_liquidation() -> None:
    """Test early liquidation with penalty forfeiture."""
    principal = Money(Decimal("50000.00"))
    apy = Decimal("6.00")
    tenor = 24
    issue_d = date(2026, 1, 1)
    mat_d = date(2028, 1, 1)

    cd = CertificateOfDeposit(
        cd_id="CD-EARLY-01",
        account_number=AccountNumber("111122223333"),
        principal_amount=principal,
        interest_rate_apy=apy,
        tenor_months=tenor,
        issue_date=issue_d,
        maturity_date=mat_d,
        early_withdrawal_penalty_months=6,  # 6 months penalty for 24m
    )

    # 1 year later (halfway through tenor)
    break_date = date(2027, 1, 1)
    p_out, net_int, penalty = cd.close_prematurely(as_of_date=break_date)

    assert cd.status == TermDepositStatus.PREMATURELY_CLOSED
    assert p_out.amount == Decimal("50000.00")
    # Penalty for 6 months at 6% on 50k = $1,500.00
    assert penalty.amount == Decimal("1500.00")
    assert cd.early_withdrawal_penalty is not None
    assert cd.early_withdrawal_penalty.amount == Decimal("1500.00")
