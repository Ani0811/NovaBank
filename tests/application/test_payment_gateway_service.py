"""Application-layer tests for BankingService Payment Gateway workflows."""

import os
import tempfile
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from novabank.application.dto.payment_dto import PaymentRequestDTO
from novabank.application.events import (
    PaymentDeclinedEvent,
    PaymentProcessedEvent,
    PaymentRefundedEvent,
)
from novabank.application.services.audit_service import AuditService
from novabank.application.services.banking_service import BankingService
from novabank.domain.entities.account import Account
from novabank.domain.entities.payment import PaymentChannel, PaymentStatus
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    AccountNotFoundError,
    InsufficientFundsError,
    InvalidAmountError,
    PaymentDeclinedError,
    PaymentRefundError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.session import init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_payment_repository import SQLPaymentRepository


@pytest.fixture
def db_setup():
    """Create a temporary SQLite database for clean multi-threaded testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    engine = create_engine(
        f"sqlite:///{db_path}?timeout=30",
        pool_size=10,
        max_overflow=20,
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
    init_database(engine)
    session_factory = sessionmaker(bind=engine)

    yield session_factory, engine

    engine.dispose()
    try:
        os.remove(db_path)
        for ext in ["-wal", "-shm"]:
            f = db_path + ext
            if os.path.exists(f):
                os.remove(f)
    except OSError:
        pass


@pytest.fixture
def banking_service(db_setup):
    session_factory, _ = db_setup
    audit_service = AuditService(session_factory)
    service = BankingService(session_factory)
    service.subscribe(audit_service.handle_event)
    return service


@pytest.fixture
def seed_account(db_setup):
    session_factory, _ = db_setup
    with session_factory() as session:
        with session.begin():
            account = Account(
                account_number=AccountNumber("100012345678"),
                holder_name="Acme Corporation",
                dob=date(1985, 5, 20),
                address_line="100 Enterprise Way",
                city="San Francisco",
                state="CA",
                country="USA",
                phone_number="4155551234",
                is_active=True,
                balance=Money(Decimal("1000.00")),
            )
            SQLAccountRepository(session).save(account)
    return "100012345678"


def test_process_card_payment_success(banking_service, seed_account):
    events = []
    banking_service.subscribe(lambda e: events.append(e))

    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="CARD",
        amount=Decimal("100.00"),
        merchant_name="Acme Corp Store",
        customer_name="Alice Smith",
        card_number="4242424242424242",
        card_exp="12/28",
        card_cvv="123",
        description="Online order #9921",
    )

    result = banking_service.process_gateway_payment(req, actor="gateway_user")

    assert result.payment_id.startswith("PAY-")
    assert result.status == "SETTLED"
    assert result.amount == Decimal("100.00")
    # Card interchange: 2.9% + $0.30 = $2.90 + $0.30 = $3.20
    assert result.fee == Decimal("3.20")
    assert result.net_amount == Decimal("96.80")
    assert result.card_brand == "VISA"
    assert result.last4 == "4242"

    # Verify ledger credit
    acc = banking_service.get_account(seed_account)
    # $1000 + $96.80 net = $1096.80
    assert acc.balance == Decimal("1096.80")

    # Verify event
    proc_events = [e for e in events if isinstance(e, PaymentProcessedEvent)]
    assert len(proc_events) == 1
    assert proc_events[0].amount == Decimal("100.00")
    assert proc_events[0].fee == Decimal("3.20")
    assert proc_events[0].net_amount == Decimal("96.80")


def test_process_ach_payment_success(banking_service, seed_account):
    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="ACH",
        amount=Decimal("250.00"),
        merchant_name="Acme B2B Services",
        customer_name="Bob Jones",
        routing_number="121000358",
        description="Invoice #440",
    )

    result = banking_service.process_gateway_payment(req)
    assert result.status == "SETTLED"
    assert result.channel == "ACH"
    # ACH fee: 0.8% of $250 = $2.00
    assert result.fee == Decimal("2.00")
    assert result.net_amount == Decimal("248.00")

    acc = banking_service.get_account(seed_account)
    assert acc.balance == Decimal("1248.00")


def test_process_payment_decline_handling(banking_service, seed_account):
    events = []
    banking_service.subscribe(lambda e: events.append(e))

    # Card ending 0002 triggers INSUFFICIENT_FUNDS decline in rails simulator
    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="CARD",
        amount=Decimal("150.00"),
        merchant_name="Acme Shop",
        card_number="4000000000000002",
        card_exp="10/29",
        card_cvv="999",
    )

    with pytest.raises(PaymentDeclinedError) as exc_info:
        banking_service.process_gateway_payment(req)

    assert "Insufficient funds in card account" in str(exc_info.value)

    # Balance remains unchanged
    acc = banking_service.get_account(seed_account)
    assert acc.balance == Decimal("1000.00")

    # PaymentDeclinedEvent emitted
    decline_events = [e for e in events if isinstance(e, PaymentDeclinedEvent)]
    assert len(decline_events) == 1
    assert decline_events[0].amount == Decimal("150.00")

    # Decline is persisted in database
    payments, count = banking_service.list_gateway_payments(status="DECLINED")
    assert count >= 1
    assert any(p.failure_reason and "Insufficient funds" in p.failure_reason for p in payments)


def test_process_payment_idempotency(banking_service, seed_account):
    key = "UNIQUE-IDEMP-KEY-999"
    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="FEDNOW",
        amount=Decimal("50.00"),
        merchant_name="Instant Settlement Corp",
        idempotency_key=key,
    )

    first = banking_service.process_gateway_payment(req)
    assert first.status == "SETTLED"

    acc_first = banking_service.get_account(seed_account)

    # Resubmission returns existing settled record without duplicate credit
    second = banking_service.process_gateway_payment(req)
    assert second.payment_id == first.payment_id

    acc_second = banking_service.get_account(seed_account)
    assert acc_first.balance == acc_second.balance


def test_process_payment_account_validation(banking_service, seed_account):
    # Non-existent account
    req_bad_acc = PaymentRequestDTO(
        account_number="999999999999",
        channel="CARD",
        amount=Decimal("50.00"),
        merchant_name="Test",
    )
    with pytest.raises(AccountNotFoundError):
        banking_service.process_gateway_payment(req_bad_acc)

    # Negative / Zero amount
    req_bad_amt = PaymentRequestDTO(
        account_number=seed_account,
        channel="CARD",
        amount=Decimal("-10.00"),
        merchant_name="Test",
    )
    with pytest.raises(InvalidAmountError):
        banking_service.process_gateway_payment(req_bad_amt)


def test_process_payment_closed_or_frozen_account(banking_service, seed_account):
    banking_service.freeze_account(seed_account, reason="Compliance Audit")

    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="CARD",
        amount=Decimal("50.00"),
        merchant_name="Test Merchant",
    )
    with pytest.raises(AccountFrozenError):
        banking_service.process_gateway_payment(req)

    banking_service.unfreeze_account(seed_account)
    banking_service.withdraw(account_number=seed_account, amount=Decimal("1000.00"), description="Zero balance")
    banking_service.close_account(seed_account)

    with pytest.raises(AccountClosedError):
        banking_service.process_gateway_payment(req)


def test_refund_gateway_payment_success(banking_service, seed_account):
    events = []
    banking_service.subscribe(lambda e: events.append(e))

    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="CARD",
        amount=Decimal("100.00"),
        merchant_name="Acme Retail",
        card_number="4242424242424242",
        card_exp="11/27",
        card_cvv="555",
    )

    settled = banking_service.process_gateway_payment(req)
    # Balance before refund: $1000 + $96.80 = $1096.80
    assert banking_service.get_account(seed_account).balance == Decimal("1096.80")

    refund_result = banking_service.refund_gateway_payment(
        payment_id=settled.payment_id,
        reason="Defective merchandise return",
        actor="lead_teller",
    )

    assert refund_result.status == "REFUNDED"
    assert refund_result.refunded_amount == Decimal("96.80")

    # Balance after reversal: $1000.00
    assert banking_service.get_account(seed_account).balance == Decimal("1000.00")

    # Re-reading payment transaction reflects REFUNDED
    updated_pay = banking_service.get_gateway_payment(settled.payment_id)
    assert updated_pay.status == "REFUNDED"
    assert updated_pay.refund_reason == "Defective merchandise return"

    # Event emitted
    refund_events = [e for e in events if isinstance(e, PaymentRefundedEvent)]
    assert len(refund_events) == 1
    assert refund_events[0].refund_amount == Decimal("96.80")


def test_refund_already_refunded_fails(banking_service, seed_account):
    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="CARD",
        amount=Decimal("50.00"),
        merchant_name="Store",
        card_number="4242424242424242",
        card_exp="11/27",
        card_cvv="555",
    )
    settled = banking_service.process_gateway_payment(req)
    banking_service.refund_gateway_payment(settled.payment_id, reason="First refund")

    with pytest.raises(PaymentRefundError) as exc_info:
        banking_service.refund_gateway_payment(settled.payment_id, reason="Second refund")
    assert "Only settled payments can be refunded" in str(exc_info.value)


def test_export_payments_csv(banking_service, seed_account):
    req = PaymentRequestDTO(
        account_number=seed_account,
        channel="CARD",
        amount=Decimal("150.00"),
        merchant_name="CSV Store",
        card_number="4242424242424242",
        card_exp="11/27",
        card_cvv="555",
    )
    banking_service.process_gateway_payment(req)

    payments, _ = banking_service.list_gateway_payments(account_number=seed_account)
    csv_text = banking_service.export_payments_csv(payments)

    assert "Payment ID,Date,Account,Channel,Merchant" in csv_text
    assert "CSV Store" in csv_text
    assert "150.00" in csv_text
