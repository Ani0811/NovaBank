"""ViewModel for customer account directory with debounced search, filtering, and pagination."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, QTimer, Signal

from novabank.application.dto.account_dto import AccountDTO

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class AccountListViewModel(QObject):
    """ViewModel managing state, debounced filtering, and async loading for AccountListView."""

    loading_changed = Signal(bool)
    accounts_loaded = Signal(list, int, int, int)  # accounts, total_count, page, total_pages
    load_error = Signal(str)
    account_selected = Signal(object)  # AccountDTO

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner

        self.search_query: str = ""
        self.status_filter: str = "ALL"  # ALL, ACTIVE, CLOSED
        self.current_page: int = 1
        self.page_size: int = 25
        self.total_count: int = 0
        self.total_pages: int = 1
        self.accounts: list[AccountDTO] = []
        self.is_loading: bool = False

        # Debounce timer for instant search queries
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._on_debounce_timeout)

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        """Inject or update backend services."""
        self.banking_service = banking_service
        self.task_runner = task_runner

    def set_search_query(self, query: str) -> None:
        """Update search query string and restart the 200ms debounce timer."""
        self.search_query = query
        self.current_page = 1
        self._debounce_timer.stop()
        self._debounce_timer.start(200)

    def _on_debounce_timeout(self) -> None:
        """Invoked when debounce timer expires."""
        self.load_data()

    def set_status_filter(self, filter_name: str) -> None:
        """Update status filter ('ALL', 'ACTIVE', 'CLOSED') and reload."""
        norm_filter = filter_name.strip().upper()
        if norm_filter in ("ALL", "ACTIVE", "CLOSED"):
            self.status_filter = norm_filter
            self.current_page = 1
            self.load_data()

    def next_page(self) -> None:
        """Advance to next page if available."""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_data()

    def prev_page(self) -> None:
        """Go back to previous page if available."""
        if self.current_page > 1:
            self.current_page -= 1
            self.load_data()

    def refresh(self) -> None:
        """Force immediate reload of current view."""
        self._debounce_timer.stop()
        self.load_data()

    def select_account_at_index(self, index: int) -> Optional[AccountDTO]:
        """Select account by table index and emit account_selected signal."""
        if 0 <= index < len(self.accounts):
            acc = self.accounts[index]
            self.account_selected.emit(acc)
            return acc
        return None

    def load_data(self) -> None:
        """Asynchronously load accounts from the database via TaskRunner."""
        if not self.banking_service or not self.task_runner:
            return

        self.is_loading = True
        self.loading_changed.emit(True)

        query = self.search_query.strip()
        status_filter = self.status_filter
        page = self.current_page
        page_size = self.page_size

        def _fetch():
            return self.banking_service.list_accounts(
                search=query or None,
                status_filter=status_filter,
                page=page,
                page_size=page_size,
            )

        def _on_success(result: tuple[list[AccountDTO], int]):
            dtos, total_count = result
            self.accounts = dtos
            self.total_count = total_count
            self.total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1
            self.accounts_loaded.emit(
                self.accounts, self.total_count, self.current_page, self.total_pages
            )

        def _on_error(exc: Exception, tb: str):
            self.load_error.emit(str(exc))

        def _on_finished():
            self.is_loading = False
            self.loading_changed.emit(False)

        self.task_runner.run_async(
            _fetch,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )
