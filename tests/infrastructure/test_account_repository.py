"""Tests for SQLAccountRepository."""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from novabank.domain.entities.account import Account
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.session import create_session_factory, init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository


@pytest.fixture
def session() -> Session:
    """Create in-memory SQLite database session for repository testing."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_database(engine)
    session_factory = create_session_factory(engine)
    with session_factory() as sess:
        yield sess
        sess.rollback()
    engine.dispose()


@pytest.fixture
def repo(session: Session) -> SQLAccountRepository:
    """Create a SQLAccountRepository instance bound to the test session."""
    return SQLAccountRepository(session)


def make_test_account(
    acc_no: str = "100000000001",
    name: str = "Alice Walker",
    balance: str = "100.00",
    is_active: bool = True,
    city: str = "Boston",
    phone: str = "1234567890",
) -> Account:
    """Helper factory for valid Account entities."""
    return Account(
        account_number=AccountNumber(acc_no),
        holder_name=name,
        dob=date(1992, 4, 10),
        address_line="10 Beacon St",
        city=city,
        state="MA",
        country="USA",
        phone_number=phone,
        is_active=is_active,
        balance=Money(balance),
    )


def test_save_and_get_by_number(repo: SQLAccountRepository, session: Session):
    """Verify saving a new account and retrieving it."""
    account = make_test_account()
    repo.save(account)
    session.commit()

    retrieved = repo.get_by_number("100000000001")
    assert retrieved is not None
    assert retrieved.account_number.value == "100000000001"
    assert retrieved.holder_name == "Alice Walker"
    assert retrieved.balance == Money("100.00")

    # Retrieve with AccountNumber value object
    retrieved_vo = repo.get_by_number(AccountNumber("100000000001"))
    assert retrieved_vo == retrieved

    # Retrieve non-existent
    assert repo.get_by_number("999999999999") is None


def test_update_existing_account(repo: SQLAccountRepository, session: Session):
    """Verify saving an updated account synchronizes changes."""
    account = make_test_account(balance="100.00")
    repo.save(account)
    session.commit()

    # Credit account and update contact details
    account.credit(Money("50.00"), description="Deposit")
    account.update_profile(
        address_line="20 Commonwealth Ave",
        city="Cambridge",
        state="MA",
        country="USA",
        phone_number="9876543210",
    )
    repo.save(account)
    session.commit()

    updated = repo.get_by_number("100000000001")
    assert updated is not None
    assert updated.balance == Money("150.00")
    assert updated.address_line == "20 Commonwealth Ave"
    assert updated.city == "Cambridge"
    assert updated.phone_number == "9876543210"
    assert updated.version == 3


def test_get_by_number_for_update(repo: SQLAccountRepository, session: Session):
    """Verify row locking query executes and retrieves entity."""
    account = make_test_account("200000000002", "Bob Vance")
    repo.save(account)
    session.commit()

    locked = repo.get_by_number_for_update("200000000002")
    assert locked is not None
    assert locked.account_number.value == "200000000002"
    assert locked.holder_name == "Bob Vance"
    assert repo.get_by_number_for_update("999999999999") is None


def test_exists(repo: SQLAccountRepository, session: Session):
    """Verify exists returns True for present accounts and False otherwise."""
    account = make_test_account("300000000003")
    repo.save(account)
    session.commit()

    assert repo.exists("300000000003") is True
    assert repo.exists(AccountNumber("300000000003")) is True
    assert repo.exists("000000000001") is False


def test_list_and_count_accounts_search_and_pagination(
    repo: SQLAccountRepository, session: Session
):
    """Verify filtering by active status, search terms, and pagination."""
    acc1 = make_test_account(
        "400000000001", "Charlie Brown", city="Detroit", phone="1112223334", is_active=True
    )
    acc2 = make_test_account(
        "400000000002", "David Miller", city="Denver", phone="2223334445", is_active=True
    )
    acc3 = make_test_account(
        "400000000003", "Eve Adams", city="Dallas", phone="3334445556", is_active=False
    )

    repo.save(acc1)
    repo.save(acc2)
    repo.save(acc3)
    session.commit()

    # Total count
    assert repo.count_accounts() == 3
    assert repo.count_accounts(active_only=True) == 2
    assert repo.count_accounts(search="David") == 1
    assert repo.count_accounts(search="   ") == 3

    # Search by name
    results = repo.list_accounts(search="David")
    assert len(results) == 1
    assert results[0].holder_name == "David Miller"

    # Search by city
    results = repo.list_accounts(search="Dallas")
    assert len(results) == 1
    assert results[0].holder_name == "Eve Adams"

    # Search by phone
    results = repo.list_accounts(search="111222")
    assert len(results) == 1
    assert results[0].holder_name == "Charlie Brown"

    # Search by account number substring
    results = repo.list_accounts(search="40000000000")
    assert len(results) == 3

    # Active only list
    active_results = repo.list_accounts(active_only=True)
    assert len(active_results) == 2
    assert all(a.is_active for a in active_results)

    # Pagination: limit and offset
    page1 = repo.list_accounts(limit=2, offset=0)
    assert len(page1) == 2
    page2 = repo.list_accounts(limit=2, offset=2)
    assert len(page2) == 1


def test_account_equality_and_hashing():
    """Verify Account entity equality and hashing based on account number."""
    acc1 = make_test_account("500000000001")
    acc2 = make_test_account("500000000001")
    acc3 = make_test_account("500000000002")

    assert acc1 == acc2
    assert acc1 != acc3
    assert acc1 != "not_an_account"
    assert hash(acc1) == hash(acc2)
