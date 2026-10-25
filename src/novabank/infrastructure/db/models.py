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
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from novabank.domain.entities.account import Account
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
