"""Commercial Loan repository interface defining persistence contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Union

from novabank.domain.entities.loan import LoanContract
from novabank.domain.value_objects.account_number import AccountNumber


class LoanRepositoryInterface(ABC):
    """Abstract port for Commercial Loan persistence and portfolio management."""

    @abstractmethod
    def save(self, loan: LoanContract) -> None:
        """Persist a new or updated loan facility."""
        pass

    @abstractmethod
    def get_by_id(self, loan_id: str) -> Optional[LoanContract]:
        """Fetch loan contract by unique facility identifier."""
        pass

    @abstractmethod
    def list_loans(
        self,
        account_number: Optional[Union[AccountNumber, str]] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[LoanContract], int]:
        """Retrieve paginated loan facilities matching optional filter criteria."""
        pass
