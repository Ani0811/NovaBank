"""Beneficiary domain entity representing saved payees and transfer contacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from novabank.domain.exceptions import DomainError, SelfTransferError
from novabank.domain.value_objects.account_number import AccountNumber


class Beneficiary:
    """Domain entity representing a verified frequent payee or beneficiary contact."""

    def __init__(
        self,
        source_account_number: AccountNumber,
        destination_account_number: AccountNumber,
        destination_holder_name: str,
        nickname: str,
        bank_name: str = "NovaBank",
        beneficiary_id: Optional[int] = None,
        created_at: Optional[datetime] = None,
    ) -> None:
        if source_account_number == destination_account_number:
            raise SelfTransferError(source_account_number.value)

        self.source_account_number = source_account_number
        self.destination_account_number = destination_account_number
        self.destination_holder_name = self._validate_holder_name(destination_holder_name)
        self.nickname = self._validate_nickname(nickname)
        self.bank_name = bank_name.strip() or "NovaBank"
        self.beneficiary_id = beneficiary_id
        self.created_at = created_at or datetime.now(timezone.utc)

    @staticmethod
    def _validate_nickname(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise DomainError("Beneficiary nickname cannot be empty.")
        clean = name.strip()
        if len(clean) > 50:
            raise DomainError("Beneficiary nickname cannot exceed 50 characters.")
        return clean

    @staticmethod
    def _validate_holder_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise DomainError("Destination holder name cannot be empty.")
        clean = name.strip()
        if len(clean) > 100:
            raise DomainError("Destination holder name cannot exceed 100 characters.")
        return clean

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Beneficiary):
            return False
        return (
            self.source_account_number == other.source_account_number
            and self.destination_account_number == other.destination_account_number
        )

    def __hash__(self) -> int:
        return hash((self.source_account_number, self.destination_account_number))

    def __repr__(self) -> str:
        return (
            f"Beneficiary(id={self.beneficiary_id}, nick='{self.nickname}', "
            f"dest='{self.destination_account_number.value}', holder='{self.destination_holder_name}')"
        )

