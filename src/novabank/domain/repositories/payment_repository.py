"""Payment gateway repository interface defining persistence contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Union

from novabank.domain.entities.payment import PaymentTransaction
from novabank.domain.value_objects.account_number import AccountNumber


class PaymentRepositoryInterface(ABC):
    """Abstract port for Payment Gateway transaction persistence and auditing."""

    @abstractmethod
    def save(self, payment: PaymentTransaction) -> None:
        """Persist a new or updated payment transaction."""
        pass

    @abstractmethod
    def get_by_id(self, payment_id: str) -> Optional[PaymentTransaction]:
        """Fetch payment by unique gateway payment_id."""
        pass

    @abstractmethod
    def get_by_idempotency_key(self, key: str) -> Optional[PaymentTransaction]:
        """Fetch payment by unique idempotency key."""
        pass

    @abstractmethod
    def list_payments(
        self,
        account_number: Optional[Union[AccountNumber, str]] = None,
        channel: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[PaymentTransaction], int]:
        """Retrieve paginated payments matching optional filter criteria."""
        pass

