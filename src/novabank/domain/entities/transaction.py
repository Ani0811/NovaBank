"""Immutable Transaction ledger entry entity."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from novabank.domain.exceptions import DomainError
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType


class Transaction:
    """Immutable record of a financial transaction on an account ledger."""

    def __init__(
        self,
        account_number: AccountNumber,
        transaction_type: TransactionType,
        direction: TransactionDirection,
        amount: Money,
        balance_after: Money,
        description: str = "",
        transaction_ref: Optional[str] = None,
        created_at: Optional[datetime] = None,
        created_by: str = "system",
        transaction_id: Optional[int] = None,
    ) -> None:
        if not isinstance(account_number, AccountNumber):
            raise TypeError("account_number must be an AccountNumber instance")

        if not isinstance(transaction_type, TransactionType):
            raise TypeError("transaction_type must be a TransactionType enum")

        if not isinstance(direction, TransactionDirection):
            raise TypeError("direction must be a TransactionDirection enum")

        if not isinstance(amount, Money) or not amount.is_positive():
            raise DomainError(f"Transaction amount must be positive, got {amount}")

        if not isinstance(balance_after, Money):
            raise TypeError("balance_after must be a Money instance")

        if amount.currency != balance_after.currency:
            raise DomainError("Amount and balance_after currencies must match.")

        self._transaction_id = transaction_id
        self._transaction_ref = transaction_ref or str(uuid.uuid4())
        self._account_number = account_number
        self._transaction_type = transaction_type
        self._direction = direction
        self._amount = amount
        self._balance_after = balance_after
        self._description = description.strip()
        self._created_at = created_at or datetime.now(timezone.utc)
        self._created_by = created_by.strip() or "system"

    @property
    def transaction_id(self) -> Optional[int]:
        return self._transaction_id

    @property
    def transaction_ref(self) -> str:
        return self._transaction_ref

    @property
    def account_number(self) -> AccountNumber:
        return self._account_number

    @property
    def transaction_type(self) -> TransactionType:
        return self._transaction_type

    @property
    def direction(self) -> TransactionDirection:
        return self._direction

    @property
    def amount(self) -> Money:
        return self._amount

    @property
    def balance_after(self) -> Money:
        return self._balance_after

    @property
    def description(self) -> str:
        return self._description

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def created_by(self) -> str:
        return self._created_by

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Transaction):
            return False
        return self._transaction_ref == other._transaction_ref

    def __hash__(self) -> int:
        return hash(self._transaction_ref)

    def __repr__(self) -> str:
        return (
            f"Transaction(ref='{self._transaction_ref}', type={self._transaction_type.value}, "
            f"direction={self._direction.value}, amount={self._amount.formatted()}, "
            f"balance_after={self._balance_after.formatted()})"
        )
