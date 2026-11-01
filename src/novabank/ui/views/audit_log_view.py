"""Administrative Audit Trail Viewer with searchable ledger and JSON diff inspector."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.audit_dto import AuditEventDTO
from novabank.ui.viewmodels.audit_log_viewmodel import AuditLogViewModel

if TYPE_CHECKING:
    from novabank.application.services.audit_service import AuditService
    from novabank.ui.workers.task_runner import TaskRunner


class AuditLogView(QWidget):
    """Compliance audit viewer allowing administrators to inspect system events and payload diffs."""

    COLUMNS = [
        "Timestamp",
        "Event Category",
        "Entity Type",
        "Entity ID",
        "Actor",
    ]

    def __init__(
        self,
        audit_service: Optional[AuditService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.vm = AuditLogViewModel(audit_service, task_runner, parent=self)

        self._build_ui()
        self._bind_viewmodel()

        # Initial load if services provided
        if audit_service and task_runner:
            self.vm.load_data()

    def set_services(self, audit_service: AuditService, task_runner: TaskRunner) -> None:
        """Inject backend services dynamically."""
        self.vm.set_services(audit_service, task_runner)
        self.vm.load_data()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # 1. Header Row
        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title_lbl = QLabel("Audit Trail & Compliance Ledger")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: #f8fafc;")
        subtitle_lbl = QLabel(
            "Immutable audit log tracking all account creation, modifications, transfers, and transactions."
        )
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #94a3b8;")

        header_text.addWidget(title_lbl)
        header_text.addWidget(subtitle_lbl)
        header_layout.addLayout(header_text)
        header_layout.addStretch()

        self.compliance_badge = QLabel("🛡️ Immutable Log")
        self.compliance_badge.setStyleSheet(
            "background-color: #064e3b; color: #34d399; font-weight: bold; padding: 6px 14px; border-radius: 12px; font-size: 12px;"
        )
        header_layout.addWidget(self.compliance_badge)
        main_layout.addLayout(header_layout)

        # 2. Filter Toolbar Card
        filter_card = self._create_card()
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(14, 10, 14, 10)
        filter_layout.setSpacing(10)

        # Category Filter
        cat_lbl = QLabel("Category:")
        cat_lbl.setStyleSheet("color: #cbd5e1; font-weight: 500; font-size: 12px;")
        filter_layout.addWidget(cat_lbl)

        self.category_combo = QComboBox()
        for cat_code, cat_label in AuditLogViewModel.CATEGORIES:
            self.category_combo.addItem(cat_label, cat_code)
        self.category_combo.setStyleSheet(
            "QComboBox { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 5px 10px; color: #f8fafc; font-size: 12px; min-width: 140px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background-color: #1e293b; color: #f8fafc; selection-background-color: #2563eb; }"
        )
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        filter_layout.addWidget(self.category_combo)

        # Entity ID Search
        search_lbl = QLabel("Entity ID:")
        search_lbl.setStyleSheet("color: #cbd5e1; font-weight: 500; font-size: 12px;")
        filter_layout.addWidget(search_lbl)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Filter by Account No or Ref...")
        self.search_edit.setStyleSheet(
            "QLineEdit { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 5px 10px; color: #f8fafc; font-size: 12px; max-width: 220px; }"
        )
        self.search_edit.textChanged.connect(self._on_search_text_changed)
        filter_layout.addWidget(self.search_edit)

        # Date Pickers
        from_lbl = QLabel("From:")
        from_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setDate(QDate.currentDate().addDays(-30))
        self.start_date_edit.setStyleSheet(
            "QDateEdit { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 4px 8px; color: #f8fafc; font-size: 12px; }"
        )

        to_lbl = QLabel("To:")
        to_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setStyleSheet(
            "QDateEdit { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 4px 8px; color: #f8fafc; font-size: 12px; }"
        )

        self.btn_apply_date = QPushButton("Filter Dates")
        self.btn_apply_date.setStyleSheet(
            "QPushButton { background-color: #2563eb; border-radius: 6px; padding: 5px 12px; color: #ffffff; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
        )
        self.btn_apply_date.clicked.connect(self._on_apply_dates_clicked)

        self.btn_clear_date = QPushButton("All Dates")
        self.btn_clear_date.setStyleSheet(
            "QPushButton { background-color: #334155; border-radius: 6px; padding: 5px 10px; color: #cbd5e1; font-size: 12px; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.btn_clear_date.clicked.connect(self._on_clear_dates_clicked)

        filter_layout.addWidget(from_lbl)
        filter_layout.addWidget(self.start_date_edit)
        filter_layout.addWidget(to_lbl)
        filter_layout.addWidget(self.end_date_edit)
        filter_layout.addWidget(self.btn_apply_date)
        filter_layout.addWidget(self.btn_clear_date)
        filter_layout.addStretch()

        self.loading_indicator = QLabel("")
        self.loading_indicator.setStyleSheet("color: #94a3b8; font-style: italic;")
        filter_layout.addWidget(self.loading_indicator)

        self.btn_refresh = QPushButton("🔄 Refresh")
        self.btn_refresh.setStyleSheet(
            "QPushButton { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 5px 12px; color: #f8fafc; font-size: 12px; }"
            "QPushButton:hover { background-color: #1e293b; }"
        )
        self.btn_refresh.clicked.connect(lambda: self.vm.load_data())
        filter_layout.addWidget(self.btn_refresh)

        main_layout.addWidget(filter_card)

        # 3. Splitter: Left Table | Right JSON Inspector
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet(
            "QSplitter::handle { background-color: #334155; width: 2px; margin: 4px; }"
        )

        # 3A. Left Table Section
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #1e293b; alternate-background-color: #0f172a; border: 1px solid #334155; border-radius: 8px; color: #f8fafc; font-size: 12px; }"
            "QHeaderView::section { background-color: #0f172a; color: #94a3b8; font-weight: bold; border: none; padding: 8px 6px; border-bottom: 2px solid #334155; font-size: 11px; }"
            "QTableWidget::item { padding: 6px; }"
            "QTableWidget::item:selected { background-color: #2563eb; color: #ffffff; }"
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        splitter.addWidget(self.table)

        # 3B. Right JSON Inspector Panel
        inspector_card = self._create_card()
        inspector_layout = QVBoxLayout(inspector_card)
        inspector_layout.setContentsMargins(14, 12, 14, 12)
        inspector_layout.setSpacing(8)

        self.inspector_title = QLabel("Event Payload Inspector")
        self.inspector_title.setStyleSheet("color: #38bdf8; font-weight: bold; font-size: 14px;")
        inspector_layout.addWidget(self.inspector_title)

        self.inspector_meta = QLabel(
            "Select an event from the ledger table to view its state diff."
        )
        self.inspector_meta.setStyleSheet("color: #94a3b8; font-size: 11px;")
        inspector_layout.addWidget(self.inspector_meta)

        self.json_viewer = QPlainTextEdit()
        self.json_viewer.setReadOnly(True)
        self.json_viewer.setFont(QFont("Consolas", 10))
        self.json_viewer.setStyleSheet(
            "QPlainTextEdit { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #34d399; padding: 10px; font-family: monospace; }"
        )
        self.json_viewer.setPlaceholderText("No event selected.")
        inspector_layout.addWidget(self.json_viewer, stretch=1)

        splitter.addWidget(inspector_card)
        splitter.setSizes([650, 450])
        main_layout.addWidget(splitter, stretch=1)

        # 4. Pagination Footer Bar
        footer_layout = QHBoxLayout()
        self.total_badge = QLabel("0 total audit events")
        self.total_badge.setStyleSheet("color: #94a3b8; font-size: 12px;")
        footer_layout.addWidget(self.total_badge)
        footer_layout.addStretch()

        self.btn_prev = QPushButton("◀ Prev")
        self.btn_prev.setStyleSheet(
            "QPushButton { background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 4px 10px; color: #cbd5e1; font-size: 12px; }"
            "QPushButton:hover:enabled { background-color: #334155; }"
            "QPushButton:disabled { color: #64748b; }"
        )
        self.btn_prev.clicked.connect(self.vm.prev_page)

        self.page_info_label = QLabel("Page 1 of 1")
        self.page_info_label.setStyleSheet("color: #f8fafc; font-size: 12px; margin: 0 8px;")

        self.btn_next = QPushButton("Next ▶")
        self.btn_next.setStyleSheet(
            "QPushButton { background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; padding: 4px 10px; color: #cbd5e1; font-size: 12px; }"
            "QPushButton:hover:enabled { background-color: #334155; }"
            "QPushButton:disabled { color: #64748b; }"
        )
        self.btn_next.clicked.connect(self.vm.next_page)

        footer_layout.addWidget(self.btn_prev)
        footer_layout.addWidget(self.page_info_label)
        footer_layout.addWidget(self.btn_next)
        main_layout.addLayout(footer_layout)

    def _create_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; }"
        )
        return card

    def _bind_viewmodel(self) -> None:
        self.vm.events_loaded.connect(self._on_events_loaded)
        self.vm.event_selected.connect(self._on_event_selected)
        self.vm.loading_changed.connect(self._on_loading_changed)
        self.vm.error_occurred.connect(self._on_error_occurred)
        self.vm.page_changed.connect(self._on_page_changed)

    def _on_category_changed(self, index: int) -> None:
        cat_code = self.category_combo.currentData()
        if cat_code:
            self.vm.set_event_type_filter(cat_code)

    def _on_search_text_changed(self, text: str) -> None:
        self.vm.set_entity_search(text)

    def _on_apply_dates_clicked(self) -> None:
        sq = self.start_date_edit.date()
        eq = self.end_date_edit.date()
        s_date = datetime(sq.year(), sq.month(), sq.day(), 0, 0, 0)
        e_date = datetime(eq.year(), eq.month(), eq.day(), 23, 59, 59)
        self.vm.set_date_range(s_date, e_date)

    def _on_clear_dates_clicked(self) -> None:
        self.vm.set_date_range(None, None)

    def _on_table_selection_changed(self) -> None:
        selected_rows = self.table.selectionModel().selectedRows()
        if selected_rows:
            row_idx = selected_rows[0].row()
            self.vm.select_event_by_index(row_idx)

    def _on_events_loaded(self, events: list[AuditEventDTO], total_count: int) -> None:
        self.table.setRowCount(len(events))
        for row_idx, ev in enumerate(events):
            item_ts = QTableWidgetItem(ev.formatted_timestamp)
            item_cat = QTableWidgetItem(ev.event_type)
            item_ent = QTableWidgetItem(ev.entity_type)
            item_eid = QTableWidgetItem(ev.entity_id)
            item_act = QTableWidgetItem(ev.actor)

            # Styling badges by event type
            if "CREATED" in ev.event_type:
                item_cat.setForeground(Qt.GlobalColor.cyan)
            elif "DEPOSIT" in ev.event_type:
                item_cat.setForeground(Qt.GlobalColor.green)
            elif "WITHDRAWAL" in ev.event_type:
                item_cat.setForeground(Qt.GlobalColor.red)
            elif "CLOSED" in ev.event_type:
                item_cat.setForeground(Qt.GlobalColor.gray)
            elif "TRANSFER" in ev.event_type:
                item_cat.setForeground(Qt.GlobalColor.yellow)

            self.table.setItem(row_idx, 0, item_ts)
            self.table.setItem(row_idx, 1, item_cat)
            self.table.setItem(row_idx, 2, item_ent)
            self.table.setItem(row_idx, 3, item_eid)
            self.table.setItem(row_idx, 4, item_act)

        self.total_badge.setText(f"{total_count} total audit events")
        if events:
            self.table.selectRow(0)
        else:
            self.json_viewer.clear()
            self.inspector_title.setText("Event Payload Inspector")
            self.inspector_meta.setText("No audit events found matching criteria.")

    def _on_event_selected(self, ev: Optional[AuditEventDTO]) -> None:
        if ev:
            self.inspector_title.setText(f"Event #{ev.event_id}: {ev.event_type}")
            self.inspector_meta.setText(
                f"Actor: {ev.actor}  •  Entity: {ev.entity_type} [{ev.entity_id}]  •  {ev.formatted_timestamp}"
            )
            self.json_viewer.setPlainText(ev.formatted_json)
        else:
            self.inspector_title.setText("Event Payload Inspector")
            self.inspector_meta.setText(
                "Select an event from the ledger table to view its state diff."
            )
            self.json_viewer.clear()

    def _on_page_changed(self, current: int, total: int) -> None:
        self.page_info_label.setText(f"Page {current} of {total}")
        self.btn_prev.setEnabled(current > 1)
        self.btn_next.setEnabled(current < total)

    def _on_loading_changed(self, is_loading: bool) -> None:
        self.btn_refresh.setEnabled(not is_loading)
        self.loading_indicator.setText("Loading audit trail..." if is_loading else "")

    def _on_error_occurred(self, err_msg: str) -> None:
        QMessageBox.warning(self, "Audit Trail Error", err_msg)
