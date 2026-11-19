"""Data Transfer Objects for Multi-Currency Treasury and FX Exchange Desk."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from novabank.domain.entities.fx_trade import (
    ExchangeRate,
    FXTrade,
    TreasuryPosition,
)
from novabank.domain.services.fx_calculator import FXCalculator


@dataclass(frozen=True)
class FXQuoteRequestDTO:
    """Inbound request to calculate live FX quotation."""

    source_currency: str
    target_currency: str
    source_amount: Decimal


@dataclass(frozen=True)
class FXQuoteResponseDTO:
    """Outbound guaranteed execution quote with fee and spread breakdown."""

    source_currency: str
    target_currency: str
    source_amount: Decimal
    target_amount: Decimal
    spot_rate: Decimal
    effective_rate: Decimal
    spread_bps: int
    fee_amount: Decimal
    spread_revenue_usd: Decimal
    guaranteed_seconds: int = 60

    @property
    def formatted_source_amount(self) -> str:
        symbol = "$" if self.source_currency == "USD" else f"{self.source_currency} "
        decimals = FXCalculator.get_currency_decimals(self.source_currency)
        return f"{symbol}{self.source_amount:,.{decimals}f}"

    @property
    def formatted_target_amount(self) -> str:
        symbol = "$" if self.target_currency == "USD" else f"{self.target_currency} "
        decimals = FXCalculator.get_currency_decimals(self.target_currency)
        return f"{symbol}{self.target_amount:,.{decimals}f}"

    @property
    def formatted_spot_rate(self) -> str:
        decimals = 3 if self.target_currency == "JPY" else 5
        return f"{self.spot_rate:.{decimals}f}"

    @property
    def formatted_effective_rate(self) -> str:
        decimals = 3 if self.target_currency == "JPY" else 5
        return f"{self.effective_rate:.{decimals}f}"

    @property
    def formatted_fee(self) -> str:
        decimals = FXCalculator.get_currency_decimals(self.source_currency)
        return f"{self.source_currency} {self.fee_amount:,.{decimals}f}"

    @property
    def formatted_spread_revenue(self) -> str:
        return f"${self.spread_revenue_usd:,.2f}"


@dataclass(frozen=True)
class ExecuteFXTradeRequestDTO:
    """Inbound request to execute an atomic spot FX conversion."""

    account_number: str
    source_currency: str
    target_currency: str
    source_amount: Decimal
    actor: str = "teller"


@dataclass(frozen=True)
class FXTradeDTO:
    """Read-only view representation of an executed Foreign Exchange trade."""

    trade_id: str
    account_number: str
    source_currency: str
    source_amount: Decimal
    target_currency: str
    target_amount: Decimal
    spot_rate: Decimal
    effective_rate: Decimal
    spread_bps: int
    spread_revenue_usd: Decimal
    fee_amount: Decimal
    status: str
    settlement_reference: str
    actor: str
    executed_at: str

    @property
    def formatted_source_amount(self) -> str:
        decimals = FXCalculator.get_currency_decimals(self.source_currency)
        return f"{self.source_currency} {self.source_amount:,.{decimals}f}"

    @property
    def formatted_target_amount(self) -> str:
        decimals = FXCalculator.get_currency_decimals(self.target_currency)
        return f"{self.target_currency} {self.target_amount:,.{decimals}f}"

    @property
    def formatted_effective_rate(self) -> str:
        decimals = 3 if self.target_currency == "JPY" else 5
        return f"{self.effective_rate:.{decimals}f}"

    @property
    def formatted_fee(self) -> str:
        decimals = FXCalculator.get_currency_decimals(self.source_currency)
        return f"{self.source_currency} {self.fee_amount:,.{decimals}f}"

    @property
    def pair_display(self) -> str:
        return f"{self.source_currency}/{self.target_currency}"

    @classmethod
    def from_entity(cls, entity: FXTrade) -> FXTradeDTO:
        return cls(
            trade_id=entity.trade_id,
            account_number=entity.account_number.value,
            source_currency=entity.source_currency,
            source_amount=entity.source_amount,
            target_currency=entity.target_currency,
            target_amount=entity.target_amount,
            spot_rate=entity.spot_rate,
            effective_rate=entity.effective_rate,
            spread_bps=entity.spread_bps,
            spread_revenue_usd=entity.spread_revenue_usd,
            fee_amount=entity.fee_amount,
            status=entity.status.value,
            settlement_reference=entity.settlement_reference,
            actor=entity.actor,
            executed_at=entity.executed_at.strftime("%Y-%m-%d %H:%M:%S"),
        )


@dataclass(frozen=True)
class TreasuryPositionDTO:
    """Read-only view representation of a sovereign currency reserve position."""

    currency: str
    reserve_balance: Decimal
    usd_equivalent: Decimal
    spot_to_usd: Decimal
    target_allocation_pct: Decimal
    current_allocation_pct: Decimal
    last_revalued_at: str

    @property
    def formatted_reserve_balance(self) -> str:
        decimals = FXCalculator.get_currency_decimals(self.currency)
        return f"{self.currency} {self.reserve_balance:,.{decimals}f}"

    @property
    def formatted_usd_equivalent(self) -> str:
        return f"${self.usd_equivalent:,.2f}"

    @property
    def formatted_spot_to_usd(self) -> str:
        return f"{self.spot_to_usd:.5f}"

    @property
    def formatted_allocation(self) -> str:
        return f"{self.current_allocation_pct:.1f}%"


@dataclass(frozen=True)
class FXRateTableEntryDTO:
    """Benchmark market exchange rate entry for live ticker tables."""

    pair: str
    base_currency: str
    quote_currency: str
    spot_rate: Decimal
    bid_rate: Decimal
    ask_rate: Decimal
    spread_bps: int
    last_updated: str

    @property
    def currency_pair(self) -> str:
        return self.pair

    @property
    def formatted_spot(self) -> str:
        decimals = 3 if self.quote_currency == "JPY" else 5
        return f"{self.spot_rate:.{decimals}f}"

    @property
    def formatted_bid(self) -> str:
        decimals = 3 if self.quote_currency == "JPY" else 5
        return f"{self.bid_rate:.{decimals}f}"

    @property
    def formatted_ask(self) -> str:
        decimals = 3 if self.quote_currency == "JPY" else 5
        return f"{self.ask_rate:.{decimals}f}"

    @classmethod
    def from_entity(cls, entity: ExchangeRate) -> FXRateTableEntryDTO:
        return cls(
            pair=entity.pair,
            base_currency=entity.base_currency,
            quote_currency=entity.quote_currency,
            spot_rate=entity.spot_rate,
            bid_rate=entity.bid_rate,
            ask_rate=entity.ask_rate,
            spread_bps=entity.spread_bps,
            last_updated=entity.last_updated.strftime("%Y-%m-%d %H:%M:%S"),
        )
