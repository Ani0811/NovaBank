"""Application and domain lifecycle events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


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
