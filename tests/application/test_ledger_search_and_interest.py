"""Tests for ledger search, CSV export, and batch interest accrual."""

from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine

from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.db.session import create_session_factory, init_database


@pytest.fixture
def banking_service() -> BankingService:
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_database(engine)
    factory = create_session_factory(engine)
    service = BankingService(factory)
    return service


def test_search_transactions_and_export_csv(banking_service: BankingService):
    acc1 = banking_service.open_account(
        holder_name="Alice Wealth",
        dob=date(1980, 1, 1),
        address_line="100 Wall St",
        city="New York",
        state="NY",
        country="USA",
        phone_number="5551230000",
        initial_deposit=Decimal("10000.00"),
    ).account

    acc2 = banking_service.open_account(
        holder_name="Bob Retail",
        dob=date(1985, 2, 2),
        address_line="200 Broadway",
        city="New York",
        state="NY",
        country="USA",
        phone_number="5551231111",
        initial_deposit=Decimal("5000.00"),
    ).account

    banking_service.deposit(acc1.account_number, Decimal("2500.00"), description="Dividend Check")
    banking_service.withdraw(acc1.account_number, Decimal("400.00"), description="ATM Cash")
    banking_service.transfer(
        acc1.account_number, acc2.account_number, Decimal("1500.00"), description="Invoice #101"
    )

    # Search all transactions
    results, count = banking_service.search_transactions(page=1, page_size=20)
    assert count >= 4
    assert len(results) >= 4

    # Filter by specific account
    acc1_results, acc1_count = banking_service.search_transactions(
        account_number=acc1.account_number
    )
    assert acc1_count >= 3

    # Filter by transaction type
    deposits, dep_count = banking_service.search_transactions(tx_type="DEPOSIT")
    assert dep_count >= 1
    assert all(tx.transaction_type == "DEPOSIT" for tx in deposits)

    # Filter by amount range
    large_txs, large_count = banking_service.search_transactions(
        min_amount=Decimal("1000.00"), max_amount=Decimal("3000.00")
    )
    assert large_count >= 1
    assert all(Decimal("1000.00") <= tx.amount <= Decimal("3000.00") for tx in large_txs)

    # Export to CSV
    csv_str = banking_service.export_ledger_csv(results)
    assert "Date,Reference,Type,Description,Debit,Credit,Balance,Currency" in csv_str
    assert "Dividend Check" in csv_str


def test_batch_interest_accrual(banking_service: BankingService):
    acc1 = banking_service.open_account(
        holder_name="Savers Club",
        dob=date(1975, 5, 5),
        address_line="300 High St",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5554445555",
        initial_deposit=Decimal("10000.00"),
    ).account

    acc2 = banking_service.open_account(
        holder_name="Low Balance",
        dob=date(1990, 8, 8),
        address_line="400 Low St",
        city="Chicago",
        state="IL",
        country="USA",
        phone_number="5556667777",
        initial_deposit=Decimal("20.00"),  # below $100 min balance
    ).account

    # Execute monthly interest accrual at 2.50% APY
    # $10,000 * 0.025 / 12 = $20.83
    credited = banking_service.accrue_interest(
        annual_rate_percentage=Decimal("2.50"),
        min_qualifying_balance=Decimal("100.00"),
    )

    assert len(credited) == 1
    assert credited[0].account_number == acc1.account_number
    assert credited[0].amount == Decimal("20.83")
    assert credited[0].transaction_type == "INTEREST"

    # Check updated balance on acc1
    updated_acc1 = banking_service.get_account(acc1.account_number)
    assert updated_acc1.balance == Decimal("10020.83")

    # acc2 was below min balance, should not receive interest
    updated_acc2 = banking_service.get_account(acc2.account_number)
    assert updated_acc2.balance == Decimal("20.00")
