"""ViewModel coordinating audit log querying, filtering, pagination, and diff inspection."""

from __future__ import annotations

import math
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.audit_dto import AuditEventDTO

if TYPE_CHECKING:
    from novabank.application.services.audit_service import AuditService
    from novabank.ui.workers.task_runner import TaskRunner


class AuditLogViewModel(QObject):
    """ViewModel for querying immutable audit logs with multi-column filters."""

    events_loaded = Signal(list, int)  # (events, total_count)
    event_selected = Signal(object)  # AuditEventDTO
    loading_changed = Signal(bool)
    error_occurred = Signal(str)
    page_changed = Signal(int, int)  # (current_page, total_pages)

    CATEGORY_ALL = "ALL"
    CATEGORIES = [
        ("ALL", "All Categories"),
        ("ACCOUNT_CREATED", "Account Created"),
        ("ACCOUNT_UPDATED", "Account Updated"),
        ("ACCOUNT_CLOSED", "Account Closed"),
        ("DEPOSIT", "Cash Deposit"),
        ("WITHDRAWAL", "Cash Withdrawal"),
        ("TRANSFER", "Account Transfer"),
    ]

    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.audit_service = audit_service
        self.task_runner = task_runner

        # State
        self.events: list[AuditEventDTO] = []
        self.selected_event: Optional[AuditEventDTO] = None
        self.total_count: int = 0
        self.current_page: int = 1
        self.page_size: int = 25

        # Filters
        self.event_type_filter: str = self.CATEGORY_ALL
        self.entity_id_search: str = ""
        self.actor_filter: str = ""
        self.start_date: Optional[datetime] = None
        self.end_date: Optional[datetime] = None
        self._is_loading: bool = False

    def set_services(self, audit_service: AuditService, task_runner: TaskRunner) -> None:
        """Inject audit service and task runner dependencies."""
        self.audit_service = audit_service
        self.task_runner = task_runner

    @property
    def total_pages(self) -> int:
        """Calculate total number of available pages."""
        return max(1, math.ceil(self.total_count / self.page_size))

    def set_event_type_filter(self, category: str) -> None:
        """Set event category filter and reload from first page."""
        normalized = category.strip().upper()
        if self.event_type_filter != normalized:
            self.event_type_filter = normalized
            self.current_page = 1
            self.load_data()

    def set_entity_search(self, search_text: str) -> None:
        """Set entity ID search query and reload from first page."""
        clean = search_text.strip()
        if self.entity_id_search != clean:
            self.entity_id_search = clean
            self.current_page = 1
            self.load_data()

    def set_date_range(self, start: Optional[datetime], end: Optional[datetime]) -> None:
        """Apply date range constraints and reload from first page."""
        self.start_date = start
        self.end_date = end
        self.current_page = 1
        self.load_data()

    def select_event_by_index(self, index: int) -> None:
        """Select event by zero-based row index and emit for detail display."""
        if 0 <= index < len(self.events):
            self.selected_event = self.events[index]
            self.event_selected.emit(self.selected_event)
        else:
            self.selected_event = None

    def next_page(self) -> None:
        """Navigate to next page if available."""
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.load_data()

    def prev_page(self) -> None:
        """Navigate to previous page if available."""
        if self.current_page > 1:
            self.current_page -= 1
            self.load_data()

    def load_data(self) -> None:
        """Asynchronously query audit records on worker thread."""
        if not self.audit_service or not self.task_runner:
            return

        self._set_loading(True)

        ev_type = None if self.event_type_filter == self.CATEGORY_ALL else self.event_type_filter
        ent_id = self.entity_id_search if self.entity_id_search else None
        actor = self.actor_filter if self.actor_filter else None
        start = self.start_date
        end = self.end_date
        offset = (self.current_page - 1) * self.page_size
        limit = self.page_size

        def _fetch():
            return self.audit_service.query_events(
                start_date=start,
                end_date=end,
                event_type=ev_type,
                entity_id=ent_id,
                actor=actor,
                limit=limit,
                offset=offset,
            )

        def _on_success(result: tuple[list[AuditEventDTO], int]):
            items, total = result
            self.events = items
            self.total_count = total
            self.events_loaded.emit(items, total)
            self.page_changed.emit(self.current_page, self.total_pages)
            if items:
                self.select_event_by_index(0)
            else:
                self.selected_event = None

        def _on_error(exc: Exception, tb: str):
            self.error_occurred.emit(str(exc))

        def _on_finished():
            self._set_loading(False)

        self.task_runner.run_async(
            _fetch,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def _set_loading(self, is_loading: bool) -> None:
        if self._is_loading != is_loading:
            self._is_loading = is_loading
            self.loading_changed.emit(is_loading)
