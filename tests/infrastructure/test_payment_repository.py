"""Tests for SQLPaymentRepository."""

from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from novabank.domain.entities.account import Account
from novabank.domain.entities.payment import (
    PaymentChannel,
    PaymentDirection,
    PaymentStatus,
    PaymentTransaction,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.session import create_session_factory, init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_payment_repository import SQLPaymentRepository


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as sess:
        yield sess
        sess.rollback()
    engine.dispose()


def test_payment_repository_crud_and_queries(session: Session):
    acc_repo = SQLAccountRepository(session)
    pay_repo = SQLPaymentRepository(session)

    account = Account(
        account_number=AccountNumber("111122223333"),
        holder_name="Merchant LLC",
        dob=date(1980, 1, 1),
        address_line="100 Commerce Way",
        city="Seattle",
        state="WA",
        country="USA",
        phone_number="5551234567",
        balance=Money("5000.00"),
    )
    acc_repo.save(account)
    session.flush()

    payment = PaymentTransaction(
        payment_id="PAY-TEST-001",
        account_number=account.account_number,
        channel=PaymentChannel.CARD,
        amount=Money("250.00"),
        fee=Money("7.55"),
        merchant_name="Merchant LLC",
        customer_name="Alice Customer",
        idempotency_key="IDEMP-001",
        card_brand="VISA",
        last4="4242",
        status=PaymentStatus.SETTLED,
    )
    pay_repo.save(payment)

    # 1. Fetch by id
    fetched = pay_repo.get_by_id("PAY-TEST-001")
    assert fetched is not None
    assert fetched.amount == Money("250.00")
    assert fetched.fee == Money("7.55")
    assert fetched.net_amount == Money("242.45")
    assert fetched.card_brand == "VISA"
    assert fetched.status == PaymentStatus.SETTLED

    # 2. Fetch by idempotency key
    by_key = pay_repo.get_by_idempotency_key("IDEMP-001")
    assert by_key is not None
    assert by_key.payment_id == "PAY-TEST-001"

    # 3. List and count
    payments, count = pay_repo.list_payments(account_number="111122223333")
    assert count == 1
    assert len(payments) == 1
    assert payments[0].customer_name == "Alice Customer"

    # 4. Mutation and refund save
    fetched.refund("Damaged goods")
    pay_repo.save(fetched)

    refetched = pay_repo.get_by_id("PAY-TEST-001")
    assert refetched.status == PaymentStatus.REFUNDED
    assert refetched.refund_reason == "Damaged goods"

