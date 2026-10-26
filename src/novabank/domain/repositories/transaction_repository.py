"""Transaction repository interface defining ledger persistence contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Union

from novabank.domain.entities.transaction import Transaction
from novabank.domain.value_objects.account_number import AccountNumber


class TransactionRepositoryInterface(ABC):
    """Abstract port for appending and querying immutable ledger transactions."""

    @abstractmethod
    def append(self, transaction: Transaction) -> None:
        """Append an immutable transaction to the ledger.

        Raises DuplicateTransactionRefError if transaction_ref already exists.
        """
        pass

    @abstractmethod
    def get_by_ref(self, transaction_ref: str) -> Optional[Transaction]:
        """Fetch a transaction by its unique reference UUID string."""
        pass

    @abstractmethod
    def list_by_account(
        self,
        account_number: Union[AccountNumber, str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 50,
        offset: int = 0,
        descending: bool = True,
    ) -> list[Transaction]:
        """Fetch paginated transactions for an account, optionally filtered by date range."""
        pass

    @abstractmethod
    def count_by_account(
        self,
        account_number: Union[AccountNumber, str],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """Count total transactions for an account, optionally filtered by date range."""
        pass
