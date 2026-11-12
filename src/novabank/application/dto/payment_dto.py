"""Data Transfer Objects for Payment Gateway and Merchant Settlements."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from novabank.domain.entities.payment import PaymentTransaction


@dataclass(frozen=True)
class PaymentRequestDTO:
    """Inbound request payload for executing a payment through gateway rails."""

    account_number: str
    channel: str
    amount: Decimal
    merchant_name: str = "NovaBank Merchant"
    customer_name: str = "Valued Customer"
    description: str = ""
    card_number: Optional[str] = None
    card_exp: Optional[str] = None
    card_cvv: Optional[str] = None
    card_zip: Optional[str] = None
    routing_number: Optional[str] = None
    idempotency_key: Optional[str] = None


@dataclass(frozen=True)
class PaymentTransactionDTO:
    """Read-only view representation of a gateway payment transaction."""

    payment_id: str
    account_number: str
    channel: str
    direction: str
    amount: Decimal
    fee: Decimal
    net_amount: Decimal
    status: str
    merchant_name: str
    customer_name: str
    idempotency_key: str
    card_brand: Optional[str]
    last4: Optional[str]
    description: str
    created_at: datetime
    settled_at: Optional[datetime]
    failure_reason: Optional[str]
    refund_reason: Optional[str]

    @property
    def formatted_amount(self) -> str:
        return f"${self.amount:,.2f}"

    @property
    def formatted_fee(self) -> str:
        return f"${self.fee:,.2f}"

    @property
    def formatted_net_amount(self) -> str:
        return f"${self.net_amount:,.2f}"

    @classmethod
    def from_entity(cls, entity: PaymentTransaction) -> PaymentTransactionDTO:
        return cls(
            payment_id=entity.payment_id,
            account_number=entity.account_number.value,
            channel=entity.channel.value,
            direction=entity.direction.value,
            amount=entity.amount.amount,
            fee=entity.fee.amount,
            net_amount=entity.net_amount.amount,
            status=entity.status.value,
            merchant_name=entity.merchant_name,
            customer_name=entity.customer_name,
            idempotency_key=entity.idempotency_key,
            card_brand=entity.card_brand,
            last4=entity.last4,
            description=entity.description,
            created_at=entity.created_at,
            settled_at=entity.settled_at,
            failure_reason=entity.failure_reason,
            refund_reason=entity.refund_reason,
        )


@dataclass(frozen=True)
class PaymentRefundResultDTO:
    """Result payload after issuing a full refund against a settled transaction."""

    payment_id: str
    account_number: str
    refunded_amount: Decimal
    refund_reason: str
    status: str
    timestamp: datetime
