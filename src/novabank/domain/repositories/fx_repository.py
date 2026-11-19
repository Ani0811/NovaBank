"""Repository port interface for Foreign Exchange trades, market rates, and Treasury positions."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from novabank.domain.entities.fx_trade import (
    ExchangeRate,
    FXTrade,
    TreasuryPosition,
)


class FXRepositoryInterface(ABC):
    """Port interface defining persistence operations for FX trades and treasury reserves."""

    @abstractmethod
    def save_trade(self, trade: FXTrade) -> FXTrade:
        """Persist an FX trade entity."""
        raise NotImplementedError

    @abstractmethod
    def get_trade_by_id(self, trade_id: str) -> Optional[FXTrade]:
        """Look up an FX trade by its unique identifier."""
        raise NotImplementedError

    @abstractmethod
    def list_trades(
        self,
        account_number: Optional[str] = None,
        currency_pair: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[FXTrade], int]:
        """Retrieve paginated trade history matching optional criteria."""
        raise NotImplementedError

    @abstractmethod
    def get_rates(self) -> dict[str, ExchangeRate]:
        """Fetch all current benchmark exchange rates."""
        raise NotImplementedError

    @abstractmethod
    def save_rate(self, rate: ExchangeRate) -> None:
        """Persist or update an exchange rate quote."""
        raise NotImplementedError

    @abstractmethod
    def get_treasury_positions(self) -> list[TreasuryPosition]:
        """Retrieve all treasury reserve positions."""
        raise NotImplementedError

    @abstractmethod
    def get_treasury_position(self, currency: str) -> Optional[TreasuryPosition]:
        """Retrieve treasury reserve position for a specific currency."""
        raise NotImplementedError

    @abstractmethod
    def save_treasury_position(self, position: TreasuryPosition) -> None:
        """Persist or update a treasury currency reserve position."""
        raise NotImplementedError
