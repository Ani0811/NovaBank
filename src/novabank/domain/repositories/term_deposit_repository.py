"""Term Deposit & Certificate of Deposit repository interface defining persistence contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Union

from novabank.domain.entities.term_deposit import CertificateOfDeposit
from novabank.domain.value_objects.account_number import AccountNumber


class TermDepositRepositoryInterface(ABC):
    """Abstract port for Certificate of Deposit persistence and vault lifecycle management."""

    @abstractmethod
    def save(self, cd: CertificateOfDeposit) -> None:
        """Persist a new or updated Certificate of Deposit record."""
        pass

    @abstractmethod
    def get_by_id(self, cd_id: str) -> Optional[CertificateOfDeposit]:
        """Fetch Certificate of Deposit by unique identifier."""
        pass

    @abstractmethod
    def list_term_deposits(
        self,
        account_number: Optional[Union[AccountNumber, str]] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CertificateOfDeposit], int]:
        """Retrieve paginated Certificate of Deposit records matching optional filter criteria."""
        pass
