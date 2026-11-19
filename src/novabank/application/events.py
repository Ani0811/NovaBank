"""Application and domain lifecycle events."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class AccountOpenedEvent:
    """Emitted upon successful creation and registration of a new customer account."""

    account_number: str
    holder_name: str
    phone_number: str
    initial_deposit: Decimal
    currency: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class ProfileUpdatedEvent:
    """Emitted upon successful modification of customer contact information."""

    account_number: str
    phone_number: str
    city: str
    state: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class AccountClosedEvent:
    """Emitted upon account closure."""

    account_number: str
    reason: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class AccountFrozenEvent:
    """Emitted upon administrative account freeze."""

    account_number: str
    reason: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class AccountUnfrozenEvent:
    """Emitted upon administrative account unfreeze."""

    account_number: str
    reason: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class DepositCompletedEvent:
    """Emitted upon successful commit of a cash deposit transaction."""

    account_number: str
    amount: Decimal
    balance_after: Decimal
    currency: str
    transaction_ref: str
    timestamp: datetime
    actor: str = "system"
    description: str = "Cash Deposit"


@dataclass(frozen=True)
class WithdrawalCompletedEvent:
    """Emitted upon successful commit of a cash withdrawal transaction."""

    account_number: str
    amount: Decimal
    balance_after: Decimal
    currency: str
    transaction_ref: str
    timestamp: datetime
    actor: str = "system"
    description: str = "Cash Withdrawal"


@dataclass(frozen=True)
class TransferCompletedEvent:
    """Emitted upon successful commit of an account-to-account fund transfer."""

    source_account: str
    destination_account: str
    amount: Decimal
    source_balance_after: Decimal
    destination_balance_after: Decimal
    currency: str
    correlation_id: str
    timestamp: datetime
    actor: str = "system"
    description: str = "Account Transfer"


@dataclass(frozen=True)
class BeneficiaryAddedEvent:
    """Emitted upon registering a new beneficiary/payee contact."""

    source_account: str
    destination_account: str
    destination_holder_name: str
    nickname: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class BeneficiaryRemovedEvent:
    """Emitted upon removing a beneficiary/payee contact."""

    beneficiary_id: int
    source_account: str
    destination_account: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class InterestAccruedEvent:
    """Emitted upon successful batch accrual of monthly interest."""

    accounts_credited: int
    total_interest_credited: Decimal
    annual_rate_percentage: Decimal
    timestamp: datetime
    actor: str = "system"


@dataclass(frozen=True)
class PaymentProcessedEvent:
    """Emitted upon successful authorization and settlement of a gateway payment."""

    payment_id: str
    account_number: str
    channel: str
    amount: Decimal
    fee: Decimal
    net_amount: Decimal
    merchant_name: str
    timestamp: datetime
    actor: str = "gateway"


@dataclass(frozen=True)
class PaymentRefundedEvent:
    """Emitted upon executing a full or partial refund against a settled transaction."""

    payment_id: str
    account_number: str
    refund_amount: Decimal
    reason: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class PaymentDeclinedEvent:
    """Emitted upon issuer or network decline of a payment request."""

    payment_id: str
    account_number: str
    amount: Decimal
    reason: str
    timestamp: datetime
    actor: str = "gateway"


@dataclass(frozen=True)
class LoanOriginatedEvent:
    """Emitted upon approval, disbursement, and scheduling of a commercial credit facility."""

    loan_id: str
    account_number: str
    principal: Decimal
    interest_rate_apr: Decimal
    term_months: int
    monthly_installment: Decimal
    timestamp: datetime
    actor: str = "lending_officer"


@dataclass(frozen=True)
class LoanRepaymentProcessedEvent:
    """Emitted upon successful settlement of an amortization installment payment."""

    loan_id: str
    account_number: str
    amount: Decimal
    principal_portion: Decimal
    interest_portion: Decimal
    remaining_balance: Decimal
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class LoanPaidOffEvent:
    """Emitted when a loan balance reaches zero, closing out the facility."""

    loan_id: str
    account_number: str
    total_principal_paid: Decimal
    timestamp: datetime
    actor: str = "system"


@dataclass(frozen=True)
class TermDepositOpenedEvent:
    """Emitted upon successful funding and issuance of a Certificate of Deposit."""

    cd_id: str
    certificate_number: str
    account_number: str
    principal: Decimal
    interest_rate_apy: Decimal
    tenor_months: int
    maturity_date: str
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class TermDepositMaturedEvent:
    """Emitted when a CD reaches maturity and proceeds are disbursed."""

    cd_id: str
    certificate_number: str
    account_number: str
    principal: Decimal
    interest_paid: Decimal
    total_payout: Decimal
    timestamp: datetime
    actor: str = "system"


@dataclass(frozen=True)
class TermDepositEarlyRedeemedEvent:
    """Emitted upon premature liquidation of a CD with penalty deduction."""

    cd_id: str
    certificate_number: str
    account_number: str
    principal: Decimal
    accrued_interest: Decimal
    penalty_deducted: Decimal
    net_payout: Decimal
    timestamp: datetime
    actor: str = "teller"


@dataclass(frozen=True)
class TermDepositRolledOverEvent:
    """Emitted when a matured CD rolls over into a new vault contract."""

    old_cd_id: str
    new_cd_id: str
    account_number: str
    principal: Decimal
    new_apy: Decimal
    timestamp: datetime
    actor: str = "system"





