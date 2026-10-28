"""Application Data Transfer Objects."""

from novabank.application.dto.account_dto import (
    AccountDTO,
    OpenAccountRequestDTO,
    OpenAccountResultDTO,
)
from novabank.application.dto.transaction_dto import (
    DepositRequestDTO,
    TransactionDTO,
    TransferRequestDTO,
    TransferResultDTO,
    WithdrawalRequestDTO,
)

__all__ = [
    "AccountDTO",
    "DepositRequestDTO",
    "OpenAccountRequestDTO",
    "OpenAccountResultDTO",
    "TransactionDTO",
    "TransferRequestDTO",
    "TransferResultDTO",
    "WithdrawalRequestDTO",
]
