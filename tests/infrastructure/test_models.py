"""Tests for SQLAlchemy ORM models, constraints, and entity mappers."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from novabank.domain.entities.account import Account
from novabank.domain.entities.transaction import Transaction
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType
from novabank.infrastructure.db.models import AccountModel, AuditEventModel, TransactionModel
from novabank.infrastructure.db.session import create_session_factory, init_database


@pytest.fixture
def session() -> Session:
    """Create in-memory SQLite database session for unit testing models."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as sess:
        yield sess
        sess.rollback()
    engine.dispose()


def test_account_model_crud_and_to_entity(session: Session):
    """Verify AccountModel creation, persistence, and conversion to Domain entity."""
    account_entity = Account(
        account_number=AccountNumber("111222333444"),
        holder_name="Bob Smith",
        dob=date(1990, 8, 15),
        address_line="789 Pine Rd",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5551234567",
        balance=Money("250.00"),
    )

    # Convert to ORM model and persist
    account_model = AccountModel.from_entity(account_entity)
    session.add(account_model)
    session.commit()

    # Query back
    retrieved = session.get(AccountModel, "111222333444")
    assert retrieved is not None
    assert retrieved.holder_name == "Bob Smith"
    assert retrieved.balance == Decimal("250.00")
    assert retrieved.version == 1

    # Convert back to domain entity
    reconstructed = retrieved.to_entity()
    assert reconstructed.account_number.value == "111222333444"
    assert reconstructed.holder_name == "Bob Smith"
    assert reconstructed.balance == Money("250.00")


def test_account_model_update_from_entity(session: Session):
    """Verify synchronizing entity updates into ORM model."""
    account_entity = Account(
        account_number=AccountNumber("111222333444"),
        holder_name="Bob Smith",
        dob=date(1990, 8, 15),
        address_line="789 Pine Rd",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5551234567",
        balance=Money("250.00"),
    )
    account_model = AccountModel.from_entity(account_entity)
    session.add(account_model)
    session.commit()

    # Domain operation on entity
    account_entity.credit(Money("50.00"), description="Deposit")
    account_entity.update_profile(
        address_line="100 Lake Shore Dr",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5559876543",
    )

    # Sync back to model
    account_model.update_from_entity(account_entity)
    session.commit()

    reloaded = session.get(AccountModel, "111222333444")
    assert reloaded.balance == Decimal("300.00")
    assert reloaded.address_line == "100 Lake Shore Dr"
    assert reloaded.phone_number == "5559876543"
    assert reloaded.version == 3


def test_transaction_model_crud_and_to_entity(session: Session):
    """Verify TransactionModel persistence and conversion to Domain entity."""
    # Create parent account
    account_model = AccountModel(
        account_number="999888777666",
        holder_name="Carol Danvers",
        dob=date(1985, 3, 10),
        address_line="1 Avengers Blvd",
        city="New York",
        state="NY",
        country="USA",
        phone_number="2125550199",
        balance=Decimal("500.00"),
    )
    session.add(account_model)
    session.commit()

    tx_entity = Transaction(
        account_number=AccountNumber("999888777666"),
        transaction_type=TransactionType.DEPOSIT,
        direction=TransactionDirection.CREDIT,
        amount=Money("100.00"),
        balance_after=Money("500.00"),
        description="Cash Counter Deposit",
        transaction_ref="tx-ref-unique-001",
        created_by="teller_1",
    )

    tx_model = TransactionModel.from_entity(tx_entity)
    session.add(tx_model)
    session.commit()

    # Query back
    retrieved_tx = (
        session.query(TransactionModel).filter_by(transaction_ref="tx-ref-unique-001").one()
    )
    assert retrieved_tx.transaction_id is not None
    assert retrieved_tx.amount == Decimal("100.00")
    assert retrieved_tx.created_by == "teller_1"

    # Convert to domain entity
    reconstructed_tx = retrieved_tx.to_entity()
    assert reconstructed_tx.transaction_ref == "tx-ref-unique-001"
    assert reconstructed_tx.amount == Money("100.00")
    assert reconstructed_tx.direction == TransactionDirection.CREDIT


def test_transaction_ref_uniqueness_constraint(session: Session):
    """Verify unique constraint on transaction_ref raises IntegrityError."""
    account_model = AccountModel(
        account_number="999888777666",
        holder_name="Carol Danvers",
        dob=date(1985, 3, 10),
        address_line="1 Avengers Blvd",
        city="New York",
        state="NY",
        country="USA",
        phone_number="2125550199",
        balance=Decimal("500.00"),
    )
    session.add(account_model)
    session.commit()

    tx1 = TransactionModel(
        transaction_ref="duplicate-ref-123",
        account_number="999888777666",
        transaction_type=TransactionType.DEPOSIT.value,
        direction=TransactionDirection.CREDIT.value,
        amount=Decimal("50.00"),
        balance_after=Decimal("550.00"),
    )
    session.add(tx1)
    session.commit()

    tx2 = TransactionModel(
        transaction_ref="duplicate-ref-123",  # Duplicate ref
        account_number="999888777666",
        transaction_type=TransactionType.DEPOSIT.value,
        direction=TransactionDirection.CREDIT.value,
        amount=Decimal("25.00"),
        balance_after=Decimal("575.00"),
    )
    session.add(tx2)
    with pytest.raises(IntegrityError):
        session.commit()


def test_audit_event_model(session: Session):
    """Verify AuditEventModel persistence and JSON payload retrieval."""
    event = AuditEventModel(
        event_type="ACCOUNT_CREATED",
        entity_type="account",
        entity_id="123456789012",
        actor="teller_admin",
        payload={"initial_balance": "0.00", "branch": "Main"},
    )
    session.add(event)
    session.commit()

    retrieved = session.get(AuditEventModel, event.event_id)
    assert retrieved is not None
    assert retrieved.actor == "teller_admin"
    assert retrieved.payload["initial_balance"] == "0.00"


def test_session_creation_helpers():
    """Verify session and engine factories for SQLite and MySQL configs."""
    from novabank.infrastructure.config import AppConfig
    from novabank.infrastructure.db.session import create_db_engine

    # Test custom SQLite URL
    sqlite_engine = create_db_engine(custom_url="sqlite:///:memory:")
    assert "sqlite" in str(sqlite_engine.url)
    sqlite_engine.dispose()

    # Test MySQL config engine
    mysql_config = AppConfig(db_host="localhost", db_user="test_user")
    mysql_engine = create_db_engine(config=mysql_config)
    assert "mysql" in str(mysql_engine.url)
    mysql_engine.dispose()
