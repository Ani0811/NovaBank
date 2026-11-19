"""Application layer integration tests for FX quotation, conversion execution, and treasury desk."""

from datetime import date
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from novabank.application.dto.fx_dto import ExecuteFXTradeRequestDTO
from novabank.application.events import (
    FXTradeExecutedEvent,
    TreasuryPositionUpdatedEvent,
    WithdrawalCompletedEvent,
)
from novabank.application.services.banking_service import BankingService
from novabank.domain.entities.account import Account
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountFrozenError,
    InsufficientFundsError,
    InsufficientTreasuryReserveError,
    InvalidFXAmountError,
    UnsupportedCurrencyError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.db.models import Base
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_fx_repository import SQLFXRepository


@pytest.fixture
def db_setup():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    return session_factory, engine


def test_quote_fx_exchange(db_setup):
    """Verify calculating an execution quote between USD and EUR."""
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    quote = service.quote_fx_exchange(
        source_currency="USD",
        target_currency="EUR",
        source_amount=Decimal("10000.00"),
    )

    assert quote.source_currency == "USD"
    assert quote.target_currency == "EUR"
    assert quote.source_amount == Decimal("10000.00")
    assert quote.target_amount > Decimal("0.00")
    assert quote.spot_rate > Decimal("0.00")
    assert quote.fee_amount == Decimal("10.00")


def test_execute_fx_conversion_success_path(db_setup):
    """Verify full atomic trade execution: debit customer USD balance, update treasury positions, emit events."""
    session_factory, _ = db_setup
    events = []
    service = BankingService(session_factory=session_factory, event_publisher=events.append)

    # Seed funding account
    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            repo.save(
                Account(
                    account_number=AccountNumber("111122223333"),
                    holder_name="Solomon FX Holdings",
                    dob=date(1980, 5, 10),
                    address_line="50 Wall St",
                    city="New York",
                    state="NY",
                    country="USA",
                    phone_number="2125550177",
                    balance=Money("50000.00"),
                )
            )

    req = ExecuteFXTradeRequestDTO(
        account_number="111122223333",
        source_currency="USD",
        target_currency="EUR",
        source_amount=Decimal("10000.00"),
        actor="senior_fx_trader",
    )

    trade_dto = service.execute_fx_conversion(req)
    assert trade_dto.trade_id.startswith("FX-")
    assert trade_dto.status == "EXECUTED"
    assert trade_dto.source_amount == Decimal("10000.00")
    assert trade_dto.target_amount > Decimal("0.00")

    # Customer account debited: $50,000 - $10,000 = $40,000
    acc = service.get_account("111122223333")
    assert acc.balance == Decimal("40000.00")

    # Treasury EUR reserve was decremented
    with session_factory() as sess:
        fx_repo = SQLFXRepository(sess)
        eur_pos = fx_repo.get_treasury_position("EUR")
        assert eur_pos.reserve_balance < Decimal("4500000.00")
        usd_pos = fx_repo.get_treasury_position("USD")
        assert usd_pos.reserve_balance > Decimal("10000000.00")

    # Verify domain events
    trade_event = next(e for e in events if isinstance(e, FXTradeExecutedEvent))
    assert trade_event.trade_id == trade_dto.trade_id
    assert trade_event.actor == "senior_fx_trader"


def test_execute_fx_conversion_insufficient_funds_rejected(db_setup):
    """Verify trade is rejected when customer account has insufficient balance."""
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            repo.save(
                Account(
                    account_number=AccountNumber("111122223333"),
                    holder_name="Solomon FX Holdings",
                    dob=date(1980, 5, 10),
                    address_line="50 Wall St",
                    city="New York",
                    state="NY",
                    country="USA",
                    phone_number="2125550177",
                    balance=Money("500.00"),
                )
            )

    req = ExecuteFXTradeRequestDTO(
        account_number="111122223333",
        source_currency="USD",
        target_currency="EUR",
        source_amount=Decimal("5000.00"),
    )

    with pytest.raises(InsufficientFundsError):
        service.execute_fx_conversion(req)


def test_treasury_overview_and_blotter_export(db_setup):
    """Verify treasury aggregation metrics and CSV blotter export."""
    session_factory, _ = db_setup
    service = BankingService(session_factory=session_factory)

    positions, total_usd, vol_24h, spread_rev_24h = service.get_treasury_overview()
    assert len(positions) == 8
    assert total_usd > Decimal("0.00")

    csv_content = service.export_fx_blotter_csv()
    assert "Trade ID,Timestamp,Account Number" in csv_content
