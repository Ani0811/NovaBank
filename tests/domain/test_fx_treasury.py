"""Unit tests for FX domain logic, currency triangulation, pricing, and treasury positions."""

from decimal import Decimal
import pytest

from novabank.domain.entities.fx_trade import (
    ExchangeRate,
    FXTrade,
    FXTradeStatus,
    TreasuryPosition,
)
from novabank.domain.exceptions import (
    InvalidFXAmountError,
    UnsupportedCurrencyError,
)
from novabank.domain.services.fx_calculator import (
    DEFAULT_USD_BENCHMARK_RATES,
    FXCalculator,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money


def test_fx_calculator_direct_and_inverse_spot_resolution():
    """Verify direct rate lookup and inverse calculation."""
    # Direct EUR/USD
    eur_usd = FXCalculator.resolve_spot_rate("EUR", "USD")
    assert eur_usd == Decimal("1.08500")

    # Inverse USD/EUR
    usd_eur = FXCalculator.resolve_spot_rate("USD", "EUR")
    assert usd_eur == Decimal("0.92166")

    # Identical currency pair
    usd_usd = FXCalculator.resolve_spot_rate("USD", "USD")
    assert usd_usd == Decimal("1.00000")


def test_fx_calculator_triangulation_via_usd():
    """Verify cross-currency triangulation through USD base."""
    # EUR to GBP: EUR/USD = 1.0850, GBP/USD = 1.2720 -> EUR/GBP = 1.0850 / 1.2720 = 0.85299
    eur_gbp = FXCalculator.resolve_spot_rate("EUR", "GBP")
    expected = (Decimal("1.0850") / Decimal("1.2720")).quantize(Decimal("0.00001"))
    assert eur_gbp == expected

    # GBP to JPY: GBP/USD = 1.2720, USD/JPY = 154.50 -> GBP/JPY = 1.2720 * 154.50 = 196.524
    gbp_jpy = FXCalculator.resolve_spot_rate("GBP", "JPY")
    assert gbp_jpy == Decimal("196.524")


def test_fx_calculator_effective_rate_and_fee():
    """Verify institutional spread deduction and transaction fee scaling."""
    # $10,000 USD to EUR
    spot, effective, target_amt, fee, spread_rev = FXCalculator.compute_conversion(
        source_currency="USD",
        target_currency="EUR",
        source_amount=Decimal("10000.00"),
        spread_bps=20,
    )

    # 10 bps fee on $10,000 = $10.00
    assert fee == Decimal("10.00")
    # Net converted is $9,990.00
    assert effective < spot
    assert target_amt > Decimal("0.00")
    assert spread_rev > Decimal("0.00")


def test_fx_calculator_unsupported_currency_rejected():
    """Ensure unsupported ISO currency codes raise UnsupportedCurrencyError."""
    with pytest.raises(UnsupportedCurrencyError):
        FXCalculator.resolve_spot_rate("BTC", "USD")

    with pytest.raises(UnsupportedCurrencyError):
        FXCalculator.resolve_spot_rate("USD", "XYZ")


def test_treasury_position_deposit_and_withdrawal():
    """Verify sovereign currency reserve balance mutations."""
    pos = TreasuryPosition(currency="EUR", reserve_balance=Decimal("1000000.00"))
    pos.deposit(Decimal("50000.00"))
    assert pos.reserve_balance == Decimal("1050000.00")

    pos.withdraw(Decimal("25000.00"))
    assert pos.reserve_balance == Decimal("1025000.00")

    with pytest.raises(InvalidFXAmountError):
        pos.deposit(Decimal("-50.00"))

    with pytest.raises(InvalidFXAmountError):
        pos.withdraw(Decimal("0.00"))


def test_fx_trade_entity_validation():
    """Verify FX trade aggregate root validation rules."""
    trade = FXTrade(
        trade_id="FX-12345678",
        account_number=AccountNumber("100000000001"),
        source_currency="USD",
        source_amount=Decimal("5000.00"),
        target_currency="EUR",
        target_amount=Decimal("4600.00"),
        spot_rate=Decimal("0.92166"),
        effective_rate=Decimal("0.92000"),
        spread_bps=20,
        spread_revenue_usd=Decimal("8.33"),
        fee_amount=Decimal("5.00"),
    )

    assert trade.status == FXTradeStatus.EXECUTED
    assert trade.settlement_reference.startswith("SWIFT-CLS-")

    # Cancelling trade
    trade.cancel(actor="supervisor")
    assert trade.status == FXTradeStatus.CANCELLED
    assert trade.actor == "supervisor"
