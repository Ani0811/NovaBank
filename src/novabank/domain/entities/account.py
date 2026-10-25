"""Account domain entity and banking business invariants."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from novabank.domain.entities.transaction import Transaction
from novabank.domain.exceptions import (
    AccountClosedError,
    CurrencyMismatchError,
    DomainError,
    InsufficientFundsError,
    InvalidAmountError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType


class Account:
    """Core Account domain entity enforcing business invariants and atomic state changes."""

    def __init__(
        self,
        account_number: AccountNumber,
        holder_name: str,
        dob: date,
        address_line: str,
        city: str,
        state: str,
        country: str,
        phone_number: str,
        is_active: bool = True,
        balance: Optional[Money] = None,
        version: int = 1,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
    ) -> None:
        self.account_number = account_number
        self.holder_name = self._validate_holder_name(holder_name)
        self.dob = self._validate_dob(dob)
        self.address_line = self._validate_address(address_line, "Address line", 255)
        self.city = self._validate_address(city, "City", 100)
        self.state = self._validate_address(state, "State", 100)
        self.country = self._validate_address(country, "Country", 100)
        self.phone_number = self._validate_phone(phone_number)
        self.is_active = is_active
        self.balance = balance if balance is not None else Money.zero()
        self.version = version
        self.created_at = created_at or datetime.now(timezone.utc)
        self.updated_at = updated_at or datetime.now(timezone.utc)

    # -----------------------------------------------------------------------
    # Invariant Validation Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _validate_holder_name(name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise DomainError("Account holder name cannot be empty.")
        clean = name.strip()
        if len(clean) > 100:
            raise DomainError("Account holder name cannot exceed 100 characters.")
        if len(clean) < 2:
            raise DomainError("Account holder name must be at least 2 characters long.")
        return clean

    @staticmethod
    def _validate_dob(dob: date) -> date:
        if not isinstance(dob, date):
            raise TypeError("Date of birth must be a date object.")
        today = date.today()
        if dob > today:
            raise DomainError("Date of birth cannot be in the future.")

        # Age calculation
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        if age < 18:
            raise DomainError(f"Account holder must be at least 18 years old (current age: {age}).")
        if age > 120:
            raise DomainError(f"Account holder age cannot exceed 120 years (current age: {age}).")
        return dob

    @staticmethod
    def _validate_phone(phone: str) -> str:
        if not isinstance(phone, str):
            raise TypeError("Phone number must be a string.")
        clean = phone.strip().replace(" ", "").replace("-", "")
        if not re.fullmatch(r"\d{10}", clean):
            raise DomainError(f"Phone number must consist of exactly 10 digits, got '{phone}'")
        return clean

    @staticmethod
    def _validate_address(val: str, field_name: str, max_len: int) -> str:
        if not isinstance(val, str) or not val.strip():
            raise DomainError(f"{field_name} cannot be empty.")
        clean = val.strip()
        if len(clean) > max_len:
            raise DomainError(f"{field_name} cannot exceed {max_len} characters.")
        return clean

    # -----------------------------------------------------------------------
    # Financial State Mutations
    # -----------------------------------------------------------------------

    def credit(
        self,
        amount: Money,
        transaction_type: TransactionType = TransactionType.DEPOSIT,
        description: str = "",
        ref: Optional[str] = None,
        actor: str = "system",
    ) -> Transaction:
        """Deposit / Credit funds to this account, returning a new immutable Transaction."""
        if not self.is_active:
            raise AccountClosedError(self.account_number.value)

        if not isinstance(amount, Money) or not amount.is_positive():
            raise InvalidAmountError(f"Credit amount must be positive, got {amount}")

        if amount.currency != self.balance.currency:
            raise CurrencyMismatchError(
                f"Credit currency {amount.currency} does not match account currency {self.balance.currency}"
            )

        new_balance = self.balance + amount
        self.balance = new_balance
        self.version += 1
        self.updated_at = datetime.now(timezone.utc)

        return Transaction(
            account_number=self.account_number,
            transaction_type=transaction_type,
            direction=TransactionDirection.CREDIT,
            amount=amount,
            balance_after=new_balance,
            description=description or "Cash Deposit",
            transaction_ref=ref or str(uuid.uuid4()),
            created_by=actor,
        )

    def debit(
        self,
        amount: Money,
        transaction_type: TransactionType = TransactionType.WITHDRAWAL,
        description: str = "",
        ref: Optional[str] = None,
        actor: str = "system",
    ) -> Transaction:
        """Withdraw / Debit funds from this account, returning a new immutable Transaction."""
        if not self.is_active:
            raise AccountClosedError(self.account_number.value)

        if not isinstance(amount, Money) or not amount.is_positive():
            raise InvalidAmountError(f"Debit amount must be positive, got {amount}")

        if amount.currency != self.balance.currency:
            raise CurrencyMismatchError(
                f"Debit currency {amount.currency} does not match account currency {self.balance.currency}"
            )

        if self.balance < amount:
            raise InsufficientFundsError(self.balance.formatted(), amount.formatted())

        new_balance = self.balance - amount
        self.balance = new_balance
        self.version += 1
        self.updated_at = datetime.now(timezone.utc)

        return Transaction(
            account_number=self.account_number,
            transaction_type=transaction_type,
            direction=TransactionDirection.DEBIT,
            amount=amount,
            balance_after=new_balance,
            description=description or "Cash Withdrawal",
            transaction_ref=ref or str(uuid.uuid4()),
            created_by=actor,
        )

    def close(self, reason: str = "") -> None:
        """Close/deactivate this account. Requires balance to be zero."""
        if not self.is_active:
            raise DomainError(f"Account {self.account_number.value} is already closed.")

        if not self.balance.is_zero():
            raise DomainError(
                f"Account balance must be zero before closure (current balance: {self.balance.formatted()})."
            )

        self.is_active = False
        self.version += 1
        self.updated_at = datetime.now(timezone.utc)

    def update_profile(
        self,
        address_line: str,
        city: str,
        state: str,
        country: str,
        phone_number: str,
    ) -> None:
        """Update mutable customer contact details with validation."""
        self.address_line = self._validate_address(address_line, "Address line", 255)
        self.city = self._validate_address(city, "City", 100)
        self.state = self._validate_address(state, "State", 100)
        self.country = self._validate_address(country, "Country", 100)
        self.phone_number = self._validate_phone(phone_number)
        self.version += 1
        self.updated_at = datetime.now(timezone.utc)

    def __repr__(self) -> str:
        return (
            f"Account(no='{self.account_number.value}', holder='{self.holder_name}', "
            f"balance={self.balance.formatted()}, active={self.is_active})"
        )
