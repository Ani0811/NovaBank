"""Transaction type and direction enumerations."""

from enum import Enum


class TransactionType(str, Enum):
    """Categorical type of financial ledger transaction."""

    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    TRANSFER_IN = "TRANSFER_IN"
    TRANSFER_OUT = "TRANSFER_OUT"
    FEE = "FEE"
    INTEREST = "INTEREST"


class TransactionDirection(str, Enum):
    """Direction of money flow relative to the account."""

    CREDIT = "CREDIT"
    DEBIT = "DEBIT"
