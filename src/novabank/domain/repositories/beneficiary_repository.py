"""Beneficiary repository interface defining persistence contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Union

from novabank.domain.entities.beneficiary import Beneficiary
from novabank.domain.value_objects.account_number import AccountNumber


class BeneficiaryRepositoryInterface(ABC):
    """Abstract port for frequent payee / beneficiary persistence."""

    @abstractmethod
    def save(self, beneficiary: Beneficiary) -> None:
        """Persist a new or modified Beneficiary entity."""
        pass

    @abstractmethod
    def get_by_id(self, beneficiary_id: int) -> Optional[Beneficiary]:
        """Fetch beneficiary by primary key id."""
        pass

    @abstractmethod
    def get_by_source_and_dest(
        self,
        source_account_number: Union[AccountNumber, str],
        destination_account_number: Union[AccountNumber, str],
    ) -> Optional[Beneficiary]:
        """Fetch beneficiary record for a specific source and destination pair."""
        pass

    @abstractmethod
    def list_by_source(
        self, source_account_number: Union[AccountNumber, str]
    ) -> list[Beneficiary]:
        """List all saved payees for a given source account ordered by nickname."""
        pass

    @abstractmethod
    def delete(self, beneficiary_id: int) -> bool:
        """Remove a beneficiary record by id. Returns True if deleted, False if not found."""
        pass

