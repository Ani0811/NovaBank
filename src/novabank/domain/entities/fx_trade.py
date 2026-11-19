"""Domain entities for Multi-Currency Foreign Exchange (FX) trades and Treasury Reserves."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional

from novabank.domain.exceptions import (
    InvalidFXAmountError,
    UnsupportedCurrencyError,
)
from novabank.domain.services.fx_calculator import (
    SUPPORTED_CURRENCIES,
    FXCalculator,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money


class FXTradeStatus(str, Enum):
    """Lifecycle statuses for Foreign Exchange transactions."""

    EXECUTED = "EXECUTED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class ExchangeRate:
    """Read-only market quote for a currency pair."""

    pair: str  # e.g. "EUR/USD"
    base_currency: str
    quote_currency: str
    spot_rate: Decimal
    spread_bps: int = 20
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def bid_rate(self) -> Decimal:
        """Client selling base currency to bank."""
        spread_factor = Decimal(self.spread_bps) / Decimal("10000.00")
        rate = self.spot_rate * (Decimal("1.00000000") - spread_factor)
        return FXCalculator.quantize_rate(rate, self.quote_currency)

    @property
    def ask_rate(self) -> Decimal:
        """Client buying base currency from bank."""
        spread_factor = Decimal(self.spread_bps) / Decimal("10000.00")
        rate = self.spot_rate * (Decimal("1.00000000") + spread_factor)
        return FXCalculator.quantize_rate(rate, self.quote_currency)


@dataclass
class TreasuryPosition:
    """Bank liquidity reserve held in a specific sovereign currency."""

    currency: str
    reserve_balance: Decimal
    target_allocation_pct: Decimal = Decimal("0.00")
    last_revalued_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if self.currency.upper() not in SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(self.currency)

    def deposit(self, amount: Decimal) -> None:
        """Credit currency to treasury vault reserve."""
        if amount <= Decimal("0.00"):
            raise InvalidFXAmountError("Deposit amount must be strictly positive.")
        self.reserve_balance += amount
        self.last_revalued_at = datetime.now(timezone.utc)

    def withdraw(self, amount: Decimal) -> None:
        """Debit currency from treasury vault reserve."""
        if amount <= Decimal("0.00"):
            raise InvalidFXAmountError("Withdrawal amount must be strictly positive.")
        self.reserve_balance -= amount
        self.last_revalued_at = datetime.now(timezone.utc)


@dataclass
class FXTrade:
    """Aggregate root representing an executed institutional Foreign Exchange trade."""

    trade_id: str
    account_number: AccountNumber
    source_currency: str
    source_amount: Decimal
    target_currency: str
    target_amount: Decimal
    spot_rate: Decimal
    effective_rate: Decimal
    spread_bps: int
    spread_revenue_usd: Decimal
    fee_amount: Decimal
    status: FXTradeStatus = FXTradeStatus.EXECUTED
    settlement_reference: str = ""
    actor: str = "teller"
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        src = self.source_currency.upper()
        tgt = self.target_currency.upper()

        if src not in SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(src)
        if tgt not in SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(tgt)
        if src == tgt:
            raise InvalidFXAmountError("Source and target currencies must differ for FX exchange.")
        if self.source_amount <= Decimal("0.00") or self.target_amount <= Decimal("0.00"):
            raise InvalidFXAmountError("FX trade amounts must be strictly positive.")
        if self.effective_rate <= Decimal("0.00"):
            raise InvalidFXAmountError("Effective exchange rate must be strictly positive.")

        if not self.settlement_reference:
            clean_id = self.trade_id.replace("FX-", "").replace("-", "")
            self.settlement_reference = f"SWIFT-CLS-{clean_id.upper()}"

    def cancel(self, actor: str = "teller") -> None:
        """Cancel an executed trade."""
        if self.status == FXTradeStatus.CANCELLED:
            return
        self.status = FXTradeStatus.CANCELLED
        self.actor = actor

    def settle(self) -> None:
        """Mark trade as settled."""
        self.status = FXTradeStatus.SETTLED
