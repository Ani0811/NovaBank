"""Domain repository interfaces (Ports)."""

from novabank.domain.repositories.account_repository import AccountRepositoryInterface
from novabank.domain.repositories.audit_repository import AuditRepository
from novabank.domain.repositories.beneficiary_repository import BeneficiaryRepositoryInterface
from novabank.domain.repositories.fx_repository import FXRepositoryInterface
from novabank.domain.repositories.loan_repository import LoanRepositoryInterface
from novabank.domain.repositories.payment_repository import PaymentRepositoryInterface
from novabank.domain.repositories.term_deposit_repository import (
    TermDepositRepositoryInterface,
)
from novabank.domain.repositories.transaction_repository import TransactionRepositoryInterface

__all__ = [
    "AccountRepositoryInterface",
    "AuditRepository",
    "BeneficiaryRepositoryInterface",
    "FXRepositoryInterface",
    "LoanRepositoryInterface",
    "PaymentRepositoryInterface",
    "TermDepositRepositoryInterface",
    "TransactionRepositoryInterface",
]
