"""Domain tests for InterestCalculator service."""

from decimal import Decimal
import pytest

from novabank.domain.exceptions import DomainError
from novabank.domain.services.interest_calculator import InterestCalculator
from novabank.domain.value_objects.money import Money


def test_calculate_monthly_interest_standard_rate():
    # $10,000 at 2.50% APY
    # Monthly: 10,000 * 0.025 / 12 = 20.8333... -> $20.83
    balance = Money("10000.00")
    rate = Decimal("2.50")
    interest = InterestCalculator.calculate_monthly_interest(balance, rate)
    assert interest.amount == Decimal("20.83")
    assert interest.currency == "USD"


def test_calculate_monthly_interest_zero_or_negative_balance():
    rate = Decimal("2.50")
    zero_bal = Money("0.00")
    assert InterestCalculator.calculate_monthly_interest(zero_bal, rate).amount == Decimal("0.00")

    neg_bal = Money("-500.00", allow_negative=True)
    assert InterestCalculator.calculate_monthly_interest(neg_bal, rate).amount == Decimal("0.00")


def test_calculate_monthly_interest_below_qualifying_threshold():
    balance = Money("50.00")
    min_bal = Money("100.00")
    rate = Decimal("3.00")
    interest = InterestCalculator.calculate_monthly_interest(
        balance, rate, min_qualifying_balance=min_bal
    )
    assert interest.amount == Decimal("0.00")


def test_calculate_monthly_interest_negative_rate_rejected():
    balance = Money("1000.00")
    with pytest.raises(DomainError, match="cannot be negative"):
        InterestCalculator.calculate_monthly_interest(balance, Decimal("-1.00"))


def test_calculate_daily_interest():
    # $10,000 at 3.65% APY over 365 days -> 10,000 * 0.0365 / 365 = $1.00 per day
    balance = Money("10000.00")
    rate = Decimal("3.65")
    interest = InterestCalculator.calculate_daily_interest(balance, rate, days_in_year=365)
    assert interest.amount == Decimal("1.00")

