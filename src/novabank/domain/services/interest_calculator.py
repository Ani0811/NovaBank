"""Domain service for financial interest accrual and APY calculations."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from novabank.domain.exceptions import DomainError
from novabank.domain.value_objects.money import Money


class InterestCalculator:
    """Domain service providing mathematically precise APY interest calculation."""

    @classmethod
    def calculate_monthly_interest(
        cls,
        balance: Money,
        annual_rate_percentage: Decimal,
        min_qualifying_balance: Optional[Money] = None,
    ) -> Money:
        """Calculate one month of accrued interest based on annual APY percentage.

        Formula:
            Monthly Rate = (Annual Rate / 100) / 12
            Accrued = Round(Balance * Monthly Rate, 2 decimals, ROUND_HALF_UP)

        Args:
            balance: Current cleared account balance.
            annual_rate_percentage: APY percentage e.g. Decimal("2.50") for 2.50%.
            min_qualifying_balance: Minimum balance required to earn interest.

        Returns:
            Money object representing calculated interest, or zero if non-qualifying.
        """
        if annual_rate_percentage < Decimal("0.00"):
            raise DomainError(f"Annual interest rate cannot be negative: {annual_rate_percentage}")

        if not balance.is_positive():
            return Money.zero(balance.currency)

        if min_qualifying_balance is not None and balance < min_qualifying_balance:
            return Money.zero(balance.currency)

        monthly_rate = (annual_rate_percentage / Decimal("100")) / Decimal("12")
        accrued_amount = (balance.amount * monthly_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if accrued_amount <= Decimal("0.00"):
            return Money.zero(balance.currency)

        return Money(accrued_amount, balance.currency)

    @classmethod
    def calculate_daily_interest(
        cls,
        balance: Money,
        annual_rate_percentage: Decimal,
        days_in_year: int = 365,
    ) -> Money:
        """Calculate daily accrued interest based on 365 or 366-day convention."""
        if annual_rate_percentage < Decimal("0.00"):
            raise DomainError(f"Annual interest rate cannot be negative: {annual_rate_percentage}")

        if not balance.is_positive():
            return Money.zero(balance.currency)

        daily_rate = (annual_rate_percentage / Decimal("100")) / Decimal(str(days_in_year))
        accrued_amount = (balance.amount * daily_rate).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        if accrued_amount <= Decimal("0.00"):
            return Money.zero(balance.currency)

        return Money(accrued_amount, balance.currency)

