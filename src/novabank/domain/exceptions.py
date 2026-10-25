"""Domain-level exceptions and banking business rule errors."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for all domain-level exceptions."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidMoneyError(DomainError):
    """Raised when an invalid monetary value or illegal operation is attempted."""


class NegativeMoneyError(InvalidMoneyError):
    """Raised when a strictly non-negative money amount is expected but negative received."""


class CurrencyMismatchError(DomainError):
    """Raised when performing arithmetic across two different currencies."""


class InsufficientFundsError(DomainError):
    """Raised when a withdrawal or debit exceeds available account balance."""

    def __init__(self, current_balance: str, requested_amount: str) -> None:
        msg = f"Insufficient funds: available balance is {current_balance}, requested {requested_amount}."
        super().__init__(msg)
        self.current_balance = current_balance
        self.requested_amount = requested_amount


class AccountClosedError(DomainError):
    """Raised when an operation is attempted on an inactive or closed account."""

    def __init__(self, account_number: str) -> None:
        msg = f"Account {account_number} is closed or inactive. Transactions are prohibited."
        super().__init__(msg)
        self.account_number = account_number


class AccountNotFoundError(DomainError):
    """Raised when the requested account number does not exist."""

    def __init__(self, account_number: str) -> None:
        msg = f"Account {account_number} not found."
        super().__init__(msg)
        self.account_number = account_number


class InvalidAmountError(DomainError):
    """Raised when an operation amount violates business rules (e.g. <= 0 or exceeds limits)."""


class DuplicateTransactionRefError(DomainError):
    """Raised when an idempotency violation occurs with a duplicate transaction reference."""
