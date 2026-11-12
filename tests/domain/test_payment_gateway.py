"""Domain tests for PaymentTransaction entity and PaymentRailsSimulator."""

from decimal import Decimal
import pytest

from novabank.domain.entities.payment import (
    PaymentChannel,
    PaymentDirection,
    PaymentStatus,
    PaymentTransaction,
)
from novabank.domain.exceptions import (
    DomainError,
    InvalidAmountError,
    PaymentAlreadySettledError,
    PaymentGatewayError,
    PaymentRefundError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.gateways.payment_rails_simulator import PaymentRailsSimulator


def test_payment_transaction_creation_and_net_calculation():
    acc = AccountNumber("123456789012")
    gross = Money("500.00")
    fee = Money("14.80")

    payment = PaymentTransaction(
        account_number=acc,
        channel=PaymentChannel.CARD,
        direction=PaymentDirection.INBOUND,
        amount=gross,
        fee=fee,
        merchant_name="Acme Retailers",
        customer_name="John Customer",
        idempotency_key="KEY-12345",
        card_brand="VISA",
        last4="4242",
    )

    assert payment.payment_id.startswith("PAY-")
    assert payment.amount == gross
    assert payment.fee == fee
    assert payment.net_amount == Money("485.20")
    assert payment.status == PaymentStatus.AUTHORIZED
    assert payment.card_brand == "VISA"
    assert payment.last4 == "4242"


def test_payment_outbound_net_calculation():
    acc = AccountNumber("123456789012")
    gross = Money("200.00")
    fee = Money("0.25")

    payment = PaymentTransaction(
        account_number=acc,
        channel=PaymentChannel.FEDNOW,
        direction=PaymentDirection.OUTBOUND,
        amount=gross,
        fee=fee,
        merchant_name="Vendor Payout",
        customer_name="Contractor Corp",
        idempotency_key="KEY-9999",
    )
    # Outbound payout net = 200 + 0.25 = $200.25
    assert payment.net_amount == Money("200.25")


def test_payment_invalid_amount_or_fee():
    acc = AccountNumber("123456789012")
    with pytest.raises(InvalidAmountError):
        PaymentTransaction(
            account_number=acc,
            channel=PaymentChannel.CARD,
            amount=Money("0.00"),
            fee=Money("0.00"),
            merchant_name="Store",
            customer_name="Buyer",
            idempotency_key="KEY-1",
        )

    with pytest.raises(DomainError, match="cannot be negative"):
        PaymentTransaction(
            account_number=acc,
            channel=PaymentChannel.CARD,
            amount=Money("100.00"),
            fee=Money("-5.00", allow_negative=True),
            merchant_name="Store",
            customer_name="Buyer",
            idempotency_key="KEY-2",
        )


def test_payment_state_machine_transitions():
    acc = AccountNumber("123456789012")
    payment = PaymentTransaction(
        account_number=acc,
        channel=PaymentChannel.CARD,
        amount=Money("100.00"),
        fee=Money("3.20"),
        merchant_name="Store",
        customer_name="Buyer",
        idempotency_key="KEY-3",
    )

    # 1. Settle
    payment.settle()
    assert payment.status == PaymentStatus.SETTLED
    assert payment.settled_at is not None

    # Double settle rejected
    with pytest.raises(PaymentAlreadySettledError):
        payment.settle()

    # 2. Refund
    payment.refund("Customer returned merchandise")
    assert payment.status == PaymentStatus.REFUNDED
    assert payment.refund_reason == "Customer returned merchandise"


def test_payment_refund_rejected_when_not_settled():
    acc = AccountNumber("123456789012")
    payment = PaymentTransaction(
        account_number=acc,
        channel=PaymentChannel.CARD,
        amount=Money("100.00"),
        fee=Money("3.20"),
        merchant_name="Store",
        customer_name="Buyer",
        idempotency_key="KEY-4",
        status=PaymentStatus.AUTHORIZED,
    )
    with pytest.raises(PaymentRefundError):
        payment.refund("Try to refund before settlement")


def test_rails_simulator_luhn_algorithm():
    # Valid Visa card numbers passing Luhn
    assert PaymentRailsSimulator.validate_luhn("4242424242424242") is True
    assert PaymentRailsSimulator.validate_luhn("4000001234567899") is True
    # Invalid card number failing Luhn
    assert PaymentRailsSimulator.validate_luhn("4242424242424243") is False
    assert PaymentRailsSimulator.validate_luhn("123") is False


def test_rails_simulator_brand_detection():
    assert PaymentRailsSimulator.detect_card_brand("4111111111111111") == "VISA"
    assert PaymentRailsSimulator.detect_card_brand("5500000000000004") == "MASTERCARD"
    assert PaymentRailsSimulator.detect_card_brand("378282246310005") == "AMEX"
    assert PaymentRailsSimulator.detect_card_brand("6011000000000000") == "DISCOVER"


def test_rails_simulator_interchange_fees():
    amt = Money("1000.00")
    # Card: 2.9% + $0.30 = $29.00 + $0.30 = $29.30
    assert (
        PaymentRailsSimulator.calculate_interchange_fee(PaymentChannel.CARD, amt).amount
        == Decimal("29.30")
    )
    # ACH: 0.8% capped at $5.00 -> 0.008 * 1000 = $8.00 -> capped at $5.00
    assert (
        PaymentRailsSimulator.calculate_interchange_fee(PaymentChannel.ACH, amt).amount
        == Decimal("5.00")
    )
    # FedNow: flat $0.25
    assert (
        PaymentRailsSimulator.calculate_interchange_fee(PaymentChannel.FEDNOW, amt).amount
        == Decimal("0.25")
    )
    # Wire: flat $15.00
    assert (
        PaymentRailsSimulator.calculate_interchange_fee(PaymentChannel.WIRE, amt).amount
        == Decimal("15.00")
    )

