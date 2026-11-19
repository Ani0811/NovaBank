"""SQLAlchemy adapter implementing FXRepositoryInterface for Foreign Exchange trades and Treasury positions."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from novabank.domain.entities.fx_trade import (
    ExchangeRate,
    FXTrade,
    TreasuryPosition,
)
from novabank.domain.repositories.fx_repository import FXRepositoryInterface
from novabank.domain.services.fx_calculator import (
    DEFAULT_USD_BENCHMARK_RATES,
    SUPPORTED_CURRENCIES,
)
from novabank.infrastructure.db.models import (
    FXRateModel,
    FXTradeModel,
    TreasuryPositionModel,
)

DEFAULT_INITIAL_RESERVES: list[tuple[str, Decimal, Decimal]] = [
    ("USD", Decimal("10000000.00"), Decimal("40.00")),
    ("EUR", Decimal("4500000.00"), Decimal("20.00")),
    ("GBP", Decimal("2500000.00"), Decimal("15.00")),
    ("JPY", Decimal("500000000.00"), Decimal("10.00")),
    ("CHF", Decimal("1500000.00"), Decimal("5.00")),
    ("CAD", Decimal("2000000.00"), Decimal("5.00")),
    ("AUD", Decimal("1500000.00"), Decimal("3.00")),
    ("SGD", Decimal("1000000.00"), Decimal("2.00")),
]


class SQLFXRepository(FXRepositoryInterface):
    """SQLAlchemy implementation of the Foreign Exchange and Treasury Desk repository."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._ensure_defaults_seeded()

    def _ensure_defaults_seeded(self) -> None:
        """Seed benchmark rates and initial treasury reserves if tables are empty."""
        try:
            # Seed rates
            rate_count = self.session.scalar(select(func.count(FXRateModel.pair)))
            if rate_count == 0:
                for pair, spot in DEFAULT_USD_BENCHMARK_RATES.items():
                    base, quote = pair.split("/")
                    model = FXRateModel(
                        pair=pair,
                        base_currency=base,
                        quote_currency=quote,
                        spot_rate=spot,
                        spread_bps=20,
                        last_updated=datetime.now(timezone.utc),
                    )
                    self.session.add(model)

            # Seed treasury positions
            pos_count = self.session.scalar(select(func.count(TreasuryPositionModel.currency)))
            if pos_count == 0:
                for curr, bal, alloc in DEFAULT_INITIAL_RESERVES:
                    pos = TreasuryPositionModel(
                        currency=curr,
                        reserve_balance=bal,
                        target_allocation_pct=alloc,
                        last_revalued_at=datetime.now(timezone.utc),
                    )
                    self.session.add(pos)
            self.session.flush()
        except Exception:
            # Safe ignore if tables aren't ready yet
            pass

    def save_trade(self, trade: FXTrade) -> FXTrade:
        """Persist an FX trade entity."""
        model = self.session.get(FXTradeModel, trade.trade_id)
        if model is None:
            model = FXTradeModel.from_entity(trade)
            self.session.add(model)
        else:
            model.status = trade.status.value
            model.actor = trade.actor
            model.settlement_reference = trade.settlement_reference

        self.session.flush()
        return model.to_entity()

    def get_trade_by_id(self, trade_id: str) -> Optional[FXTrade]:
        """Look up an FX trade by its unique identifier."""
        model = self.session.get(FXTradeModel, trade_id)
        return model.to_entity() if model else None

    def list_trades(
        self,
        account_number: Optional[str] = None,
        currency_pair: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[FXTrade], int]:
        """Retrieve paginated trade history matching optional criteria."""
        stmt = select(FXTradeModel)

        if account_number:
            clean_acc = account_number.strip().replace("-", "").replace(" ", "")
            stmt = stmt.where(FXTradeModel.account_number == clean_acc)

        if currency_pair:
            # Currency pair filter can match e.g. "EUR/USD" or "EUR"
            clean_p = currency_pair.strip().upper()
            if "/" in clean_p:
                src, tgt = clean_p.split("/")
                stmt = stmt.where(
                    (FXTradeModel.source_currency == src) & (FXTradeModel.target_currency == tgt)
                )
            else:
                stmt = stmt.where(
                    (FXTradeModel.source_currency == clean_p) | (FXTradeModel.target_currency == clean_p)
                )

        if status:
            clean_status = status.strip().upper()
            if clean_status not in ("ALL", "ALL STATUSES"):
                stmt = stmt.where(FXTradeModel.status == clean_status)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_count = self.session.scalar(count_stmt) or 0

        # Pagination & ordering
        offset = max(0, (page - 1) * page_size)
        paginated_stmt = stmt.order_by(desc(FXTradeModel.executed_at)).offset(offset).limit(page_size)
        models = self.session.scalars(paginated_stmt).all()

        return [m.to_entity() for m in models], total_count

    def get_rates(self) -> dict[str, ExchangeRate]:
        """Fetch all current benchmark exchange rates."""
        models = self.session.scalars(select(FXRateModel)).all()
        result: dict[str, ExchangeRate] = {}
        for m in models:
            entity = m.to_entity()
            result[entity.pair] = entity
        return result

    def save_rate(self, rate: ExchangeRate) -> None:
        """Persist or update an exchange rate quote."""
        model = self.session.get(FXRateModel, rate.pair)
        if model is None:
            model = FXRateModel.from_entity(rate)
            self.session.add(model)
        else:
            model.spot_rate = rate.spot_rate
            model.spread_bps = rate.spread_bps
            model.last_updated = rate.last_updated
        self.session.flush()

    def get_treasury_positions(self) -> list[TreasuryPosition]:
        """Retrieve all treasury reserve positions."""
        models = self.session.scalars(select(TreasuryPositionModel).order_by(TreasuryPositionModel.currency)).all()
        return [m.to_entity() for m in models]

    def get_treasury_position(self, currency: str) -> Optional[TreasuryPosition]:
        """Retrieve treasury reserve position for a specific currency."""
        model = self.session.get(TreasuryPositionModel, currency.upper())
        return model.to_entity() if model else None

    def save_treasury_position(self, position: TreasuryPosition) -> None:
        """Persist or update a treasury currency reserve position."""
        model = self.session.get(TreasuryPositionModel, position.currency.upper())
        if model is None:
            model = TreasuryPositionModel.from_entity(position)
            self.session.add(model)
        else:
            model.reserve_balance = position.reserve_balance
            model.target_allocation_pct = position.target_allocation_pct
            model.last_revalued_at = position.last_revalued_at
        self.session.flush()
