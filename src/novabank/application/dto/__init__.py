"""Application Data Transfer Objects."""

from novabank.application.dto.account_dto import (
    AccountDTO,
    OpenAccountRequestDTO,
    OpenAccountResultDTO,
)
from novabank.application.dto.loan_dto import (
    AmortizationScheduleEntryDTO,
    LoanContractDTO,
    LoanOriginationRequestDTO,
    LoanQuoteRequestDTO,
    LoanQuoteResponseDTO,
    LoanRepaymentResultDTO,
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
    "AmortizationScheduleEntryDTO",
    "DepositRequestDTO",
    "LoanContractDTO",
    "LoanOriginationRequestDTO",
    "LoanQuoteRequestDTO",
    "LoanQuoteResponseDTO",
    "LoanRepaymentResultDTO",
    "OpenAccountRequestDTO",
    "OpenAccountResultDTO",
    "TransactionDTO",
    "TransferRequestDTO",
    "TransferResultDTO",
    "WithdrawalRequestDTO",
]
