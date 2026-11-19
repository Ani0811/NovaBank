"""SQL Repository implementations."""

from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_audit_repository import SQLAuditRepository
from novabank.infrastructure.repositories.sql_beneficiary_repository import (
    SQLBeneficiaryRepository,
)
from novabank.infrastructure.repositories.sql_loan_repository import SQLLoanRepository
from novabank.infrastructure.repositories.sql_payment_repository import (
    SQLPaymentRepository,
)
from novabank.infrastructure.repositories.sql_term_deposit_repository import (
    SQLTermDepositRepository,
)
from novabank.infrastructure.repositories.sql_transaction_repository import (
    SQLTransactionRepository,
)

__all__ = [
    "SQLAccountRepository",
    "SQLAuditRepository",
    "SQLBeneficiaryRepository",
    "SQLLoanRepository",
    "SQLPaymentRepository",
    "SQLTermDepositRepository",
    "SQLTransactionRepository",
]
