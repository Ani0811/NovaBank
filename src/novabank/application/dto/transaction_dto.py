"""Data Transfer Objects (DTOs) for transactions and banking operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from novabank.domain.entities.transaction import Transaction


@dataclass(frozen=True)
class TransactionDTO:
    """Immutable data transfer object representing a completed transaction."""

    transaction_ref: str
    account_number: str
    transaction_type: str
    direction: str
    amount: Decimal
    balance_after: Decimal
    currency: str
    description: str
    created_at: datetime
    created_by: str
    formatted_amount: str
    formatted_balance_after: str
    transaction_id: Optional[int] = None

    @classmethod
    def from_entity(cls, tx: Transaction) -> TransactionDTO:
        """Construct DTO from domain Transaction entity."""
        return cls(
            transaction_ref=tx.transaction_ref,
            account_number=tx.account_number.value,
            transaction_type=tx.transaction_type.value,
            direction=tx.direction.value,
            amount=tx.amount.amount,
            balance_after=tx.balance_after.amount,
            currency=tx.amount.currency,
            description=tx.description,
            created_at=tx.created_at,
            created_by=tx.created_by,
            formatted_amount=tx.amount.formatted(),
            formatted_balance_after=tx.balance_after.formatted(),
            transaction_id=tx.transaction_id,
        )


@dataclass(frozen=True)
class DepositRequestDTO:
    """Input parameters for initiating a cash deposit workflow."""

    account_number: str
    amount: Decimal
    description: str = "Cash Deposit"
    reference: Optional[str] = None
    actor: str = "system"


@dataclass(frozen=True)
class WithdrawalRequestDTO:
    """Input parameters for initiating a cash withdrawal workflow."""

    account_number: str
    amount: Decimal
    description: str = "Cash Withdrawal"
    reference: Optional[str] = None
    actor: str = "system"


@dataclass(frozen=True)
class TransferRequestDTO:
    """Input parameters for initiating an account-to-account transfer workflow."""

    source_account: str
    destination_account: str
    amount: Decimal
    description: str = "Account Transfer"
    correlation_id: Optional[str] = None
    actor: str = "system"


@dataclass(frozen=True)
class TransferResultDTO:
    """Result returned after a successful account-to-account transfer."""

    correlation_id: str
    source_transaction: TransactionDTO
    destination_transaction: TransactionDTO
    amount: Decimal
    currency: str
    timestamp: datetime
