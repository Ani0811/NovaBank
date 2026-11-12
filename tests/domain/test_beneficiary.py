"""Domain entity tests for Beneficiary payee records."""

import pytest

from novabank.domain.entities.beneficiary import Beneficiary
from novabank.domain.exceptions import DomainError, SelfTransferError
from novabank.domain.value_objects.account_number import AccountNumber


def test_valid_beneficiary_creation():
    src = AccountNumber("123456789012")
    dest = AccountNumber("987654321098")
    ben = Beneficiary(
        source_account_number=src,
        destination_account_number=dest,
        destination_holder_name="Jane Doe",
        nickname="Jane Personal",
    )
    assert ben.source_account_number == src
    assert ben.destination_account_number == dest
    assert ben.destination_holder_name == "Jane Doe"
    assert ben.nickname == "Jane Personal"
    assert ben.bank_name == "NovaBank"


def test_beneficiary_self_transfer_rejected():
    src = AccountNumber("123456789012")
    with pytest.raises(SelfTransferError):
        Beneficiary(
            source_account_number=src,
            destination_account_number=src,
            destination_holder_name="Self",
            nickname="My Other Self",
        )


def test_beneficiary_empty_nickname_rejected():
    src = AccountNumber("123456789012")
    dest = AccountNumber("987654321098")
    with pytest.raises(DomainError, match="nickname cannot be empty"):
        Beneficiary(
            source_account_number=src,
            destination_account_number=dest,
            destination_holder_name="Jane",
            nickname="   ",
        )


def test_beneficiary_long_nickname_rejected():
    src = AccountNumber("123456789012")
    dest = AccountNumber("987654321098")
    with pytest.raises(DomainError, match="cannot exceed 50"):
        Beneficiary(
            source_account_number=src,
            destination_account_number=dest,
            destination_holder_name="Jane",
            nickname="x" * 51,
        )


def test_beneficiary_empty_holder_name_rejected():
    src = AccountNumber("123456789012")
    dest = AccountNumber("987654321098")
    with pytest.raises(DomainError, match="holder name cannot be empty"):
        Beneficiary(
            source_account_number=src,
            destination_account_number=dest,
            destination_holder_name="   ",
            nickname="Nick",
        )


def test_beneficiary_equality_and_hashing():
    src = AccountNumber("123456789012")
    dest = AccountNumber("987654321098")
    b1 = Beneficiary(src, dest, "Jane Doe", "Nick 1")
    b2 = Beneficiary(src, dest, "Jane Doe", "Nick 2")
    assert b1 == b2
    assert hash(b1) == hash(b2)

