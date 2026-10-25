"""Immutable Money value object with exact decimal arithmetic."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Union

from novabank.domain.exceptions import (
    CurrencyMismatchError,
    InvalidMoneyError,
    NegativeMoneyError,
)

# Standard monetary quantization: 2 decimal places
CENT = Decimal("0.01")


class Money:
    """Immutable monetary representation ensuring exact decimal precision.

    Guarantees:
    - Never uses IEEE 754 floating point arithmetic.
    - Strictly quantizes to 2 decimal places using ROUND_HALF_UP.
    - Forbids float inputs to prevent precision loss before construction.
    - Supports arithmetic, comparison, formatting, and serialization.
    """

    __slots__ = ("_amount", "_currency")

    def __init__(
        self,
        amount: Union[Decimal, int, str],
        currency: str = "USD",
        allow_negative: bool = False,
    ) -> None:
        if isinstance(amount, float):
            raise TypeError(
                "Float types are strictly prohibited in Money to prevent floating point inaccuracies. "
                "Use Decimal, int, or str instead."
            )

        if not isinstance(currency, str) or not currency.strip():
            raise InvalidMoneyError("Currency code must be a non-empty string.")

        try:
            dec_amount = Decimal(str(amount) if isinstance(amount, int) else amount)
        except (InvalidOperation, TypeError, ValueError) as err:
            raise InvalidMoneyError(
                f"Cannot construct Money from invalid value: {amount!r}"
            ) from err

        # Quantize to 2 decimal places
        quantized = dec_amount.quantize(CENT, rounding=ROUND_HALF_UP)

        if not allow_negative and quantized < Decimal("0.00"):
            raise NegativeMoneyError(
                f"Negative money amount {quantized} is not permitted for standard monetary amounts."
            )

        object.__setattr__(self, "_amount", quantized)
        object.__setattr__(self, "_currency", currency.strip().upper())

    @property
    def amount(self) -> Decimal:
        """The exact quantized decimal value."""
        return self._amount

    @property
    def currency(self) -> str:
        """The three-letter ISO currency code (e.g. USD, INR, EUR)."""
        return self._currency

    @classmethod
    def zero(cls, currency: str = "USD") -> Money:
        """Construct zero monetary amount."""
        return cls(Decimal("0.00"), currency=currency)

    @classmethod
    def from_cents(cls, cents: int, currency: str = "USD", allow_negative: bool = False) -> Money:
        """Construct Money from an integer number of cents/paise (e.g. 1050 -> $10.50)."""
        if not isinstance(cents, int):
            raise TypeError(f"Cents must be an integer, got {type(cents).__name__}")
        dec_amount = Decimal(cents) / Decimal("100")
        return cls(dec_amount, currency=currency, allow_negative=allow_negative)

    @classmethod
    def from_str(cls, value_str: str, currency: str = "USD", allow_negative: bool = False) -> Money:
        """Construct Money from a string representation (e.g. '123.45')."""
        clean_str = value_str.strip().replace(",", "")
        return cls(clean_str, currency=currency, allow_negative=allow_negative)

    def to_cents(self) -> int:
        """Convert to integer cents without floating-point conversion."""
        return int(self._amount * Decimal("100"))

    def is_zero(self) -> bool:
        """Return True if amount is zero."""
        return self._amount == Decimal("0.00")

    def is_positive(self) -> bool:
        """Return True if amount is strictly greater than zero."""
        return self._amount > Decimal("0.00")

    def is_negative(self) -> bool:
        """Return True if amount is strictly less than zero."""
        return self._amount < Decimal("0.00")

    def formatted(self, include_symbol: bool = True) -> str:
        """Format monetary amount with thousands separators and optional currency symbol."""
        symbol_map = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£"}
        symbol = symbol_map.get(self._currency, f"{self._currency} ") if include_symbol else ""
        formatted_number = f"{self._amount:,.2f}"
        return f"{symbol}{formatted_number}"

    # -----------------------------------------------------------------------
    # Arithmetic Operations
    # -----------------------------------------------------------------------

    def _assert_same_currency(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError(f"Cannot perform Money operation with type {type(other).__name__}")
        if self._currency != other._currency:
            raise CurrencyMismatchError(
                f"Cannot operate between different currencies: {self._currency} and {other._currency}"
            )

    def __add__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        new_amount = self._amount + other._amount
        allow_neg = new_amount < Decimal("0.00")
        return Money(new_amount, currency=self._currency, allow_negative=allow_neg)

    def __sub__(self, other: Money) -> Money:
        self._assert_same_currency(other)
        new_amount = self._amount - other._amount
        allow_neg = new_amount < Decimal("0.00")
        return Money(new_amount, currency=self._currency, allow_negative=allow_neg)

    def __mul__(self, scalar: Union[int, Decimal]) -> Money:
        if isinstance(scalar, float):
            raise TypeError("Multiplication by float is prohibited. Use int or Decimal.")
        if not isinstance(scalar, (int, Decimal)):
            raise TypeError(f"Cannot multiply Money by {type(scalar).__name__}")
        new_amount = self._amount * Decimal(str(scalar) if isinstance(scalar, int) else scalar)
        allow_neg = new_amount < Decimal("0.00")
        return Money(new_amount, currency=self._currency, allow_negative=allow_neg)

    def __rmul__(self, scalar: Union[int, Decimal]) -> Money:
        return self.__mul__(scalar)

    def __truediv__(self, divisor: Union[int, Decimal]) -> Money:
        if isinstance(divisor, float):
            raise TypeError("Division by float is prohibited. Use int or Decimal.")
        if not isinstance(divisor, (int, Decimal)):
            raise TypeError(f"Cannot divide Money by {type(divisor).__name__}")
        dec_div = Decimal(str(divisor) if isinstance(divisor, int) else divisor)
        if dec_div == Decimal("0"):
            raise ZeroDivisionError("Cannot divide Money by zero.")
        new_amount = self._amount / dec_div
        allow_neg = new_amount < Decimal("0.00")
        return Money(new_amount, currency=self._currency, allow_negative=allow_neg)

    def __neg__(self) -> Money:
        return Money(-self._amount, currency=self._currency, allow_negative=True)

    def __abs__(self) -> Money:
        return Money(abs(self._amount), currency=self._currency, allow_negative=False)

    # -----------------------------------------------------------------------
    # Comparison Operations
    # -----------------------------------------------------------------------

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Money):
            return False
        return self._amount == other._amount and self._currency == other._currency

    def __lt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self._amount < other._amount

    def __le__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self._amount <= other._amount

    def __gt__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self._amount > other._amount

    def __ge__(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self._amount >= other._amount

    # -----------------------------------------------------------------------
    # Immutability, Hash & Representation
    # -----------------------------------------------------------------------

    def __setattr__(self, name: str, value: Any) -> None:
        raise AttributeError("Money instances are immutable.")

    def __delattr__(self, name: str) -> None:
        raise AttributeError("Money instances are immutable.")

    def __hash__(self) -> int:
        return hash((self._amount, self._currency))

    def __repr__(self) -> str:
        return f"Money({self._amount!r}, currency={self._currency!r})"

    def __str__(self) -> str:
        return self.formatted(include_symbol=True)
