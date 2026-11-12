"""Ledger Explorer and Multi-Criteria Transaction Search View with CSV Export."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.transaction_dto import TransactionDTO
from novabank.ui.resources.icons import get_icon

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class LedgerExplorerView(QWidget):
    """Real-time financial ledger explorer offering multi-column filtering and CSV data export."""

    COLUMNS = [
        "Reference",
        "Timestamp",
        "Account",
        "Type",
        "Direction",
        "Amount",
        "Balance After",
        "Description",
    ]

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner

        self.current_page: int = 1
        self.page_size: int = 50
        self.total_count: int = 0
        self.current_transactions: list[TransactionDTO] = []
        self._is_loading: bool = False

        self._setup_ui()
        if self.banking_service and self.task_runner:
            self.refresh_data()

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.refresh_data()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # 1. Header Box
        header_card = QFrame()
        header_card.setProperty("class", "CardFrame")
        h_layout = QVBoxLayout(header_card)
        h_layout.setContentsMargins(16, 14, 16, 14)
        h_layout.setSpacing(4)

        title = QLabel("Ledger Explorer & Transaction Search")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #172033;")
        subtitle = QLabel(
            "Audit all ledger journal entries across customer accounts with multi-criteria filtering and CSV export."
        )
        subtitle.setStyleSheet("font-size: 12px; color: #64748B;")

        h_layout.addWidget(title)
        h_layout.addWidget(subtitle)
        layout.addWidget(header_card)

        # 2. Filter Bar
        filter_card = QFrame()
        filter_card.setProperty("class", "CardFrame")
        f_layout = QVBoxLayout(filter_card)
        f_layout.setContentsMargins(16, 12, 16, 12)
        f_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(12)

        # Account Filter
        acc_box = QVBoxLayout()
        acc_box.setSpacing(2)
        acc_lbl = QLabel("Account Number:")
        acc_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        self.acc_filter_edit = QLineEdit()
        self.acc_filter_edit.setPlaceholderText("Filter by 12-digit account...")
        self.acc_filter_edit.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        acc_box.addWidget(acc_lbl)
        acc_box.addWidget(self.acc_filter_edit)
        row1.addLayout(acc_box, stretch=2)

        # Type Filter
        type_box = QVBoxLayout()
        type_box.setSpacing(2)
        type_lbl = QLabel("Transaction Type:")
        type_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        self.type_combo = QComboBox()
        self.type_combo.addItems(
            ["ALL", "DEPOSIT", "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT", "INTEREST", "FEE"]
        )
        self.type_combo.setStyleSheet("font-size: 12px; padding: 4px;")
        type_box.addWidget(type_lbl)
        type_box.addWidget(self.type_combo)
        row1.addLayout(type_box, stretch=1)

        # Date Range
        start_box = QVBoxLayout()
        start_box.setSpacing(2)
        start_lbl = QLabel("From Date:")
        start_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setDate(QDate.currentDate().addDays(-90))
        start_box.addWidget(start_lbl)
        start_box.addWidget(self.start_date_edit)
        row1.addLayout(start_box, stretch=1)

        end_box = QVBoxLayout()
        end_box.setSpacing(2)
        end_lbl = QLabel("To Date:")
        end_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setDate(QDate.currentDate().addDays(1))
        end_box.addWidget(end_lbl)
        end_box.addWidget(self.end_date_edit)
        row1.addLayout(end_box, stretch=1)

        f_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)

        # Amount range
        min_box = QVBoxLayout()
        min_box.setSpacing(2)
        min_lbl = QLabel("Min Amount ($):")
        min_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        self.min_amount_edit = QLineEdit()
        self.min_amount_edit.setPlaceholderText("0.00")
        min_box.addWidget(min_lbl)
        min_box.addWidget(self.min_amount_edit)
        row2.addLayout(min_box, stretch=1)

        max_box = QVBoxLayout()
        max_box.setSpacing(2)
        max_lbl = QLabel("Max Amount ($):")
        max_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #475569;")
        self.max_amount_edit = QLineEdit()
        self.max_amount_edit.setPlaceholderText("Any")
        max_box.addWidget(max_lbl)
        max_box.addWidget(self.max_amount_edit)
        row2.addLayout(max_box, stretch=1)

        row2.addStretch(1)

        # Action Buttons
        btn_box = QHBoxLayout()
        btn_box.setSpacing(8)

        self.search_btn = QPushButton("Apply Filters")
        self.search_btn.setProperty("class", "PrimaryButton")
        self.search_btn.setIcon(get_icon("search", color="#FFFFFF", size=14))
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.clicked.connect(self._on_search_clicked)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setProperty("class", "SecondaryButton")
        self.reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.reset_btn.clicked.connect(self._on_reset_clicked)

        self.export_csv_btn = QPushButton("Export CSV")
        self.export_csv_btn.setProperty("class", "SecondaryButton")
        self.export_csv_btn.setIcon(get_icon("download", color="#172033", size=14))
        self.export_csv_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_csv_btn.clicked.connect(self._on_export_csv_clicked)

        btn_box.addWidget(self.search_btn)
        btn_box.addWidget(self.reset_btn)
        btn_box.addWidget(self.export_csv_btn)
        row2.addLayout(btn_box)

        f_layout.addLayout(row2)
        layout.addWidget(filter_card)

        # 3. Table
        self.table = QTableWidget()
        self.table.setColumnCount(len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(
            "QTableWidget { background-color: #FFFFFF; alternate-background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; font-size: 12px; }"
            "QHeaderView::section { background-color: #F8FAFC; color: #475569; font-weight: 600; border: none; padding: 8px 6px; border-bottom: 2px solid #E2E8F0; font-size: 11px; }"
            "QTableWidget::item { padding: 6px 8px; border-bottom: 1px solid #F1F5F9; }"
            "QTableWidget::item:selected { background-color: #EFF6FF; color: #1E3A8A; }"
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(0, 130)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(1, 135)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(2, 110)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(5, 120)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(6, 120)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table, stretch=1)

        # 4. Pagination & Status Bar
        footer = QHBoxLayout()
        footer.setContentsMargins(4, 2, 4, 2)

        self.count_lbl = QLabel("0 transactions found")
        self.count_lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
        footer.addWidget(self.count_lbl)
        footer.addStretch()

        self.prev_btn = QPushButton("◀ Prev")
        self.prev_btn.setProperty("class", "SecondaryButton")
        self.prev_btn.setEnabled(False)
        self.prev_btn.clicked.connect(self._on_prev_page)

        self.page_lbl = QLabel("Page 1 of 1")
        self.page_lbl.setStyleSheet("font-size: 12px; color: #172033; font-weight: 600; padding: 0 8px;")

        self.next_btn = QPushButton("Next ▶")
        self.next_btn.setProperty("class", "SecondaryButton")
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self._on_next_page)

        footer.addWidget(self.prev_btn)
        footer.addWidget(self.page_lbl)
        footer.addWidget(self.next_btn)

        layout.addLayout(footer)

    def _on_search_clicked(self) -> None:
        self.current_page = 1
        self.refresh_data()

    def _on_reset_clicked(self) -> None:
        self.acc_filter_edit.clear()
        self.type_combo.setCurrentIndex(0)
        self.start_date_edit.setDate(QDate.currentDate().addDays(-90))
        self.end_date_edit.setDate(QDate.currentDate().addDays(1))
        self.min_amount_edit.clear()
        self.max_amount_edit.clear()
        self.current_page = 1
        self.refresh_data()

    def _on_prev_page(self) -> None:
        if self.current_page > 1:
            self.current_page -= 1
            self.refresh_data()

    def _on_next_page(self) -> None:
        max_page = max(1, (self.total_count + self.page_size - 1) // self.page_size)
        if self.current_page < max_page:
            self.current_page += 1
            self.refresh_data()

    def refresh_data(self) -> None:
        """Fetch matching transactions asynchronously."""
        if not self.banking_service or not self.task_runner or self._is_loading:
            return

        self._is_loading = True
        self.search_btn.setEnabled(False)

        # Parse inputs
        acc_raw = self.acc_filter_edit.text().strip().replace("-", "").replace(" ", "")
        acc_num = acc_raw if len(acc_raw) == 12 else None

        t_type = self.type_combo.currentText().strip()
        tx_type = None if t_type == "ALL" else t_type

        # Dates
        s_qdate = self.start_date_edit.date()
        s_date = date(s_qdate.year(), s_qdate.month(), s_qdate.day())

        e_qdate = self.end_date_edit.date()
        e_date = date(e_qdate.year(), e_qdate.month(), e_qdate.day())

        # Amounts
        min_amt: Optional[Decimal] = None
        min_str = self.min_amount_edit.text().strip().replace("$", "").replace(",", "")
        if min_str:
            try:
                min_amt = Decimal(min_str)
            except InvalidOperation:
                pass

        max_amt: Optional[Decimal] = None
        max_str = self.max_amount_edit.text().strip().replace("$", "").replace(",", "")
        if max_str:
            try:
                max_amt = Decimal(max_str)
            except InvalidOperation:
                pass

        page = self.current_page
        page_sz = self.page_size

        def _do_search():
            return self.banking_service.search_transactions(
                account_number=acc_num,
                start_date=s_date,
                end_date=e_date,
                tx_type=tx_type,
                min_amount=min_amt,
                max_amount=max_amt,
                page=page,
                page_size=page_sz,
            )

        def _on_success(result: tuple[list[TransactionDTO], int]):
            try:
                txs, count = result
                self.current_transactions = txs
                self.total_count = count
                self._populate_table(txs, count)
            except RuntimeError:
                pass

        def _on_error(exc: Exception, tb: str):
            try:
                self.count_lbl.setText(f"Query error: {exc}")
            except RuntimeError:
                pass

        def _on_finished():
            try:
                self._is_loading = False
                self.search_btn.setEnabled(True)
            except RuntimeError:
                pass

        self.task_runner.run_async(
            _do_search,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def _populate_table(self, transactions: list[TransactionDTO], total_count: int) -> None:
        self.table.setRowCount(len(transactions))
        mono_font = QFont("Consolas", 10)

        for row_idx, tx in enumerate(transactions):
            # 0. Reference
            ref_item = QTableWidgetItem(tx.transaction_ref)
            ref_item.setFont(mono_font)
            ref_item.setForeground(QColor("#475569"))
            self.table.setItem(row_idx, 0, ref_item)

            # 1. Timestamp
            ts_str = tx.created_at.strftime("%Y-%m-%d %H:%M:%S")
            ts_item = QTableWidgetItem(ts_str)
            ts_item.setForeground(QColor("#64748B"))
            self.table.setItem(row_idx, 1, ts_item)

            # 2. Account
            acc_item = QTableWidgetItem(tx.account_number)
            acc_item.setFont(mono_font)
            acc_item.setForeground(QColor("#172033"))
            self.table.setItem(row_idx, 2, acc_item)

            # 3. Type
            type_item = QTableWidgetItem(tx.transaction_type)
            type_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row_idx, 3, type_item)

            # 4. Direction
            dir_item = QTableWidgetItem(tx.direction)
            dir_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if tx.direction == "CREDIT":
                dir_item.setForeground(QColor("#15803D"))
            else:
                dir_item.setForeground(QColor("#DC2626"))
            self.table.setItem(row_idx, 4, dir_item)

            # 5. Amount
            prefix = "+" if tx.direction == "CREDIT" else "-"
            amt_item = QTableWidgetItem(f"{prefix}${tx.amount:,.2f}")
            amt_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if tx.direction == "CREDIT":
                amt_item.setForeground(QColor("#15803D"))
            else:
                amt_item.setForeground(QColor("#DC2626"))
            amt_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            self.table.setItem(row_idx, 5, amt_item)

            # 6. Balance After
            bal_item = QTableWidgetItem(f"${tx.balance_after:,.2f}")
            bal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            bal_item.setFont(QFont("Consolas", 10))
            self.table.setItem(row_idx, 6, bal_item)

            # 7. Description
            desc_item = QTableWidgetItem(tx.description)
            desc_item.setForeground(QColor("#334155"))
            self.table.setItem(row_idx, 7, desc_item)

        # Update Pagination Controls
        max_page = max(1, (total_count + self.page_size - 1) // self.page_size)
        self.count_lbl.setText(f"{total_count:,} ledger transactions found")
        self.page_lbl.setText(f"Page {self.current_page} of {max_page}")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(self.current_page < max_page)

    def _on_export_csv_clicked(self) -> None:
        """Export current filtered results to CSV file."""
        if not self.current_transactions:
            QMessageBox.information(
                self, "Export CSV", "No transactions found matching current filter criteria."
            )
            return

        default_filename = f"novabank_ledger_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Ledger to CSV",
            default_filename,
            "CSV Files (*.csv);;All Files (*)",
        )

        if not file_path:
            return

        try:
            self.banking_service.export_ledger_csv(
                transactions=self.current_transactions,
                destination=file_path,
            )
            QMessageBox.information(
                self,
                "Export Complete",
                f"Successfully exported {len(self.current_transactions)} transactions to:\n{file_path}",
            )
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Failed to export CSV:\n{exc}")
