"""Data Transfer Objects for Payees and Beneficiaries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from novabank.domain.entities.beneficiary import Beneficiary


@dataclass(frozen=True)
class BeneficiaryDTO:
    """Read-only transfer contact representation for UI views."""

    beneficiary_id: Optional[int]
    source_account_number: str
    destination_account_number: str
    destination_holder_name: str
    nickname: str
    bank_name: str
    created_at: datetime

    @classmethod
    def from_entity(cls, entity: Beneficiary) -> BeneficiaryDTO:
        return cls(
            beneficiary_id=entity.beneficiary_id,
            source_account_number=entity.source_account_number.value,
            destination_account_number=entity.destination_account_number.value,
            destination_holder_name=entity.destination_holder_name,
            nickname=entity.nickname,
            bank_name=entity.bank_name,
            created_at=entity.created_at,
        )

