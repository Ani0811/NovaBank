"""Tests for BankingService beneficiary address book workflows."""

from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine

from novabank.application.services.banking_service import BankingService
from novabank.domain.exceptions import AccountNotFoundError, SelfTransferError
from novabank.infrastructure.db.session import create_session_factory, init_database


@pytest.fixture
def banking_service() -> BankingService:
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_database(engine)
    factory = create_session_factory(engine)
    service = BankingService(factory)
    return service


def test_add_and_list_beneficiaries(banking_service: BankingService):
    acc1 = banking_service.open_account(
        holder_name="Alice Smith",
        dob=date(1990, 1, 1),
        address_line="123 Oak St",
        city="Denver",
        state="CO",
        country="USA",
        phone_number="5551112222",
        initial_deposit=Decimal("1500.00"),
    ).account

    acc2 = banking_service.open_account(
        holder_name="Bob Vendor",
        dob=date(1985, 3, 10),
        address_line="456 Pine St",
        city="Boulder",
        state="CO",
        country="USA",
        phone_number="5553334444",
        initial_deposit=Decimal("2000.00"),
    ).account

    dto = banking_service.add_beneficiary(
        source_account=acc1.account_number,
        destination_account=acc2.account_number,
        nickname="Bob Supplies",
    )
    assert dto.nickname == "Bob Supplies"
    assert dto.destination_holder_name == "Bob Vendor"

    payees = banking_service.list_beneficiaries(acc1.account_number)
    assert len(payees) == 1
    assert payees[0].destination_account_number == acc2.account_number

    deleted = banking_service.delete_beneficiary(dto.beneficiary_id)
    assert deleted is True

    payees_after = banking_service.list_beneficiaries(acc1.account_number)
    assert len(payees_after) == 0


def test_add_beneficiary_self_transfer_rejected(banking_service: BankingService):
    acc = banking_service.open_account(
        holder_name="Charlie Single",
        dob=date(1992, 4, 12),
        address_line="789 Elm St",
        city="Austin",
        state="TX",
        country="USA",
        phone_number="5557778888",
        initial_deposit=Decimal("1000.00"),
    ).account

    with pytest.raises(SelfTransferError):
        banking_service.add_beneficiary(
            source_account=acc.account_number,
            destination_account=acc.account_number,
            nickname="Self",
        )


def test_add_beneficiary_nonexistent_destination_rejected(banking_service: BankingService):
    acc = banking_service.open_account(
        holder_name="Diana Prince",
        dob=date(1994, 6, 20),
        address_line="321 Maple Ave",
        city="Dallas",
        state="TX",
        country="USA",
        phone_number="5559990000",
        initial_deposit=Decimal("1000.00"),
    ).account

    with pytest.raises(AccountNotFoundError):
        banking_service.add_beneficiary(
            source_account=acc.account_number,
            destination_account="999999999999",
            nickname="Ghost",
        )
