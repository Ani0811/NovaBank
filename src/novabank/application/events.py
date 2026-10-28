"""Application and domain lifecycle events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class AccountOpenedEvent:
    """Emitted upon successful creation and registration of a new customer account."""

    account_number: str
    holder_name: str
    phone_number: str
    initial_deposit: Decimal
    currency: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class DepositCompletedEvent:
    """Emitted upon successful commit of a cash deposit transaction."""

    account_number: str
    amount: Decimal
    balance_after: Decimal
    currency: str
    transaction_ref: str
    timestamp: datetime
    actor: str = "system"
    description: str = "Cash Deposit"


@dataclass(frozen=True)
class WithdrawalCompletedEvent:
    """Emitted upon successful commit of a cash withdrawal transaction."""

    account_number: str
    amount: Decimal
    balance_after: Decimal
    currency: str
    transaction_ref: str
    timestamp: datetime
    actor: str = "system"
    description: str = "Cash Withdrawal"


@dataclass(frozen=True)
class TransferCompletedEvent:
    """Emitted upon successful commit of an account-to-account fund transfer."""

    source_account: str
    destination_account: str
    amount: Decimal
    source_balance_after: Decimal
    destination_balance_after: Decimal
    currency: str
    correlation_id: str
    timestamp: datetime
    actor: str = "system"
    description: str = "Account Transfer"
