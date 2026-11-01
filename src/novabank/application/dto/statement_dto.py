"""Data Transfer Objects for Account Statement generation and reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, Union

from novabank.domain.entities.transaction import Transaction
from novabank.domain.value_objects.transaction_type import TransactionDirection


@dataclass(frozen=True)
class StatementRequestDTO:
    """Parameters for requesting an account statement."""

    account_number: str
    start_date: Optional[Union[date, datetime]] = None
    end_date: Optional[Union[date, datetime]] = None


@dataclass(frozen=True)
class StatementEntryDTO:
    """Individual line item in an account statement ledger view."""

    transaction_id: Optional[int]
    transaction_ref: str
    created_at: datetime
    transaction_type: str
    direction: str
    description: str
    amount: Decimal
    debit_amount: Optional[Decimal]
    credit_amount: Optional[Decimal]
    balance_after: Decimal
    currency: str
    created_by: str
    formatted_amount: str
    formatted_balance_after: str
    formatted_debit: str
    formatted_credit: str

    @classmethod
    def from_entity(cls, tx: Transaction) -> StatementEntryDTO:
        is_debit = tx.direction == TransactionDirection.DEBIT
        is_credit = tx.direction == TransactionDirection.CREDIT

        amt_val = tx.amount.amount
        debit_val = amt_val if is_debit else None
        credit_val = amt_val if is_credit else None

        fmt_debit = f"-${amt_val:,.2f}" if is_debit else ""
        fmt_credit = f"+${amt_val:,.2f}" if is_credit else ""

        return cls(
            transaction_id=tx.transaction_id,
            transaction_ref=tx.transaction_ref,
            created_at=tx.created_at,
            transaction_type=tx.transaction_type.value,
            direction=tx.direction.value,
            description=tx.description,
            amount=amt_val,
            debit_amount=debit_val,
            credit_amount=credit_val,
            balance_after=tx.balance_after.amount,
            currency=tx.amount.currency,
            created_by=tx.created_by,
            formatted_amount=tx.amount.formatted(),
            formatted_balance_after=tx.balance_after.formatted(),
            formatted_debit=fmt_debit,
            formatted_credit=fmt_credit,
        )


@dataclass(frozen=True)
class AccountStatementDTO:
    """Comprehensive statement model capturing opening, periodic activity, and closing reconciliations."""

    account_number: str
    holder_name: str
    account_status: str  # "Active" or "Closed"
    currency: str
    start_date: Optional[datetime]
    end_date: datetime
    generated_at: datetime
    opening_balance: Decimal
    total_credits: Decimal
    total_debits: Decimal
    net_change: Decimal
    closing_balance: Decimal
    transaction_count: int
    entries: tuple[StatementEntryDTO, ...]

    @property
    def formatted_opening_balance(self) -> str:
        return f"${self.opening_balance:,.2f} {self.currency}"

    @property
    def formatted_total_credits(self) -> str:
        return f"${self.total_credits:,.2f} {self.currency}"

    @property
    def formatted_total_debits(self) -> str:
        return f"${self.total_debits:,.2f} {self.currency}"

    @property
    def formatted_net_change(self) -> str:
        prefix = "+" if self.net_change > Decimal("0.00") else ""
        return f"{prefix}${self.net_change:,.2f} {self.currency}"

    @property
    def formatted_closing_balance(self) -> str:
        return f"${self.closing_balance:,.2f} {self.currency}"

    def is_reconciled(self) -> bool:
        """Verify mathematical integrity invariant: Opening + Credits - Debits == Closing."""
        return (
            self.opening_balance + self.total_credits - self.total_debits
        ) == self.closing_balance
