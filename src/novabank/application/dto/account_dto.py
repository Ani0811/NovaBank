"""Data Transfer Objects for Account operations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from novabank.application.dto.transaction_dto import TransactionDTO
from novabank.domain.entities.account import Account


@dataclass(frozen=True)
class OpenAccountRequestDTO:
    """Request DTO containing customer registration parameters."""

    holder_name: str
    dob: date
    address_line: str
    city: str
    state: str
    country: str
    phone_number: str
    initial_deposit: Optional[Decimal] = None
    currency: str = "USD"
    actor: str = "teller"


@dataclass(frozen=True)
class AccountDTO:
    """Read-only customer account representation for UI views."""

    account_number: str
    holder_name: str
    dob: date
    address_line: str
    city: str
    state: str
    country: str
    phone_number: str
    balance: Decimal
    currency: str
    is_active: bool
    version: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_entity(cls, entity: Account) -> AccountDTO:
        return cls(
            account_number=entity.account_number.value,
            holder_name=entity.holder_name,
            dob=entity.dob,
            address_line=entity.address_line,
            city=entity.city,
            state=entity.state,
            country=entity.country,
            phone_number=entity.phone_number,
            balance=entity.balance.amount,
            currency=entity.balance.currency,
            is_active=entity.is_active,
            version=entity.version,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )


@dataclass(frozen=True)
class OpenAccountResultDTO:
    """Result DTO returned upon successful account registration."""

    account: AccountDTO
    initial_transaction: Optional[TransactionDTO] = None
