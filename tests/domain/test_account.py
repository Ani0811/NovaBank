"""Unit tests for Account entity and domain invariants."""

from datetime import date, timedelta

import pytest

from novabank.domain.entities.account import Account
from novabank.domain.exceptions import (
    AccountClosedError,
    DomainError,
    InsufficientFundsError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection


def create_sample_account(balance: str = "100.00", is_active: bool = True) -> Account:
    """Helper to create a standard valid Account entity."""
    return Account(
        account_number=AccountNumber("123456789012"),
        holder_name="Alice Johnson",
        dob=date(1995, 5, 20),
        address_line="123 Financial Way",
        city="Metropolis",
        state="NY",
        country="USA",
        phone_number="1234567890",
        is_active=is_active,
        balance=Money(balance),
    )


def test_account_creation_valid():
    """Verify standard account initialization."""
    account = create_sample_account()
    assert account.account_number.value == "123456789012"
    assert account.holder_name == "Alice Johnson"
    assert account.balance == Money("100.00")
    assert account.is_active is True
    assert account.version == 1


def test_holder_name_validation():
    """Verify name validation boundaries."""
    with pytest.raises(DomainError, match="Account holder name cannot be empty"):
        Account(
            account_number=AccountNumber("123456789012"),
            holder_name="   ",
            dob=date(1995, 5, 20),
            address_line="123 Financial Way",
            city="Metropolis",
            state="NY",
            country="USA",
            phone_number="1234567890",
        )

    with pytest.raises(DomainError, match="at least 2 characters"):
        Account(
            account_number=AccountNumber("123456789012"),
            holder_name="A",
            dob=date(1995, 5, 20),
            address_line="123 Financial Way",
            city="Metropolis",
            state="NY",
            country="USA",
            phone_number="1234567890",
        )


def test_dob_age_validation():
    """Verify age boundaries (minimum 18, maximum 120, no future dates)."""
    today = date.today()

    # Underage (17 years old)
    underage_dob = date(today.year - 17, today.month, today.day)
    with pytest.raises(DomainError, match="at least 18 years old"):
        Account(
            account_number=AccountNumber("123456789012"),
            holder_name="Young Teen",
            dob=underage_dob,
            address_line="123 Way",
            city="City",
            state="ST",
            country="USA",
            phone_number="1234567890",
        )

    # Future DOB
    with pytest.raises(DomainError, match="cannot be in the future"):
        Account(
            account_number=AccountNumber("123456789012"),
            holder_name="Time Traveler",
            dob=today + timedelta(days=1),
            address_line="123 Way",
            city="City",
            state="ST",
            country="USA",
            phone_number="1234567890",
        )


def test_phone_number_validation():
    """Verify phone must be exactly 10 digits."""
    with pytest.raises(DomainError, match="exactly 10 digits"):
        Account(
            account_number=AccountNumber("123456789012"),
            holder_name="Alice",
            dob=date(1995, 1, 1),
            address_line="123 Way",
            city="City",
            state="ST",
            country="USA",
            phone_number="12345",  # Too short
        )

    with pytest.raises(DomainError, match="exactly 10 digits"):
        Account(
            account_number=AccountNumber("123456789012"),
            holder_name="Alice",
            dob=date(1995, 1, 1),
            address_line="123 Way",
            city="City",
            state="ST",
            country="USA",
            phone_number="12345678901",  # Too long
        )


def test_credit_workflow_success():
    """Verify successful credit updates balance, version, and produces Transaction."""
    account = create_sample_account("50.00")
    tx = account.credit(Money("25.50"), description="Payroll", actor="teller_1")

    assert account.balance == Money("75.50")
    assert account.version == 2
    assert tx.amount == Money("25.50")
    assert tx.balance_after == Money("75.50")
    assert tx.direction == TransactionDirection.CREDIT
    assert tx.created_by == "teller_1"


def test_credit_to_closed_account_fails():
    """Verify credit fails on closed accounts."""
    account = create_sample_account(is_active=False)
    with pytest.raises(AccountClosedError):
        account.credit(Money("10.00"))


def test_debit_workflow_success():
    """Verify successful debit decreases balance and produces Transaction."""
    account = create_sample_account("100.00")
    tx = account.debit(Money("40.00"), description="ATM Cash", actor="atm_1")

    assert account.balance == Money("60.00")
    assert account.version == 2
    assert tx.amount == Money("40.00")
    assert tx.balance_after == Money("60.00")
    assert tx.direction == TransactionDirection.DEBIT


def test_debit_insufficient_funds_overdraft_prevention():
    """Verify debit greater than balance raises InsufficientFundsError."""
    account = create_sample_account("50.00")

    with pytest.raises(InsufficientFundsError) as exc_info:
        account.debit(Money("50.01"))

    assert "available balance is $50.00" in str(exc_info.value)
    # Balance must remain unchanged
    assert account.balance == Money("50.00")
    assert account.version == 1


def test_account_closure_requires_zero_balance():
    """Verify account cannot be closed with positive balance."""
    account = create_sample_account("10.00")

    with pytest.raises(DomainError, match="balance must be zero before closure"):
        account.close()

    # Zero the balance first
    account.debit(Money("10.00"))
    assert account.balance.is_zero()

    account.close()
    assert account.is_active is False

    # Second closure attempt fails
    with pytest.raises(DomainError, match="already closed"):
        account.close()


def test_profile_update():
    """Verify updating contact information."""
    account = create_sample_account()
    account.update_profile(
        address_line="456 New Blvd",
        city="Gotham",
        state="NJ",
        country="USA",
        phone_number="9876543210",
    )

    assert account.address_line == "456 New Blvd"
    assert account.city == "Gotham"
    assert account.phone_number == "9876543210"
    assert account.version == 2
