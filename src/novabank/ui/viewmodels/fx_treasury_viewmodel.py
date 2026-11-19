"""ViewModel coordinating Multi-Currency Treasury & FX Exchange Desk operations."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.fx_dto import (
    ExecuteFXTradeRequestDTO,
    FXQuoteRequestDTO,
    FXQuoteResponseDTO,
    FXRateTableEntryDTO,
    FXTradeDTO,
    TreasuryPositionDTO,
)

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class FXTreasuryViewModel(QObject):
    """Coordinates Foreign Exchange spot trading, pricing quotation, treasury positions, and trade blotter."""

    account_found = Signal(object)  # AccountDTO
    account_lookup_failed = Signal(str)

    quote_calculated = Signal(object)  # FXQuoteResponseDTO
    quote_failed = Signal(str)

    submitting_changed = Signal(bool)
    trade_executed = Signal(object)  # FXTradeDTO
    trade_failed = Signal(str)

    trades_loaded = Signal(list, int)  # (list[FXTradeDTO], total_count)
    trades_load_failed = Signal(str)

    treasury_updated = Signal(dict)  # {"total_usd": Decimal, "positions": list[TreasuryPositionDTO], ...}
    treasury_update_failed = Signal(str)

    rates_loaded = Signal(list)  # list[FXRateTableEntryDTO]
    rates_load_failed = Signal(str)

    csv_exported = Signal(str)
    csv_export_failed = Signal(str)

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner

        # Local cached state
        self.target_account: Optional[AccountDTO] = None
        self.current_quote: Optional[FXQuoteResponseDTO] = None
        self.current_trades: list[FXTradeDTO] = []
        self.current_positions: list[TreasuryPositionDTO] = []
        self.current_rates: list[FXRateTableEntryDTO] = []
        self.treasury_summary: dict = {}
        self._is_submitting: bool = False

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        self.banking_service = banking_service
        self.task_runner = task_runner

    def _safe_emit(self, sig: Signal, *args) -> None:
        try:
            sig.emit(*args)
        except RuntimeError:
            pass

    def lookup_account(self, account_number_raw: str) -> None:
        """Lookup funding account asynchronously."""
        clean_num = account_number_raw.strip().replace("-", "").replace(" ", "")
        if len(clean_num) != 12:
            self.target_account = None
            return

        if not self.banking_service or not self.task_runner:
            return

        def _fetch():
            return self.banking_service.get_account(clean_num)

        def _on_success(account: Optional[AccountDTO]):
            if account:
                if not account.is_active:
                    self.target_account = None
                    self._safe_emit(self.account_lookup_failed, f"Account {clean_num} is closed.")
                elif account.is_frozen:
                    self.target_account = None
                    self._safe_emit(self.account_lookup_failed, f"Account {clean_num} is frozen.")
                else:
                    self.target_account = account
                    self._safe_emit(self.account_found, account)
            else:
                self.target_account = None
                self._safe_emit(self.account_lookup_failed, f"Account {clean_num} not found.")

        def _on_error(exc: Exception, tb: str):
            self.target_account = None
            self._safe_emit(self.account_lookup_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def calculate_quote(
        self,
        source_currency: str,
        target_currency: str,
        source_amount_str: str,
    ) -> None:
        """Calculate live FX spot exchange quote."""
        src = source_currency.strip().upper()
        tgt = target_currency.strip().upper()

        if src == tgt:
            self.current_quote = None
            self._safe_emit(self.quote_failed, "Source and target currencies must differ.")
            return

        try:
            clean_str = source_amount_str.strip().replace("$", "").replace(",", "")
            amount = Decimal(clean_str)
            if amount <= Decimal("0.00"):
                self.current_quote = None
                self._safe_emit(self.quote_failed, "Exchange amount must be positive.")
                return
        except (InvalidOperation, ValueError, TypeError) as exc:
            self.current_quote = None
            self._safe_emit(self.quote_failed, f"Invalid amount: {exc}")
            return

        if not self.banking_service:
            return

        req = FXQuoteRequestDTO(
            source_currency=src,
            target_currency=tgt,
            source_amount=amount,
        )

        try:
            quote = self.banking_service.quote_fx_exchange(req)
            self.current_quote = quote
            self._safe_emit(self.quote_calculated, quote)
        except Exception as exc:
            self.current_quote = None
            self._safe_emit(self.quote_failed, str(exc))

    def execute_trade(
        self,
        account_number: str,
        source_currency: str,
        target_currency: str,
        source_amount: Decimal,
        actor: str = "senior_fx_trader",
    ) -> None:
        """Execute spot conversion asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        self._is_submitting = True
        self._safe_emit(self.submitting_changed, True)

        req = ExecuteFXTradeRequestDTO(
            account_number=account_number,
            source_currency=source_currency,
            target_currency=target_currency,
            source_amount=source_amount,
            actor=actor,
        )

        def _execute():
            return self.banking_service.execute_fx_conversion(req)

        def _on_success(trade_dto: FXTradeDTO):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.trade_executed, trade_dto)
            # Trigger refresh of blotter & treasury
            self.load_trades()
            self.load_treasury_overview()

        def _on_error(exc: Exception, tb: str):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.trade_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)

    def load_trades(
        self,
        account_number: Optional[str] = None,
        pair: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> None:
        """Load trade blotter records asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        clean_acc = account_number.strip().replace("-", "").replace(" ", "") if account_number else None
        clean_pair = pair.strip().upper() if pair and pair != "ALL" else None
        clean_status = status.strip().upper() if status and status != "ALL" else None

        def _fetch():
            return self.banking_service.list_fx_trades(
                account_number=clean_acc,
                pair=clean_pair,
                status=clean_status,
                limit=limit,
                offset=offset,
            )

        def _on_success(result):
            trades, total = result
            self.current_trades = trades
            self._safe_emit(self.trades_loaded, trades, total)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.trades_load_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def load_treasury_overview(self) -> None:
        """Load treasury position liquidity and mark-to-market balances asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        def _fetch():
            return self.banking_service.get_treasury_overview()

        def _on_success(result):
            positions, total_usd, volume_24h, spread_rev_24h = result
            summary = {
                "positions": positions,
                "total_usd": total_usd,
                "volume_24h": volume_24h,
                "spread_revenue_24h": spread_rev_24h,
            }
            self.treasury_summary = summary
            self.current_positions = positions
            self._safe_emit(self.treasury_updated, summary)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.treasury_update_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def load_live_rates(self) -> None:
        """Load benchmark spot rates table asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        def _fetch():
            return self.banking_service.get_live_fx_rates()

        def _on_success(rates: list[FXRateTableEntryDTO]):
            self.current_rates = rates
            self._safe_emit(self.rates_loaded, rates)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.rates_load_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def export_blotter_csv(self, destination: Optional[str] = None) -> None:
        """Export FX trade blotter to RFC-4180 CSV document."""
        if not self.banking_service or not self.task_runner:
            return

        def _export():
            return self.banking_service.export_fx_blotter_csv(destination=destination)

        def _on_success(content: str):
            self._safe_emit(self.csv_exported, content)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.csv_export_failed, str(exc))

        self.task_runner.run_async(_export, on_result=_on_success, on_error=_on_error)
