"""Account List View displaying a searchable, paginated table of customer accounts."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.account_dto import AccountDTO
from novabank.ui.viewmodels.account_list_viewmodel import AccountListViewModel

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class AccountListView(QWidget):
    """View widget rendering searchable and paginated customer account table."""

    # Emitted when an account row is double-clicked for details inspection
    account_detail_requested = Signal(object)

    COLUMNS = [
        "Account Number",
        "Customer Name",
        "Phone Number",
        "City, State",
        "Status",
        "Current Balance",
        "Created Date",
    ]

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        viewmodel: Optional[AccountListViewModel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm = viewmodel or AccountListViewModel(banking_service, task_runner, parent=self)

        self._setup_ui()
        self._bind_viewmodel()

        # Initial load if services are connected
        if self.banking_service and self.task_runner:
            self.vm.load_data()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 28, 28, 28)
        main_layout.setSpacing(16)

        # Header Section
        header_layout = QHBoxLayout()
        header_text_layout = QVBoxLayout()
        header_text_layout.setSpacing(2)

        self.title_label = QLabel("Customer Accounts Directory")
        self.title_label.setStyleSheet("font-size: 22px; font-weight: bold; color: #f8fafc;")

        self.subtitle_label = QLabel(
            "Real-time registry of all customer accounts, balances, and operational statuses."
        )
        self.subtitle_label.setStyleSheet("font-size: 13px; color: #94a3b8;")

        header_text_layout.addWidget(self.title_label)
        header_text_layout.addWidget(self.subtitle_label)
        header_layout.addLayout(header_text_layout)
        header_layout.addStretch()

        self.total_badge = QLabel("0 accounts")
        self.total_badge.setStyleSheet(
            "background-color: #1e293b; color: #38bdf8; font-weight: bold; padding: 6px 14px; border-radius: 12px; border: 1px solid #334155;"
        )
        header_layout.addWidget(self.total_badge)
        main_layout.addLayout(header_layout)

        # Search & Filter Toolbar
        toolbar_card = QFrame()
        toolbar_card.setStyleSheet(
            "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 6px 12px; }"
        )
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        toolbar_layout.setSpacing(12)

        # Search Bar
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(
            "Search by account number, customer name, phone, or city..."
        )
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setStyleSheet(
            "QLineEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 12px; color: #f8fafc; font-size: 13px; min-width: 340px; }"
        )
        toolbar_layout.addWidget(self.search_edit, stretch=2)

        # Filter Segment Buttons
        filter_label = QLabel("Status:")
        filter_label.setStyleSheet("color: #94a3b8; font-weight: 500;")
        toolbar_layout.addWidget(filter_label)

        self.filter_group = QButtonGroup(self)
        self.filter_group.setExclusive(True)

        self.btn_all = QPushButton("All")
        self.btn_active = QPushButton("Active Only")
        self.btn_closed = QPushButton("Closed Only")

        for btn in (self.btn_all, self.btn_active, self.btn_closed):
            btn.setCheckable(True)
            btn.setStyleSheet(
                "QPushButton { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 6px 12px; color: #cbd5e1; }"
                "QPushButton:checked { background-color: #2563eb; color: #ffffff; border-color: #3b82f6; font-weight: bold; }"
            )
            self.filter_group.addButton(btn)
            toolbar_layout.addWidget(btn)

        self.btn_all.setChecked(True)

        # Refresh Button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet(
            "QPushButton { background-color: #334155; border-radius: 6px; padding: 6px 14px; color: #f8fafc; font-weight: 500; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        toolbar_layout.addWidget(self.refresh_btn)

        main_layout.addWidget(toolbar_card)

        # Table Section
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setStyleSheet(
            "QTableWidget { background-color: #0f172a; alternate-background-color: #1e293b; gridline-color: transparent; border: 1px solid #334155; border-radius: 8px; color: #f8fafc; font-size: 13px; }"
            "QHeaderView::section { background-color: #1e293b; color: #94a3b8; padding: 10px 8px; font-weight: bold; border: none; border-bottom: 2px solid #334155; }"
            "QTableWidget::item { padding: 8px; }"
            "QTableWidget::item:selected { background-color: #1d4ed8; color: #ffffff; }"
        )
        main_layout.addWidget(self.table, stretch=1)

        # Pagination & Status Footer
        footer_layout = QHBoxLayout()
        footer_layout.setContentsMargins(0, 4, 0, 0)
        footer_layout.setSpacing(12)

        self.loading_indicator = QLabel("")
        self.loading_indicator.setStyleSheet("color: #38bdf8; font-weight: 500;")
        footer_layout.addWidget(self.loading_indicator)
        footer_layout.addStretch()

        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.setEnabled(False)
        self.prev_btn.setStyleSheet(
            "padding: 6px 14px; border-radius: 6px; background-color: #1e293b; border: 1px solid #334155; color: #cbd5e1;"
        )
        footer_layout.addWidget(self.prev_btn)

        self.page_info_label = QLabel("Page 1 of 1")
        self.page_info_label.setStyleSheet("color: #94a3b8; font-weight: 500;")
        footer_layout.addWidget(self.page_info_label)

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setEnabled(False)
        self.next_btn.setStyleSheet(
            "padding: 6px 14px; border-radius: 6px; background-color: #1e293b; border: 1px solid #334155; color: #cbd5e1;"
        )
        footer_layout.addWidget(self.next_btn)

        main_layout.addLayout(footer_layout)

    def _bind_viewmodel(self) -> None:
        # User input -> ViewModel
        self.search_edit.textChanged.connect(self.vm.set_search_query)

        self.btn_all.clicked.connect(lambda: self.vm.set_status_filter("ALL"))
        self.btn_active.clicked.connect(lambda: self.vm.set_status_filter("ACTIVE"))
        self.btn_closed.clicked.connect(lambda: self.vm.set_status_filter("CLOSED"))

        self.refresh_btn.clicked.connect(self.vm.refresh)
        self.prev_btn.clicked.connect(self.vm.prev_page)
        self.next_btn.clicked.connect(self.vm.next_page)

        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        # ViewModel -> View updates
        self.vm.loading_changed.connect(self._on_loading_changed)
        self.vm.accounts_loaded.connect(self._populate_table)
        self.vm.load_error.connect(self._on_load_error)
        self.vm.account_selected.connect(self.account_detail_requested.emit)

    def _on_cell_double_clicked(self, row: int, column: int) -> None:
        self.vm.select_account_at_index(row)

    def _on_loading_changed(self, is_loading: bool) -> None:
        if is_loading:
            self.loading_indicator.setText("Loading accounts...")
            self.refresh_btn.setEnabled(False)
        else:
            self.loading_indicator.setText("")
            self.refresh_btn.setEnabled(True)

    def _on_load_error(self, error_msg: str) -> None:
        self.loading_indicator.setText(f"Error loading accounts: {error_msg}")

    def _populate_table(
        self,
        accounts: list[AccountDTO],
        total_count: int,
        page: int,
        total_pages: int,
    ) -> None:
        self.table.setRowCount(len(accounts))

        for row, acc in enumerate(accounts):
            # 1. Account Number (Formatted)
            acc_num = f"{acc.account_number[:4]}-{acc.account_number[4:8]}-{acc.account_number[8:]}"
            item_num = QTableWidgetItem(acc_num)
            item_num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 0, item_num)

            # 2. Customer Name
            item_name = QTableWidgetItem(acc.holder_name)
            self.table.setItem(row, 1, item_name)

            # 3. Phone Number
            item_phone = QTableWidgetItem(acc.phone_number)
            item_phone.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 2, item_phone)

            # 4. Location
            location = f"{acc.city}, {acc.state}"
            item_loc = QTableWidgetItem(location)
            self.table.setItem(row, 3, item_loc)

            # 5. Status
            status_text = "● Active" if acc.is_active else "○ Closed"
            item_status = QTableWidgetItem(status_text)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if acc.is_active:
                item_status.setForeground(Qt.GlobalColor.green)
            else:
                item_status.setForeground(Qt.GlobalColor.red)
            self.table.setItem(row, 4, item_status)

            # 6. Balance
            balance_str = f"${acc.balance:,.2f} {acc.currency}"
            item_balance = QTableWidgetItem(balance_str)
            item_balance.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            self.table.setItem(row, 5, item_balance)

            # 7. Created Date
            date_str = acc.created_at.strftime("%Y-%m-%d") if acc.created_at else ""
            item_date = QTableWidgetItem(date_str)
            item_date.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 6, item_date)

        # Update summary labels
        self.total_badge.setText(f"{total_count} account{'s' if total_count != 1 else ''}")
        self.page_info_label.setText(f"Page {page} of {total_pages}")
        self.prev_btn.setEnabled(page > 1)
        self.next_btn.setEnabled(page < total_pages)
