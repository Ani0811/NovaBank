"""Unit tests for Transaction entity and AccountNumber value object."""

import pytest

from novabank.domain.entities.transaction import Transaction
from novabank.domain.exceptions import DomainError
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType


def test_account_number_validation():
    """Verify account number formatting and generation."""
    acc_no = AccountNumber("123456789012")
    assert acc_no.value == "123456789012"
    assert acc_no.masked == "****-****-9012"
    assert acc_no.formatted == "1234-5678-9012"

    # With hyphens or spaces in input
    acc_formatted = AccountNumber("1234-5678-9012")
    assert acc_formatted == acc_no

    # Invalid length
    with pytest.raises(DomainError, match="exactly 12 numeric digits"):
        AccountNumber("12345")

    # Non-numeric
    with pytest.raises(DomainError, match="exactly 12 numeric digits"):
        AccountNumber("12345678901a")

    # All zeros
    with pytest.raises(DomainError, match="cannot be all zeros"):
        AccountNumber("000000000000")


def test_account_number_generation():
    """Verify generated account numbers are valid."""
    acc1 = AccountNumber.generate()
    acc2 = AccountNumber.generate()

    assert len(acc1.value) == 12
    assert acc1.value.isdigit()
    assert acc1 != acc2  # Collision probability negligible


def test_transaction_entity_attributes():
    """Verify Transaction entity construction and property access."""
    acc_no = AccountNumber("123456789012")
    tx = Transaction(
        account_number=acc_no,
        transaction_type=TransactionType.DEPOSIT,
        direction=TransactionDirection.CREDIT,
        amount=Money("100.00"),
        balance_after=Money("100.00"),
        description="Initial deposit",
        created_by="teller_bob",
    )

    assert tx.account_number == acc_no
    assert tx.transaction_type == TransactionType.DEPOSIT
    assert tx.direction == TransactionDirection.CREDIT
    assert tx.amount == Money("100.00")
    assert tx.balance_after == Money("100.00")
    assert tx.created_by == "teller_bob"
    assert len(tx.transaction_ref) > 10  # UUID generated


def test_transaction_invalid_amount_rejected():
    """Verify transactions cannot have zero or negative amounts."""
    acc_no = AccountNumber("123456789012")

    with pytest.raises(DomainError, match="amount must be positive"):
        Transaction(
            account_number=acc_no,
            transaction_type=TransactionType.DEPOSIT,
            direction=TransactionDirection.CREDIT,
            amount=Money.zero(),
            balance_after=Money("100.00"),
        )
