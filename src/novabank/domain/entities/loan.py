"""Commercial Loan domain entity, status enums, and amortization schedule value objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from novabank.domain.exceptions import (
    InvalidLoanTermsError,
    LoanAlreadyPaidOffError,
    LoanDisbursementError,
    LoanError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money


class LoanStatus(str, Enum):
    """Lifecycle status states for institutional credit facilities."""

    SUBMITTED = "SUBMITTED"
    ACTIVE = "ACTIVE"
    DELINQUENT = "DELINQUENT"
    PAID_OFF = "PAID_OFF"
    DEFAULTED = "DEFAULTED"


class LoanType(str, Enum):
    """Categorization for commercial and institutional credit products."""

    COMMERCIAL_EQUIPMENT = "COMMERCIAL_EQUIPMENT"
    WORKING_CAPITAL = "WORKING_CAPITAL"
    COMMERCIAL_MORTGAGE = "COMMERCIAL_MORTGAGE"
    TERM_LOAN = "TERM_LOAN"


@dataclass(frozen=True)
class AmortizationScheduleEntry:
    """Immutable single monthly installment milestone in the amortization schedule."""

    installment_number: int
    due_date: date
    payment_amount: Money
    principal_amount: Money
    interest_amount: Money
    remaining_balance: Money
    is_paid: bool = False
    paid_date: Optional[date] = None

    def mark_paid(self, payment_date: date) -> AmortizationScheduleEntry:
        """Return a copy marked as settled on the specified payment date."""
        return AmortizationScheduleEntry(
            installment_number=self.installment_number,
            due_date=self.due_date,
            payment_amount=self.payment_amount,
            principal_amount=self.principal_amount,
            interest_amount=self.interest_amount,
            remaining_balance=self.remaining_balance,
            is_paid=True,
            paid_date=payment_date,
        )


@dataclass
class LoanContract:
    """Core domain aggregate representing an active or disbursed commercial credit facility."""

    loan_id: str
    account_number: AccountNumber
    loan_type: LoanType
    principal_amount: Money
    interest_rate_apr: Decimal
    term_months: int
    monthly_installment: Money
    outstanding_balance: Money
    total_interest: Money
    status: LoanStatus = LoanStatus.SUBMITTED
    originated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    next_due_date: Optional[date] = None
    schedule: list[AmortizationScheduleEntry] = field(default_factory=list)
    purpose: str = "Commercial Financing"

    def __post_init__(self) -> None:
        if not self.principal_amount.is_positive():
            raise InvalidLoanTermsError("Principal amount must be positive.")
        if self.term_months <= 0 or self.term_months > 360:
            raise InvalidLoanTermsError(f"Loan term must be between 1 and 360 months, got {self.term_months}.")
        if self.interest_rate_apr <= Decimal("0.00") or self.interest_rate_apr > Decimal("100.00"):
            raise InvalidLoanTermsError(f"APR rate must be between 0.01% and 100.00%, got {self.interest_rate_apr}%.")

        if self.next_due_date is None and self.schedule:
            # First unpaid installment due date
            for item in self.schedule:
                if not item.is_paid:
                    self.next_due_date = item.due_date
                    break

    def disburse(self, actor: str = "system") -> None:
        """Activate the loan facility and verify schedule readiness."""
        if self.status != LoanStatus.SUBMITTED:
            raise LoanDisbursementError(f"Cannot disburse loan in status: {self.status.value}")
        if not self.schedule:
            raise LoanDisbursementError("Cannot disburse loan without a generated amortization schedule.")

        self.status = LoanStatus.ACTIVE
        self.outstanding_balance = self.principal_amount
        # Next due date defaults to first schedule installment
        self.next_due_date = self.schedule[0].due_date

    def process_repayment(
        self,
        amount: Optional[Money] = None,
        paid_date: Optional[date] = None,
        actor: str = "system",
    ) -> tuple[Money, Money]:
        """Apply an installment repayment, decrementing principal and interest atomically."""
        if self.status == LoanStatus.PAID_OFF:
            raise LoanAlreadyPaidOffError(f"Loan '{self.loan_id}' is already paid off in full.")
        if self.status not in (LoanStatus.ACTIVE, LoanStatus.DELINQUENT):
            raise LoanError(f"Cannot process repayment for loan in status: {self.status.value}")

        effective_date = paid_date or date.today()

        # Locate first unpaid installment
        target_idx: Optional[int] = None
        for idx, entry in enumerate(self.schedule):
            if not entry.is_paid:
                target_idx = idx
                break

        if target_idx is None:
            self.status = LoanStatus.PAID_OFF
            self.outstanding_balance = Money.zero()
            self.next_due_date = None
            return Money.zero(), Money.zero()

        entry = self.schedule[target_idx]
        principal_portion = entry.principal_amount
        interest_portion = entry.interest_amount

        # Mark installment as paid
        self.schedule[target_idx] = entry.mark_paid(effective_date)

        # Decrement outstanding balance by principal paid
        new_balance = self.outstanding_balance - principal_portion
        if new_balance.amount < Decimal("0.00"):
            new_balance = Money.zero()
        self.outstanding_balance = new_balance

        # Find next unpaid due date
        next_due: Optional[date] = None
        all_paid = True
        for item in self.schedule:
            if not item.is_paid:
                all_paid = False
                if next_due is None:
                    next_due = item.due_date

        self.next_due_date = next_due
        if all_paid or self.outstanding_balance.is_zero():
            self.status = LoanStatus.PAID_OFF
            self.outstanding_balance = Money.zero()
            self.next_due_date = None
        else:
            self.status = LoanStatus.ACTIVE

        return principal_portion, interest_portion

    def mark_delinquent(self) -> None:
        """Mark loan as delinquent if an installment is overdue past grace period."""
        if self.status == LoanStatus.ACTIVE:
            self.status = LoanStatus.DELINQUENT
