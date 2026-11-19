"""SQLAlchemy 2.0 ORM Declarative Models for NovaBank."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from novabank.domain.entities.account import Account
from novabank.domain.entities.beneficiary import Beneficiary
from novabank.domain.entities.loan import (
    AmortizationScheduleEntry,
    LoanContract,
    LoanStatus,
    LoanType,
)
from novabank.domain.entities.payment import (
    PaymentChannel,
    PaymentDirection,
    PaymentStatus,
    PaymentTransaction,
)
from novabank.domain.entities.term_deposit import (
    CDAccrualMilestone,
    CertificateOfDeposit,
    TermDepositPayoutFrequency,
    TermDepositRolloverOption,
    TermDepositStatus,
)
from novabank.domain.entities.transaction import Transaction
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""


class AccountModel(Base):
    """Relational model for customer bank accounts."""

    __tablename__ = "accounts"

    account_number: Mapped[str] = mapped_column(String(12), primary_key=True)
    holder_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dob: Mapped[date] = mapped_column(Date, nullable=False)
    address_line: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(15), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2, asdecimal=True), default=Decimal("0.00"), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    transactions: Mapped[list[TransactionModel]] = relationship(
        "TransactionModel",
        back_populates="account",
        order_by="TransactionModel.created_at.desc()",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("balance >= 0.00", name="chk_accounts_balance_non_negative"),
        Index("idx_accounts_holder_name", "holder_name"),
        Index("idx_accounts_phone", "phone_number"),
    )

    def to_entity(self) -> Account:
        """Convert ORM model to pure Domain Account entity."""
        return Account(
            account_number=AccountNumber(self.account_number),
            holder_name=self.holder_name,
            dob=self.dob,
            address_line=self.address_line,
            city=self.city,
            state=self.state,
            country=self.country,
            phone_number=self.phone_number,
            is_active=self.is_active,
            is_frozen=self.is_frozen,
            balance=Money(self.balance, currency=self.currency, allow_negative=False),
            version=self.version,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )

    @classmethod
    def from_entity(cls, entity: Account) -> AccountModel:
        """Construct ORM model from pure Domain Account entity."""
        return cls(
            account_number=entity.account_number.value,
            holder_name=entity.holder_name,
            dob=entity.dob,
            address_line=entity.address_line,
            city=entity.city,
            state=entity.state,
            country=entity.country,
            phone_number=entity.phone_number,
            is_active=entity.is_active,
            is_frozen=entity.is_frozen,
            balance=entity.balance.amount,
            currency=entity.balance.currency,
            version=entity.version,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )

    def update_from_entity(self, entity: Account) -> None:
        """Synchronize ORM model attributes from modified Domain entity."""
        self.holder_name = entity.holder_name
        self.dob = entity.dob
        self.address_line = entity.address_line
        self.city = entity.city
        self.state = entity.state
        self.country = entity.country
        self.phone_number = entity.phone_number
        self.is_active = entity.is_active
        self.is_frozen = entity.is_frozen
        self.balance = entity.balance.amount
        self.currency = entity.balance.currency
        self.version = entity.version
        self.updated_at = entity.updated_at


class TransactionModel(Base):
    """Relational model for immutable transaction ledger entries."""

    __tablename__ = "transactions"

    transaction_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    transaction_ref: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    account_number: Mapped[str] = mapped_column(
        String(12), ForeignKey("accounts.account_number", ondelete="RESTRICT"), nullable=False
    )
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2, asdecimal=True), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(15, 2, asdecimal=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_by: Mapped[str] = mapped_column(String(50), default="system", nullable=False)

    # Relationships
    account: Mapped[AccountModel] = relationship("AccountModel", back_populates="transactions")

    __table_args__ = (
        CheckConstraint("amount > 0.00", name="chk_transactions_amount_positive"),
        Index("idx_transactions_account", "account_number"),
        Index("idx_transactions_created_at", "created_at"),
        Index("idx_transactions_ref", "transaction_ref"),
    )

    def to_entity(self) -> Transaction:
        """Convert ORM model to pure Domain Transaction entity."""
        return Transaction(
            account_number=AccountNumber(self.account_number),
            transaction_type=TransactionType(self.transaction_type),
            direction=TransactionDirection(self.direction),
            amount=Money(self.amount, currency=self.currency),
            balance_after=Money(self.balance_after, currency=self.currency),
            description=self.description,
            transaction_ref=self.transaction_ref,
            created_at=self.created_at,
            created_by=self.created_by,
            transaction_id=self.transaction_id,
        )

    @classmethod
    def from_entity(cls, entity: Transaction) -> TransactionModel:
        """Construct ORM model from pure Domain Transaction entity."""
        return cls(
            transaction_id=entity.transaction_id,
            transaction_ref=entity.transaction_ref,
            account_number=entity.account_number.value,
            transaction_type=entity.transaction_type.value,
            direction=entity.direction.value,
            amount=entity.amount.amount,
            balance_after=entity.balance_after.amount,
            currency=entity.amount.currency,
            description=entity.description,
            created_at=entity.created_at,
            created_by=entity.created_by,
        )


class AuditEventModel(Base):
    """Relational model for compliance audit events and administrative tracking."""

    __tablename__ = "audit_events"

    event_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(50), nullable=False)
    actor: Mapped[str] = mapped_column(String(50), default="system", nullable=False)
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("idx_audit_event_type", "event_type"),
        Index("idx_audit_entity", "entity_type", "entity_id"),
        Index("idx_audit_timestamp", "timestamp"),
    )


class BeneficiaryModel(Base):
    """Relational model for frequent payee contacts and transfer beneficiaries."""

    __tablename__ = "beneficiaries"

    beneficiary_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    source_account_number: Mapped[str] = mapped_column(
        String(12), ForeignKey("accounts.account_number", ondelete="CASCADE"), nullable=False
    )
    destination_account_number: Mapped[str] = mapped_column(
        String(12), ForeignKey("accounts.account_number", ondelete="CASCADE"), nullable=False
    )
    destination_holder_name: Mapped[str] = mapped_column(String(100), nullable=False)
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(100), default="NovaBank", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "source_account_number", "destination_account_number", name="uq_beneficiary_source_dest"
        ),
        Index("idx_beneficiary_source", "source_account_number"),
    )

    def to_entity(self) -> Beneficiary:
        """Convert ORM model to pure Domain Beneficiary entity."""
        return Beneficiary(
            source_account_number=AccountNumber(self.source_account_number),
            destination_account_number=AccountNumber(self.destination_account_number),
            destination_holder_name=self.destination_holder_name,
            nickname=self.nickname,
            bank_name=self.bank_name,
            beneficiary_id=self.beneficiary_id,
            created_at=self.created_at,
        )

    @classmethod
    def from_entity(cls, entity: Beneficiary) -> BeneficiaryModel:
        """Construct ORM model from pure Domain Beneficiary entity."""
        return cls(
            beneficiary_id=entity.beneficiary_id,
            source_account_number=entity.source_account_number.value,
            destination_account_number=entity.destination_account_number.value,
            destination_holder_name=entity.destination_holder_name,
            nickname=entity.nickname,
            bank_name=entity.bank_name,
            created_at=entity.created_at,
        )


class PaymentTransactionModel(Base):
    """Relational model for payment gateway authorizations and settlements."""

    __tablename__ = "payment_transactions"

    payment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_number: Mapped[str] = mapped_column(
        String(12), ForeignKey("accounts.account_number", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    direction: Mapped[str] = mapped_column(String(20), default="INBOUND", nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.00"), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="AUTHORIZED", nullable=False)
    merchant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    card_brand: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last4: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    refund_reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("idx_payment_account", "account_number"),
        Index("idx_payment_status", "status"),
        Index("idx_payment_created", "created_at"),
        Index("idx_payment_idempotency", "idempotency_key"),
    )

    def to_entity(self) -> PaymentTransaction:
        """Convert ORM model to pure Domain PaymentTransaction entity."""
        return PaymentTransaction(
            payment_id=self.payment_id,
            account_number=AccountNumber(self.account_number),
            channel=PaymentChannel(self.channel),
            direction=PaymentDirection(self.direction),
            amount=Money(self.amount, currency=self.currency),
            fee=Money(self.fee, currency=self.currency),
            status=PaymentStatus(self.status),
            merchant_name=self.merchant_name,
            customer_name=self.customer_name,
            idempotency_key=self.idempotency_key,
            card_brand=self.card_brand,
            last4=self.last4,
            description=self.description,
            created_at=self.created_at,
            settled_at=self.settled_at,
            failure_reason=self.failure_reason,
            refund_reason=self.refund_reason,
        )

    @classmethod
    def from_entity(cls, entity: PaymentTransaction) -> PaymentTransactionModel:
        """Construct ORM model from pure Domain PaymentTransaction entity."""
        return cls(
            payment_id=entity.payment_id,
            account_number=entity.account_number.value,
            channel=entity.channel.value,
            direction=entity.direction.value,
            amount=entity.amount.amount,
            fee=entity.fee.amount,
            currency=entity.amount.currency,
            status=entity.status.value,
            merchant_name=entity.merchant_name,
            customer_name=entity.customer_name,
            idempotency_key=entity.idempotency_key,
            card_brand=entity.card_brand,
            last4=entity.last4,
            description=entity.description,
            failure_reason=entity.failure_reason,
            refund_reason=entity.refund_reason,
            created_at=entity.created_at,
            settled_at=entity.settled_at,
        )


class LoanContractModel(Base):
    """Relational model for commercial loans, credit lines, and amortization schedules."""

    __tablename__ = "loan_contracts"

    loan_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_number: Mapped[str] = mapped_column(
        String(12), ForeignKey("accounts.account_number"), nullable=False
    )
    loan_type: Mapped[str] = mapped_column(String(30), nullable=False)
    principal_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2, asdecimal=True), nullable=False
    )
    interest_rate_apr: Mapped[Decimal] = mapped_column(
        Numeric(5, 2, asdecimal=True), nullable=False
    )
    term_months: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_installment: Mapped[Decimal] = mapped_column(
        Numeric(15, 2, asdecimal=True), nullable=False
    )
    outstanding_balance: Mapped[Decimal] = mapped_column(
        Numeric(15, 2, asdecimal=True), nullable=False
    )
    total_interest: Mapped[Decimal] = mapped_column(
        Numeric(15, 2, asdecimal=True), nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="SUBMITTED", nullable=False)
    purpose: Mapped[str] = mapped_column(String(255), default="Commercial Financing", nullable=False)
    originated_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    next_due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    schedule_json: Mapped[Any] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        Index("idx_loan_account", "account_number"),
        Index("idx_loan_status", "status"),
        Index("idx_loan_originated", "originated_at"),
    )

    def to_entity(self) -> LoanContract:
        """Convert ORM model to pure Domain LoanContract entity."""
        entries: list[AmortizationScheduleEntry] = []
        if self.schedule_json and isinstance(self.schedule_json, list):
            for item in self.schedule_json:
                entries.append(
                    AmortizationScheduleEntry(
                        installment_number=int(item["installment_number"]),
                        due_date=date.fromisoformat(item["due_date"])
                        if isinstance(item["due_date"], str)
                        else item["due_date"],
                        payment_amount=Money(Decimal(str(item["payment_amount"])), currency=self.currency),
                        principal_amount=Money(Decimal(str(item["principal_amount"])), currency=self.currency),
                        interest_amount=Money(Decimal(str(item["interest_amount"])), currency=self.currency),
                        remaining_balance=Money(Decimal(str(item["remaining_balance"])), currency=self.currency),
                        is_paid=bool(item.get("is_paid", False)),
                        paid_date=date.fromisoformat(item["paid_date"])
                        if item.get("paid_date")
                        else None,
                    )
                )

        return LoanContract(
            loan_id=self.loan_id,
            account_number=AccountNumber(self.account_number),
            loan_type=LoanType(self.loan_type),
            principal_amount=Money(self.principal_amount, currency=self.currency),
            interest_rate_apr=self.interest_rate_apr,
            term_months=self.term_months,
            monthly_installment=Money(self.monthly_installment, currency=self.currency),
            outstanding_balance=Money(self.outstanding_balance, currency=self.currency),
            total_interest=Money(self.total_interest, currency=self.currency),
            status=LoanStatus(self.status),
            originated_at=self.originated_at,
            next_due_date=self.next_due_date,
            schedule=entries,
            purpose=self.purpose,
        )

    @classmethod
    def from_entity(cls, entity: LoanContract) -> LoanContractModel:
        """Construct ORM model from pure Domain LoanContract entity."""
        schedule_data = [
            {
                "installment_number": item.installment_number,
                "due_date": item.due_date.isoformat(),
                "payment_amount": str(item.payment_amount.amount),
                "principal_amount": str(item.principal_amount.amount),
                "interest_amount": str(item.interest_amount.amount),
                "remaining_balance": str(item.remaining_balance.amount),
                "is_paid": item.is_paid,
                "paid_date": item.paid_date.isoformat() if item.paid_date else None,
            }
            for item in entity.schedule
        ]

        return cls(
            loan_id=entity.loan_id,
            account_number=entity.account_number.value,
            loan_type=entity.loan_type.value,
            principal_amount=entity.principal_amount.amount,
            interest_rate_apr=entity.interest_rate_apr,
            term_months=entity.term_months,
            monthly_installment=entity.monthly_installment.amount,
            outstanding_balance=entity.outstanding_balance.amount,
            total_interest=entity.total_interest.amount,
            currency=entity.principal_amount.currency,
            status=entity.status.value,
            purpose=entity.purpose,
            originated_at=entity.originated_at,
            next_due_date=entity.next_due_date,
            schedule_json=schedule_data,
        )


class TermDepositModel(Base):
    """Relational model for Certificates of Deposit (CD) and Term Deposit Vault contracts."""

    __tablename__ = "term_deposits"

    cd_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    account_number: Mapped[str] = mapped_column(
        String(12), ForeignKey("accounts.account_number"), nullable=False
    )
    principal_amount: Mapped[Decimal] = mapped_column(
        Numeric(15, 2, asdecimal=True), nullable=False
    )
    interest_rate_apy: Mapped[Decimal] = mapped_column(
        Numeric(5, 2, asdecimal=True), nullable=False
    )
    tenor_months: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    payout_frequency: Mapped[str] = mapped_column(String(20), default="AT_MATURITY", nullable=False)
    rollover_option: Mapped[str] = mapped_column(String(30), default="PAYOUT_AND_CLOSE", nullable=False)
    accrued_interest: Mapped[Decimal] = mapped_column(
        Numeric(15, 2, asdecimal=True), default=Decimal("0.00"), nullable=False
    )
    projected_interest_at_maturity: Mapped[Decimal] = mapped_column(
        Numeric(15, 2, asdecimal=True), default=Decimal("0.00"), nullable=False
    )
    early_withdrawal_penalty_months: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    early_withdrawal_penalty: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(15, 2, asdecimal=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", nullable=False)
    certificate_number: Mapped[str] = mapped_column(String(64), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    accruals_json: Mapped[Any] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        Index("idx_cd_account", "account_number"),
        Index("idx_cd_status", "status"),
        Index("idx_cd_maturity", "maturity_date"),
        Index("idx_cd_created", "created_at"),
    )

    def to_entity(self) -> CertificateOfDeposit:
        """Convert ORM model to pure Domain CertificateOfDeposit entity."""
        milestones: list[CDAccrualMilestone] = []
        if self.accruals_json and isinstance(self.accruals_json, list):
            for item in self.accruals_json:
                milestones.append(
                    CDAccrualMilestone(
                        milestone_index=int(item["milestone_index"]),
                        accrual_date=date.fromisoformat(item["accrual_date"])
                        if isinstance(item["accrual_date"], str)
                        else item["accrual_date"],
                        period_interest=Money(Decimal(str(item["period_interest"])), currency=self.currency),
                        cumulative_interest=Money(Decimal(str(item["cumulative_interest"])), currency=self.currency),
                        cumulative_balance=Money(Decimal(str(item["cumulative_balance"])), currency=self.currency),
                    )
                )

        return CertificateOfDeposit(
            cd_id=self.cd_id,
            account_number=AccountNumber(self.account_number),
            principal_amount=Money(self.principal_amount, currency=self.currency),
            interest_rate_apy=self.interest_rate_apy,
            tenor_months=self.tenor_months,
            issue_date=self.issue_date,
            maturity_date=self.maturity_date,
            payout_frequency=TermDepositPayoutFrequency(self.payout_frequency),
            rollover_option=TermDepositRolloverOption(self.rollover_option),
            accrued_interest=Money(self.accrued_interest, currency=self.currency),
            projected_interest_at_maturity=Money(self.projected_interest_at_maturity, currency=self.currency),
            early_withdrawal_penalty_months=self.early_withdrawal_penalty_months,
            status=TermDepositStatus(self.status),
            certificate_number=self.certificate_number,
            created_at=self.created_at,
            closed_at=self.closed_at,
            early_withdrawal_penalty=Money(self.early_withdrawal_penalty, currency=self.currency)
            if self.early_withdrawal_penalty is not None
            else None,
            accruals=milestones,
        )

    @classmethod
    def from_entity(cls, entity: CertificateOfDeposit) -> TermDepositModel:
        """Construct ORM model from pure Domain CertificateOfDeposit entity."""
        accruals_data = [
            {
                "milestone_index": item.milestone_index,
                "accrual_date": item.accrual_date.isoformat(),
                "period_interest": str(item.period_interest.amount),
                "cumulative_interest": str(item.cumulative_interest.amount),
                "cumulative_balance": str(item.cumulative_balance.amount),
            }
            for item in entity.accruals
        ]

        return cls(
            cd_id=entity.cd_id,
            account_number=entity.account_number.value,
            principal_amount=entity.principal_amount.amount,
            interest_rate_apy=entity.interest_rate_apy,
            tenor_months=entity.tenor_months,
            issue_date=entity.issue_date,
            maturity_date=entity.maturity_date,
            payout_frequency=entity.payout_frequency.value,
            rollover_option=entity.rollover_option.value,
            accrued_interest=entity.accrued_interest.amount,
            projected_interest_at_maturity=entity.projected_interest_at_maturity.amount,
            early_withdrawal_penalty_months=entity.early_withdrawal_penalty_months,
            early_withdrawal_penalty=entity.early_withdrawal_penalty.amount
            if entity.early_withdrawal_penalty is not None
            else None,
            status=entity.status.value,
            certificate_number=entity.certificate_number,
            currency=entity.principal_amount.currency,
            created_at=entity.created_at,
            closed_at=entity.closed_at,
            accruals_json=accruals_data,
        )



