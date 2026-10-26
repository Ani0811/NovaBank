"""Domain repository interfaces (Ports)."""

from novabank.domain.repositories.account_repository import AccountRepositoryInterface
from novabank.domain.repositories.transaction_repository import TransactionRepositoryInterface

__all__ = [
    "AccountRepositoryInterface",
    "TransactionRepositoryInterface",
]
