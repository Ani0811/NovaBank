"""Immutable AccountNumber value object with validation and generation."""

from __future__ import annotations

import re
import secrets
from typing import Any

from novabank.domain.exceptions import DomainError


class AccountNumber:
    """12-digit bank account number value object.

    Guarantees:
    - Exactly 12 numeric digits.
    - Cannot be all zeros.
    - Immutable and hashable.
    - Masking support for logging and AI privacy boundaries.
    """

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError(f"Account number must be a string, got {type(value).__name__}")

        clean_val = value.strip().replace("-", "").replace(" ", "")

        if not re.fullmatch(r"\d{12}", clean_val):
            raise DomainError(
                f"Account number must consist of exactly 12 numeric digits, got: '{value}'"
            )

        if clean_val == "000000000000":
            raise DomainError("Account number cannot be all zeros.")

        object.__setattr__(self, "_value", clean_val)

    @property
    def value(self) -> str:
        """The full 12-digit string value."""
        return self._value

    @property
    def masked(self) -> str:
        """Masked string for privacy boundaries (e.g. '****-****-1234')."""
        return f"****-****-{self._value[-4:]}"

    @property
    def formatted(self) -> str:
        """Formatted string with standard 4-digit grouping (e.g. '1234-5678-9012')."""
        return f"{self._value[:4]}-{self._value[4:8]}-{self._value[8:]}"

    @classmethod
    def generate(cls) -> AccountNumber:
        """Generate a cryptographically secure random 12-digit account number."""
        # Ensure first digit is 1-9 so it remains a 12-digit number
        first_digit = secrets.choice("123456789")
        remaining_digits = "".join(secrets.choice("0123456789") for _ in range(11))
        return cls(f"{first_digit}{remaining_digits}")

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, AccountNumber):
            return False
        return self._value == other._value

    def __hash__(self) -> int:
        return hash(self._value)

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("AccountNumber instances are immutable.")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("AccountNumber instances are immutable.")

    def __repr__(self) -> str:
        return f"AccountNumber('{self._value}')"

    def __str__(self) -> str:
        return self._value
