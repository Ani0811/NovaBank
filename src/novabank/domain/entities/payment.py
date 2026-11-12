"""Payment Gateway and Merchant Settlement Domain Entity."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
import uuid

from novabank.domain.exceptions import (
    DomainError,
    InvalidAmountError,
    PaymentAlreadySettledError,
    PaymentGatewayError,
    PaymentRefundError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money


class PaymentChannel(str, Enum):
    """Payment rails and ingestion channels."""

    CARD = "CARD"
    ACH = "ACH"
    FEDNOW = "FEDNOW"
    WIRE = "WIRE"


class PaymentStatus(str, Enum):
    """Payment lifecycle and settlement states."""

    AUTHORIZED = "AUTHORIZED"
    SETTLED = "SETTLED"
    DECLINED = "DECLINED"
    REFUNDED = "REFUNDED"


class PaymentDirection(str, Enum):
    """Direction of money relative to the bank."""

    INBOUND = "INBOUND"    # External customer/merchant -> Bank (Deposit/Charge)
    OUTBOUND = "OUTBOUND"  # Bank -> External receiver (Payout/Push)


class PaymentTransaction:
    """Domain entity representing a payment gateway transaction processed across financial rails."""

    def __init__(
        self,
        account_number: AccountNumber,
        channel: PaymentChannel,
        amount: Money,
        fee: Money,
        merchant_name: str,
        customer_name: str,
        idempotency_key: str,
        direction: PaymentDirection = PaymentDirection.INBOUND,
        payment_id: Optional[str] = None,
        card_brand: Optional[str] = None,
        last4: Optional[str] = None,
        status: PaymentStatus = PaymentStatus.AUTHORIZED,
        description: str = "",
        created_at: Optional[datetime] = None,
        settled_at: Optional[datetime] = None,
        failure_reason: Optional[str] = None,
        refund_reason: Optional[str] = None,
    ) -> None:
        if not amount.is_positive():
            raise InvalidAmountError(f"Payment amount must be strictly positive, got: {amount}")

        if fee.is_negative():
            raise DomainError(f"Gateway fee cannot be negative, got: {fee}")

        if fee.currency != amount.currency:
            raise DomainError(
                f"Fee currency {fee.currency} does not match amount currency {amount.currency}"
            )

        self.payment_id = payment_id or f"PAY-{uuid.uuid4().hex[:12].upper()}"
        self.account_number = account_number
        self.channel = channel
        self.direction = direction
        self.amount = amount
        self.fee = fee
        self.status = status
        self.merchant_name = self._validate_name(merchant_name, "Merchant name")
        self.customer_name = self._validate_name(customer_name, "Customer name")
        self.idempotency_key = self._validate_key(idempotency_key)
        self.card_brand = card_brand.strip().upper() if card_brand else None
        self.last4 = self._validate_last4(last4) if last4 else None
        self.description = description.strip() or f"{self.channel.value} Payment Settlement"
        self.created_at = created_at or datetime.now(timezone.utc)
        self.settled_at = settled_at
        self.failure_reason = failure_reason
        self.refund_reason = refund_reason

    @property
    def net_amount(self) -> Money:
        """Calculate net settlement amount after interchange and gateway fees."""
        if self.direction == PaymentDirection.INBOUND:
            # Customer charged gross, bank/merchant receives gross - fee
            return self.amount - self.fee
        else:
            # Outbound payout pays gross + fee
            return self.amount + self.fee

    @staticmethod
    def _validate_name(name: str, field_name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise DomainError(f"{field_name} cannot be empty.")
        clean = name.strip()
        if len(clean) > 100:
            raise DomainError(f"{field_name} cannot exceed 100 characters.")
        return clean

    @staticmethod
    def _validate_key(key: str) -> str:
        if not isinstance(key, str) or not key.strip():
            raise DomainError("Payment idempotency key cannot be empty.")
        return key.strip()

    @staticmethod
    def _validate_last4(last4: str) -> str:
        clean = str(last4).strip()
        if not re.fullmatch(r"\d{4}", clean):
            raise DomainError(f"Last 4 digits must be exactly 4 digits, got: '{last4}'")
        return clean

    def settle(self) -> None:
        """Mark payment as captured and settled to the core ledger."""
        if self.status == PaymentStatus.SETTLED:
            raise PaymentAlreadySettledError(f"Payment {self.payment_id} is already settled.")
        if self.status in (PaymentStatus.DECLINED, PaymentStatus.REFUNDED):
            raise PaymentGatewayError(
                f"Cannot settle payment in terminal status: {self.status.value}"
            )

        self.status = PaymentStatus.SETTLED
        self.settled_at = datetime.now(timezone.utc)

    def decline(self, reason: str) -> None:
        """Record payment decline and reason."""
        if self.status == PaymentStatus.SETTLED:
            raise PaymentGatewayError("Cannot decline an already settled payment.")
        self.status = PaymentStatus.DECLINED
        self.failure_reason = reason.strip() or "Gateway transaction declined"

    def refund(self, reason: str) -> None:
        """Issue full refund against an established settled transaction."""
        if self.status != PaymentStatus.SETTLED:
            raise PaymentRefundError(
                f"Only settled payments can be refunded. Current status is {self.status.value}."
            )
        self.status = PaymentStatus.REFUNDED
        self.refund_reason = reason.strip() or "Customer refund requested"

    def __repr__(self) -> str:
        return (
            f"PaymentTransaction(id='{self.payment_id}', channel={self.channel.value}, "
            f"amount={self.amount}, status={self.status.value}, account={self.account_number.value})"
        )

