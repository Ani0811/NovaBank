"""Mathematically precise compound interest engine and schedule generator for Term Deposits & CDs."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from novabank.domain.exceptions import InvalidTermDepositTermsError
from novabank.domain.value_objects.money import Money


class TermDepositCalculator:
    """Institutional financial calculator for Certificate of Deposit yields, accruals, and penalties."""

    @staticmethod
    def add_months(source_date: date, months: int) -> date:
        """Advance calendar date by exact months handling variable month lengths."""
        total_months = source_date.month - 1 + months
        year = source_date.year + total_months // 12
        month = total_months % 12 + 1
        max_days = [
            31,
            29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ][month - 1]
        day = min(source_date.day, max_days)
        return date(year, month, day)

    @staticmethod
    def calculate_projected_interest(
        principal: Money,
        apy_percentage: Decimal,
        tenor_months: int,
    ) -> Money:
        """Calculate guaranteed total interest earned at maturity using compound APY formula."""
        if not principal.is_positive():
            raise InvalidTermDepositTermsError("Principal amount must be positive.")
        if tenor_months <= 0 or tenor_months > 120:
            raise InvalidTermDepositTermsError(f"Tenor must be between 1 and 120 months, got {tenor_months}.")
        if apy_percentage <= Decimal("0.00") or apy_percentage > Decimal("30.00"):
            raise InvalidTermDepositTermsError(f"APY must be between 0.01% and 30.00%, got {apy_percentage}%.")

        p = principal.amount
        years = Decimal(tenor_months) / Decimal("12.00")
        rate_factor = Decimal("1.00") + (apy_percentage / Decimal("100.00"))

        # Compound growth: A = P * (1 + APY)^years
        # For fractional powers, float conversion with exact Decimal quantization
        factor_float = float(rate_factor) ** float(years)
        matured_amount = (p * Decimal(str(factor_float))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        interest = matured_amount - p
        if interest < Decimal("0.00"):
            interest = Decimal("0.00")
        return Money(interest)

    @staticmethod
    def calculate_accrued_interest(
        principal: Money,
        apy_percentage: Decimal,
        issue_date: date,
        as_of_date: date,
        maturity_date: date,
    ) -> Money:
        """Calculate interest accrued up to as_of_date (capped at maturity date)."""
        if as_of_date <= issue_date:
            return Money.zero()

        effective_date = min(as_of_date, maturity_date)
        total_days = (maturity_date - issue_date).days
        elapsed_days = (effective_date - issue_date).days

        if total_days <= 0 or elapsed_days <= 0:
            return Money.zero()

        # Compute annualized fraction of year
        years = Decimal(elapsed_days) / Decimal("365.25")
        rate_factor = Decimal("1.00") + (apy_percentage / Decimal("100.00"))
        factor_float = float(rate_factor) ** float(years)
        current_amount = (principal.amount * Decimal(str(factor_float))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        accrued = current_amount - principal.amount
        return Money(max(Decimal("0.00"), accrued))

    @staticmethod
    def calculate_early_withdrawal_penalty(
        principal: Money,
        apy_percentage: Decimal,
        penalty_months: int = 3,
    ) -> Money:
        """Calculate penalty fee for breaking CD before scheduled maturity date."""
        if penalty_months <= 0:
            return Money.zero()

        # Penalty = Principal * APY * (penalty_months / 12)
        annual_rate = apy_percentage / Decimal("100.00")
        time_fraction = Decimal(penalty_months) / Decimal("12.00")
        penalty = (principal.amount * annual_rate * time_fraction).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        return Money(max(Decimal("0.00"), penalty))
