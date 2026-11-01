"""ViewModel coordinating account statement retrieval, period filter presets, and KPI metrics."""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.statement_dto import AccountStatementDTO

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class StatementViewModel(QObject):
    """ViewModel for managing statement state, date filtering, and asynchronous loading."""

    account_found = Signal(object)  # AccountDTO
    account_lookup_failed = Signal(str)
    statement_loaded = Signal(object)  # AccountStatementDTO
    loading_changed = Signal(bool)
    error_occurred = Signal(str)
    filter_preset_changed = Signal(str, object, object)  # (preset_name, start_date, end_date)

    PRESET_TODAY = "TODAY"
    PRESET_LAST_7_DAYS = "LAST_7_DAYS"
    PRESET_THIS_MONTH = "THIS_MONTH"
    PRESET_YTD = "YTD"
    PRESET_ALL_TIME = "ALL_TIME"
    PRESET_CUSTOM = "CUSTOM"

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner

        # State
        self.account: Optional[AccountDTO] = None
        self.current_statement: Optional[AccountStatementDTO] = None
        self.selected_preset: str = self.PRESET_THIS_MONTH
        self.start_date: Optional[date] = None
        self.end_date: Optional[date] = None
        self._is_loading: bool = False

        # Initialize to current month
        self._apply_preset_dates(self.PRESET_THIS_MONTH)

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        """Inject banking service and async task runner dependencies."""
        self.banking_service = banking_service
        self.task_runner = task_runner

    def set_account(self, account: AccountDTO) -> None:
        """Set active customer account and immediately refresh statement."""
        self.account = account
        self.account_found.emit(account)
        self.load_statement()

    def lookup_account(self, account_number_raw: str) -> None:
        """Lookup account asynchronously and generate statement on match."""
        clean_num = account_number_raw.strip().replace("-", "").replace(" ", "")
        if len(clean_num) != 12:
            self.account = None
            self.current_statement = None
            return

        if not self.banking_service or not self.task_runner:
            return

        self._set_loading(True)

        def _fetch():
            return self.banking_service.get_account(clean_num)

        def _on_success(dto: Optional[AccountDTO]):
            if dto:
                self.account = dto
                self.account_found.emit(dto)
                self.load_statement()
            else:
                self.account = None
                self.current_statement = None
                self._set_loading(False)
                self.account_lookup_failed.emit(f"Account {clean_num} does not exist.")

        def _on_error(exc: Exception, tb: str):
            self.account = None
            self.current_statement = None
            self._set_loading(False)
            self.account_lookup_failed.emit(str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def _apply_preset_dates(self, preset: str, reference_date: Optional[date] = None) -> None:
        today = reference_date or date.today()

        if preset == self.PRESET_TODAY:
            self.start_date = today
            self.end_date = today
        elif preset == self.PRESET_LAST_7_DAYS:
            self.start_date = today - timedelta(days=7)
            self.end_date = today
        elif preset == self.PRESET_THIS_MONTH:
            self.start_date = date(today.year, today.month, 1)
            self.end_date = today
        elif preset == self.PRESET_YTD:
            self.start_date = date(today.year, 1, 1)
            self.end_date = today
        elif preset == self.PRESET_ALL_TIME:
            self.start_date = None
            self.end_date = today
        elif preset == self.PRESET_CUSTOM:
            pass  # Retain custom dates

        self.selected_preset = preset

    def select_preset(self, preset: str, reference_date: Optional[date] = None) -> None:
        """Change date filter preset and refresh statement if account is selected."""
        self._apply_preset_dates(preset, reference_date)
        self.filter_preset_changed.emit(preset, self.start_date, self.end_date)
        if self.account:
            self.load_statement()

    def set_custom_date_range(self, start: date, end: date) -> bool:
        """Apply a custom date range and refresh statement."""
        if start > end:
            self.error_occurred.emit("Start date cannot be after end date.")
            return False

        self.start_date = start
        self.end_date = end
        self.selected_preset = self.PRESET_CUSTOM
        self.filter_preset_changed.emit(self.PRESET_CUSTOM, start, end)
        if self.account:
            self.load_statement()
        return True

    def load_statement(self) -> None:
        """Asynchronously generate account statement using current account and date parameters."""
        if not self.account or not self.banking_service or not self.task_runner:
            return

        acc_num = self.account.account_number
        start = self.start_date
        end = self.end_date

        self._set_loading(True)

        def _do_generate():
            return self.banking_service.get_statement(
                account_number=acc_num,
                start_date=start,
                end_date=end,
            )

        def _on_success(statement: AccountStatementDTO):
            self.current_statement = statement
            self.statement_loaded.emit(statement)

        def _on_error(exc: Exception, tb: str):
            self.current_statement = None
            self.error_occurred.emit(str(exc))

        def _on_finished():
            self._set_loading(False)

        self.task_runner.run_async(
            _do_generate,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def _set_loading(self, is_loading: bool) -> None:
        if self._is_loading != is_loading:
            self._is_loading = is_loading
            self.loading_changed.emit(is_loading)
