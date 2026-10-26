"""Account repository interface defining persistence contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Union

from novabank.domain.entities.account import Account
from novabank.domain.value_objects.account_number import AccountNumber


class AccountRepositoryInterface(ABC):
    """Abstract port for customer account persistence and retrieval."""

    @abstractmethod
    def save(self, account: Account) -> None:
        """Persist a new or modified Account domain entity."""
        pass

    @abstractmethod
    def get_by_number(self, account_number: Union[AccountNumber, str]) -> Optional[Account]:
        """Fetch account entity by account number."""
        pass

    @abstractmethod
    def get_by_number_for_update(
        self, account_number: Union[AccountNumber, str]
    ) -> Optional[Account]:
        """Fetch account entity and acquire a pessimistic row-level lock (SELECT ... FOR UPDATE)."""
        pass

    @abstractmethod
    def list_accounts(
        self,
        search: Optional[str] = None,
        active_only: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Account]:
        """Retrieve paginated accounts matching optional search criteria."""
        pass

    @abstractmethod
    def count_accounts(
        self,
        search: Optional[str] = None,
        active_only: bool = False,
    ) -> int:
        """Count total accounts matching optional search criteria."""
        pass

    @abstractmethod
    def exists(self, account_number: Union[AccountNumber, str]) -> bool:
        """Check whether an account with the given account number exists."""
        pass
