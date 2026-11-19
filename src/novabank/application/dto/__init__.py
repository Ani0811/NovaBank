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
from novabank.application.dto.term_deposit_dto import (
    CDAccrualMilestoneDTO,
    CDSimulationRequestDTO,
    CDSimulationResponseDTO,
    CertificateOfDepositDTO,
    EarlyRedemptionPreviewDTO,
    OpenCDRequestDTO,
    RedemptionResultDTO,
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
    "CDAccrualMilestoneDTO",
    "CDSimulationRequestDTO",
    "CDSimulationResponseDTO",
    "CertificateOfDepositDTO",
    "DepositRequestDTO",
    "EarlyRedemptionPreviewDTO",
    "LoanContractDTO",
    "LoanOriginationRequestDTO",
    "LoanQuoteRequestDTO",
    "LoanQuoteResponseDTO",
    "LoanRepaymentResultDTO",
    "OpenAccountRequestDTO",
    "OpenAccountResultDTO",
    "OpenCDRequestDTO",
    "RedemptionResultDTO",
    "TransactionDTO",
    "TransferRequestDTO",
    "TransferResultDTO",
    "WithdrawalRequestDTO",
]
