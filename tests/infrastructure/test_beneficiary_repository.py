"""Tests for SQLBeneficiaryRepository."""

from datetime import date
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from novabank.domain.entities.account import Account
from novabank.domain.entities.beneficiary import Beneficiary
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.session import create_session_factory, init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_beneficiary_repository import SQLBeneficiaryRepository


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


def test_beneficiary_save_list_get_and_delete(session: Session):
    acc_repo = SQLAccountRepository(session)
    ben_repo = SQLBeneficiaryRepository(session)

    # 1. Create source and destination accounts
    src_acc = Account(
        account_number=AccountNumber("100000000001"),
        holder_name="Alice Smith",
        dob=date(1985, 1, 1),
        address_line="123 Main St",
        city="New York",
        state="NY",
        country="USA",
        phone_number="5551234567",
        balance=Money("5000.00"),
    )
    dest_acc = Account(
        account_number=AccountNumber("100000000002"),
        holder_name="Bob Jones",
        dob=date(1990, 5, 15),
        address_line="456 Elm St",
        city="Boston",
        state="MA",
        country="USA",
        phone_number="5559876543",
        balance=Money("1000.00"),
    )
    acc_repo.save(src_acc)
    acc_repo.save(dest_acc)
    session.flush()

    # 2. Save beneficiary
    ben = Beneficiary(
        source_account_number=src_acc.account_number,
        destination_account_number=dest_acc.account_number,
        destination_holder_name=dest_acc.holder_name,
        nickname="Bob Consulting",
    )
    ben_repo.save(ben)
    assert ben.beneficiary_id is not None

    # 3. Get by id
    fetched = ben_repo.get_by_id(ben.beneficiary_id)
    assert fetched is not None
    assert fetched.nickname == "Bob Consulting"
    assert fetched.destination_holder_name == "Bob Jones"

    # 4. Get by source and dest
    by_pair = ben_repo.get_by_source_and_dest("100000000001", "100000000002")
    assert by_pair is not None
    assert by_pair.nickname == "Bob Consulting"

    # 5. List by source
    listing = ben_repo.list_by_source("100000000001")
    assert len(listing) == 1
    assert listing[0].nickname == "Bob Consulting"

    # 6. Delete
    deleted = ben_repo.delete(ben.beneficiary_id)
    assert deleted is True
    assert ben_repo.get_by_id(ben.beneficiary_id) is None
    assert ben_repo.delete(999999) is False
