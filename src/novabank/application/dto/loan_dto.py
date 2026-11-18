"""Data Transfer Objects for Commercial Loan Origination, Amortization, and Portfolio Servicing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from novabank.domain.entities.loan import AmortizationScheduleEntry, LoanContract


@dataclass(frozen=True)
class LoanQuoteRequestDTO:
    """Inbound request to simulate Equal Monthly Installments."""

    principal: Decimal
    apr_percentage: Decimal
    term_months: int


@dataclass(frozen=True)
class LoanQuoteResponseDTO:
    """Outbound simulation quote with breakdown."""

    principal: Decimal
    apr_percentage: Decimal
    term_months: int
    monthly_installment: Decimal
    total_interest: Decimal
    total_payable: Decimal

    @property
    def formatted_principal(self) -> str:
        return f"${self.principal:,.2f}"

    @property
    def formatted_monthly_installment(self) -> str:
        return f"${self.monthly_installment:,.2f}"

    @property
    def formatted_total_interest(self) -> str:
        return f"${self.total_interest:,.2f}"

    @property
    def formatted_total_payable(self) -> str:
        return f"${self.total_payable:,.2f}"


@dataclass(frozen=True)
class LoanOriginationRequestDTO:
    """Inbound request payload to disburse and underwrite a new commercial loan facility."""

    account_number: str
    loan_type: str
    principal: Decimal
    apr_percentage: Decimal
    term_months: int
    purpose: str = "Commercial Financing"


@dataclass(frozen=True)
class AmortizationScheduleEntryDTO:
    """Read-only view representation of a single monthly installment milestone."""

    installment_number: int
    due_date: str
    payment_amount: Decimal
    principal_amount: Decimal
    interest_amount: Decimal
    remaining_balance: Decimal
    is_paid: bool
    paid_date: Optional[str]

    @property
    def formatted_payment(self) -> str:
        return f"${self.payment_amount:,.2f}"

    @property
    def formatted_principal(self) -> str:
        return f"${self.principal_amount:,.2f}"

    @property
    def formatted_interest(self) -> str:
        return f"${self.interest_amount:,.2f}"

    @property
    def formatted_remaining_balance(self) -> str:
        return f"${self.remaining_balance:,.2f}"

    @classmethod
    def from_entity(cls, entity: AmortizationScheduleEntry) -> AmortizationScheduleEntryDTO:
        return cls(
            installment_number=entity.installment_number,
            due_date=entity.due_date.isoformat(),
            payment_amount=entity.payment_amount.amount,
            principal_amount=entity.principal_amount.amount,
            interest_amount=entity.interest_amount.amount,
            remaining_balance=entity.remaining_balance.amount,
            is_paid=entity.is_paid,
            paid_date=entity.paid_date.isoformat() if entity.paid_date else None,
        )


@dataclass(frozen=True)
class LoanContractDTO:
    """Read-only view representation of a commercial loan contract and its lifecycle state."""

    loan_id: str
    account_number: str
    loan_type: str
    principal_amount: Decimal
    interest_rate_apr: Decimal
    term_months: int
    monthly_installment: Decimal
    outstanding_balance: Decimal
    total_interest: Decimal
    status: str
    purpose: str
    originated_at: datetime
    next_due_date: Optional[str]
    schedule: list[AmortizationScheduleEntryDTO]

    @property
    def formatted_principal(self) -> str:
        return f"${self.principal_amount:,.2f}"

    @property
    def formatted_monthly_installment(self) -> str:
        return f"${self.monthly_installment:,.2f}"

    @property
    def formatted_outstanding_balance(self) -> str:
        return f"${self.outstanding_balance:,.2f}"

    @property
    def formatted_total_interest(self) -> str:
        return f"${self.total_interest:,.2f}"

    @property
    def paid_installments_count(self) -> int:
        return sum(1 for entry in self.schedule if entry.is_paid)

    @property
    def progress_percentage(self) -> float:
        if self.principal_amount <= Decimal("0.00"):
            return 100.0
        repaid = self.principal_amount - self.outstanding_balance
        pct = (repaid / self.principal_amount) * Decimal("100.00")
        return float(min(Decimal("100.00"), max(Decimal("0.00"), pct)))

    @classmethod
    def from_entity(cls, entity: LoanContract) -> LoanContractDTO:
        return cls(
            loan_id=entity.loan_id,
            account_number=entity.account_number.value,
            loan_type=entity.loan_type.value,
            principal_amount=entity.principal_amount.amount,
            interest_rate_apr=entity.interest_rate_apr,
            term_months=entity.term_months,
            monthly_installment=entity.monthly_installment.amount,
            outstanding_balance=entity.outstanding_balance.amount,
            total_interest=entity.total_interest.amount,
            status=entity.status.value,
            purpose=entity.purpose,
            originated_at=entity.originated_at,
            next_due_date=entity.next_due_date.isoformat() if entity.next_due_date else None,
            schedule=[AmortizationScheduleEntryDTO.from_entity(s) for s in entity.schedule],
        )


@dataclass(frozen=True)
class LoanRepaymentResultDTO:
    """Result payload after successfully executing an installment repayment."""

    loan_id: str
    account_number: str
    installment_number: int
    repayment_amount: Decimal
    principal_portion: Decimal
    interest_portion: Decimal
    remaining_balance: Decimal
    new_status: str
    next_due_date: Optional[str]
    timestamp: datetime
