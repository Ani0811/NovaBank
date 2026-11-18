"""Mathematically precise loan amortization calculator and schedule generator."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from novabank.domain.entities.loan import AmortizationScheduleEntry
from novabank.domain.exceptions import InvalidLoanTermsError
from novabank.domain.value_objects.money import Money


class AmortizationCalculator:
    """Institutional financial calculator for Equal Monthly Installments (EMI) and schedule generation."""

    @staticmethod
    def calculate_monthly_installment(
        principal: Money,
        apr_percentage: Decimal,
        term_months: int,
    ) -> Money:
        """Calculate the fixed monthly installment (EMI) using the annuity formula."""
        if not principal.is_positive():
            raise InvalidLoanTermsError("Principal amount must be positive.")
        if term_months <= 0 or term_months > 360:
            raise InvalidLoanTermsError(f"Loan term must be between 1 and 360 months, got {term_months}.")
        if apr_percentage < Decimal("0.00") or apr_percentage > Decimal("100.00"):
            raise InvalidLoanTermsError(f"APR rate must be between 0.00% and 100.00%, got {apr_percentage}%.")

        p = principal.amount
        n = Decimal(term_months)

        if apr_percentage == Decimal("0.00"):
            emi = (p / n).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return Money(emi)

        # Monthly interest rate r = (APR / 100) / 12
        r = (apr_percentage / Decimal("100.00")) / Decimal("12.00")

        # EMI = P * [r * (1 + r)^n] / [(1 + r)^n - 1]
        factor = (Decimal("1.00") + r) ** int(term_months)
        numerator = p * r * factor
        denominator = factor - Decimal("1.00")

        emi = (numerator / denominator).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return Money(emi)

    @staticmethod
    def generate_amortization_schedule(
        principal: Money,
        apr_percentage: Decimal,
        term_months: int,
        start_date: Optional[date] = None,
    ) -> list[AmortizationScheduleEntry]:
        """Generate a complete month-by-month schedule ensuring zero penny drift on principal payoff."""
        installment_emi = AmortizationCalculator.calculate_monthly_installment(
            principal=principal,
            apr_percentage=apr_percentage,
            term_months=term_months,
        )

        base_date = start_date or date.today()
        r = (apr_percentage / Decimal("100.00")) / Decimal("12.00") if apr_percentage > Decimal("0.00") else Decimal("0.00")

        entries: list[AmortizationScheduleEntry] = []
        remaining_balance = principal.amount

        for month in range(1, term_months + 1):
            # Compute due date: roughly 30 days or next month offset
            due_date = AmortizationCalculator._add_months(base_date, month)

            # Interest for the month
            monthly_interest = (remaining_balance * r).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            if month == term_months:
                # Final month adjustment: principal portion pays off exact remaining balance
                principal_portion = remaining_balance
                total_payment = principal_portion + monthly_interest
                remaining_balance = Decimal("0.00")
            else:
                principal_portion = installment_emi.amount - monthly_interest
                if principal_portion > remaining_balance:
                    principal_portion = remaining_balance
                remaining_balance -= principal_portion

            entries.append(
                AmortizationScheduleEntry(
                    installment_number=month,
                    due_date=due_date,
                    payment_amount=Money(total_payment if month == term_months else installment_emi.amount),
                    principal_amount=Money(principal_portion),
                    interest_amount=Money(monthly_interest),
                    remaining_balance=Money(remaining_balance),
                    is_paid=False,
                    paid_date=None,
                )
            )

        return entries

    @staticmethod
    def _add_months(source_date: date, months_to_add: int) -> date:
        """Helper to advance calendar months while preserving end of month bounds."""
        month = source_date.month - 1 + months_to_add
        year = source_date.year + month // 12
        month = month % 12 + 1
        day = min(source_date.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
        return date(year, month, day)
