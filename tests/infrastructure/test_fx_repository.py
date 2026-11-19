"""Infrastructure repository tests for FX rates, trades, and treasury positions."""

from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.domain.entities.account import Account
from novabank.domain.entities.fx_trade import (
    ExchangeRate,
    FXTrade,
    FXTradeStatus,
    TreasuryPosition,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.models import Base
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_fx_repository import SQLFXRepository


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as sess:
        yield sess


def test_fx_repository_seeding_and_rates(session):
    """Verify repository automatically seeds default benchmark rates and treasury positions."""
    repo = SQLFXRepository(session)
    rates = repo.get_rates()

    assert "EUR/USD" in rates
    assert rates["EUR/USD"].spot_rate == Decimal("1.08500")

    positions = repo.get_treasury_positions()
    assert len(positions) == 8
    usd_pos = repo.get_treasury_position("USD")
    assert usd_pos is not None
    assert usd_pos.reserve_balance == Decimal("10000000.00")


def test_fx_repository_save_get_and_list_trades(session):
    """Verify saving trades, looking up by ID, and querying filtered blotter."""
    # Seed parent account
    acc_repo = SQLAccountRepository(session)
    acc_repo.save(
        Account(
            account_number=AccountNumber("100000000001"),
            holder_name="Global Capital Corp",
            dob=date(1985, 4, 12),
            address_line="100 Financial Way",
            city="New York",
            state="NY",
            country="USA",
            phone_number="2125550188",
            balance=Money("500000.00"),
        )
    )

    repo = SQLFXRepository(session)
    trade = FXTrade(
        trade_id="FX-TEST-001",
        account_number=AccountNumber("100000000001"),
        source_currency="USD",
        source_amount=Decimal("20000.00"),
        target_currency="GBP",
        target_amount=Decimal("15700.00"),
        spot_rate=Decimal("0.78616"),
        effective_rate=Decimal("0.78500"),
        spread_bps=20,
        spread_revenue_usd=Decimal("29.40"),
        fee_amount=Decimal("20.00"),
    )

    repo.save_trade(trade)

    fetched = repo.get_trade_by_id("FX-TEST-001")
    assert fetched is not None
    assert fetched.trade_id == "FX-TEST-001"
    assert fetched.target_currency == "GBP"

    # List trades
    trades, total = repo.list_trades(account_number="100000000001")
    assert total == 1
    assert len(trades) == 1
    assert trades[0].trade_id == "FX-TEST-001"
