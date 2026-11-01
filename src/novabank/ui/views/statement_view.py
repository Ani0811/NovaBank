"""Account Statement View providing date filter presets, summary KPI metrics, and ledger table."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
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

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.statement_dto import AccountStatementDTO, StatementEntryDTO
from novabank.ui.viewmodels.statement_viewmodel import StatementViewModel

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class StatementView(QWidget):
    """Interactive statement explorer and transaction ledger viewer with mathematical reconciliations."""

    COLUMNS = [
        "Date & Time",
        "Reference ID",
        "Type",
        "Description",
        "Debit (-)",
        "Credit (+)",
        "Running Balance",
    ]

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        viewmodel: Optional[StatementViewModel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm = viewmodel or StatementViewModel(banking_service, task_runner, parent=self)

        self._setup_ui()
        self._bind_viewmodel()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 24, 28, 24)
        main_layout.setSpacing(14)

        # 1. Header Section
        header_layout = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(2)

        title_lbl = QLabel("Account Statements & Ledger Explorer")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #f8fafc;")

        subtitle_lbl = QLabel(
            "Inspect verified ledger statements with period filtering, running balance reconciliations, and audit metrics."
        )
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #94a3b8;")

        header_text.addWidget(title_lbl)
        header_text.addWidget(subtitle_lbl)
        header_layout.addLayout(header_text)
        header_layout.addStretch()

        self.reconciliation_badge = QLabel("✓ Reconciled")
        self.reconciliation_badge.setVisible(False)
        self.reconciliation_badge.setStyleSheet(
            "background-color: #064e3b; color: #34d399; font-weight: bold; padding: 6px 16px; border-radius: 12px; font-size: 12px;"
        )
        header_layout.addWidget(self.reconciliation_badge)

        self.btn_export_csv = QPushButton("⬇ Export CSV")
        self.btn_export_csv.setEnabled(False)
        self.btn_export_csv.setStyleSheet(
            "QPushButton { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 6px 14px; color: #f8fafc; font-weight: 500; font-size: 13px; }"
            "QPushButton:hover:enabled { background-color: #1e293b; border-color: #38bdf8; }"
            "QPushButton:disabled { background-color: #1e293b; color: #64748b; border-color: #334155; }"
        )
        self.btn_export_csv.clicked.connect(self._on_export_csv_clicked)
        header_layout.addWidget(self.btn_export_csv)

        self.btn_export_pdf = QPushButton("⬇ Export PDF")
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_pdf.setStyleSheet(
            "QPushButton { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 6px 14px; color: #f8fafc; font-weight: 500; font-size: 13px; }"
            "QPushButton:hover:enabled { background-color: #1e293b; border-color: #38bdf8; }"
            "QPushButton:disabled { background-color: #1e293b; color: #64748b; border-color: #334155; }"
        )
        self.btn_export_pdf.clicked.connect(self._on_export_pdf_clicked)
        header_layout.addWidget(self.btn_export_pdf)

        main_layout.addLayout(header_layout)

        # 2. Account Lookup & Toolbar Card
        toolbar_card = self._create_card()
        toolbar_layout = QVBoxLayout(toolbar_card)
        toolbar_layout.setSpacing(12)

        # 2A. Account Selector Row
        acc_row = QHBoxLayout()
        acc_row.setSpacing(8)

        acc_title = QLabel("Account:")
        acc_title.setStyleSheet("color: #cbd5e1; font-weight: 500; font-size: 13px;")
        acc_row.addWidget(acc_title)

        self.account_edit = QLineEdit()
        self.account_edit.setPlaceholderText("Enter 12-digit Account Number...")
        self.account_edit.setStyleSheet(
            "QLineEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 6px 12px; color: #f8fafc; font-family: monospace; font-size: 13px; max-width: 240px; }"
        )
        acc_row.addWidget(self.account_edit)

        self.lookup_btn = QPushButton("Lookup Account")
        self.lookup_btn.setStyleSheet(
            "QPushButton { background-color: #334155; border-radius: 6px; padding: 6px 14px; color: #f8fafc; font-weight: 500; font-size: 13px; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.lookup_btn.clicked.connect(self._on_lookup_clicked)
        acc_row.addWidget(self.lookup_btn)

        self.account_info_lbl = QLabel("")
        self.account_info_lbl.setStyleSheet(
            "color: #38bdf8; font-weight: bold; font-size: 13px; margin-left: 12px;"
        )
        acc_row.addWidget(self.account_info_lbl)
        acc_row.addStretch()

        self.loading_indicator = QLabel("")
        self.loading_indicator.setStyleSheet("color: #94a3b8; font-style: italic;")
        acc_row.addWidget(self.loading_indicator)

        toolbar_layout.addLayout(acc_row)

        self.account_error = QLabel("")
        self.account_error.setStyleSheet("color: #f87171; font-size: 11px;")
        self.account_error.setVisible(False)
        toolbar_layout.addWidget(self.account_error)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #334155; margin-top: 2px; margin-bottom: 2px;")
        toolbar_layout.addWidget(divider)

        # 2B. Period Filter Presets Row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)

        filter_lbl = QLabel("Date Period:")
        filter_lbl.setStyleSheet("color: #94a3b8; font-weight: 500; font-size: 13px;")
        filter_row.addWidget(filter_lbl)

        self.preset_group = QButtonGroup(self)
        self.preset_group.setExclusive(True)

        self.btn_this_month = QPushButton("This Month")
        self.btn_today = QPushButton("Today")
        self.btn_last_7 = QPushButton("Last 7 Days")
        self.btn_ytd = QPushButton("Year to Date")
        self.btn_all_time = QPushButton("All Time")
        self.btn_custom = QPushButton("Custom Range")

        presets = [
            (self.btn_this_month, StatementViewModel.PRESET_THIS_MONTH),
            (self.btn_today, StatementViewModel.PRESET_TODAY),
            (self.btn_last_7, StatementViewModel.PRESET_LAST_7_DAYS),
            (self.btn_ytd, StatementViewModel.PRESET_YTD),
            (self.btn_all_time, StatementViewModel.PRESET_ALL_TIME),
            (self.btn_custom, StatementViewModel.PRESET_CUSTOM),
        ]

        for btn, preset_code in presets:
            btn.setCheckable(True)
            btn.setProperty("preset_code", preset_code)
            btn.setStyleSheet(
                "QPushButton { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 6px 12px; color: #cbd5e1; font-size: 12px; }"
                "QPushButton:checked { background-color: #0284c7; color: #ffffff; border-color: #38bdf8; font-weight: bold; }"
                "QPushButton:hover:!checked { background-color: #1e293b; color: #f8fafc; }"
            )
            self.preset_group.addButton(btn)
            filter_row.addWidget(btn)

        self.btn_this_month.setChecked(True)
        self.preset_group.buttonClicked.connect(self._on_preset_clicked)
        filter_row.addStretch()

        # 2C. Custom Date Controls
        self.custom_container = QWidget()
        custom_layout = QHBoxLayout(self.custom_container)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(6)

        from_lbl = QLabel("From:")
        from_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setStyleSheet(
            "QDateEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 4px 8px; color: #f8fafc; font-size: 12px; }"
        )

        to_lbl = QLabel("To:")
        to_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setStyleSheet(
            "QDateEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 4px 8px; color: #f8fafc; font-size: 12px; }"
        )

        self.apply_custom_btn = QPushButton("Apply")
        self.apply_custom_btn.setStyleSheet(
            "QPushButton { background-color: #2563eb; border-radius: 6px; padding: 4px 12px; color: #ffffff; font-weight: bold; font-size: 12px; }"
            "QPushButton:hover { background-color: #1d4ed8; }"
        )
        self.apply_custom_btn.clicked.connect(self._on_apply_custom_clicked)

        custom_layout.addWidget(from_lbl)
        custom_layout.addWidget(self.start_date_edit)
        custom_layout.addWidget(to_lbl)
        custom_layout.addWidget(self.end_date_edit)
        custom_layout.addWidget(self.apply_custom_btn)

        # Set default date edit values
        today_qdate = QDate.currentDate()
        self.start_date_edit.setDate(QDate(today_qdate.year(), today_qdate.month(), 1))
        self.end_date_edit.setDate(today_qdate)
        self.custom_container.setEnabled(False)  # enabled only when Custom is picked

        filter_row.addWidget(self.custom_container)
        toolbar_layout.addLayout(filter_row)

        main_layout.addWidget(toolbar_card)

        # 3. Summary KPI Cards Strip
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.card_opening = self._create_kpi_card(
            "Opening Balance", "$0.00 USD", "Prior to period start", "#94a3b8"
        )
        self.card_credits = self._create_kpi_card(
            "Total Inflow", "$0.00 USD", "Credits deposited / received", "#34d399"
        )
        self.card_debits = self._create_kpi_card(
            "Total Outflow", "$0.00 USD", "Debits withdrawn / sent", "#f87171"
        )
        self.card_closing = self._create_kpi_card(
            "Ending Balance", "$0.00 USD", "Period closing balance", "#38bdf8"
        )

        cards_layout.addWidget(self.card_opening)
        cards_layout.addWidget(self.card_credits)
        cards_layout.addWidget(self.card_debits)
        cards_layout.addWidget(self.card_closing)
        main_layout.addLayout(cards_layout)

        # 4. Table Section
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
            "QTableWidget { background-color: #1e293b; alternate-background-color: #0f172a; border: 1px solid #334155; border-radius: 8px; color: #f8fafc; font-size: 13px; }"
            "QHeaderView::section { background-color: #0f172a; color: #94a3b8; font-weight: bold; border: none; padding: 10px 8px; border-bottom: 2px solid #334155; font-size: 12px; }"
            "QTableWidget::item { padding: 6px 8px; }"
            "QTableWidget::item:selected { background-color: #2563eb; color: #ffffff; }"
        )

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Date
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Ref
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Type
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)  # Description
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Debit
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)  # Credit
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)  # Running Balance

        main_layout.addWidget(self.table, stretch=1)

        # 5. Footer / Status Row
        footer_layout = QHBoxLayout()
        self.tx_count_lbl = QLabel("0 transactions in period")
        self.tx_count_lbl.setStyleSheet("color: #94a3b8; font-size: 12px;")
        footer_layout.addWidget(self.tx_count_lbl)
        footer_layout.addStretch()

        self.statement_period_lbl = QLabel("")
        self.statement_period_lbl.setStyleSheet(
            "color: #cbd5e1; font-size: 12px; font-weight: 500;"
        )
        footer_layout.addWidget(self.statement_period_lbl)

        main_layout.addLayout(footer_layout)

    def _create_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px; }"
        )
        return card

    def _create_kpi_card(
        self, title: str, initial_value: str, subtitle: str, color_hex: str
    ) -> QFrame:
        card = QFrame()
        card.setObjectName(f"kpi_card_{title.replace(' ', '_').lower()}")
        card.setStyleSheet(
            "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px; }"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(3)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "color: #94a3b8; font-size: 11px; font-weight: bold; text-transform: uppercase; letter-spacing: 0.5px;"
        )

        val_lbl = QLabel(initial_value)
        val_lbl.setObjectName("kpi_value")
        val_lbl.setStyleSheet(f"color: {color_hex}; font-size: 20px; font-weight: bold;")

        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet("color: #64748b; font-size: 11px;")

        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)
        layout.addWidget(sub_lbl)
        return card

    def _bind_viewmodel(self) -> None:
        self.account_edit.textChanged.connect(self._on_account_text_changed)
        self.vm.account_found.connect(self._on_account_found)
        self.vm.account_lookup_failed.connect(self._on_account_lookup_failed)
        self.vm.statement_loaded.connect(self._on_statement_loaded)
        self.vm.statement_exported.connect(self._on_statement_exported)
        self.vm.export_failed.connect(self._on_export_failed)
        self.vm.loading_changed.connect(self._on_loading_changed)
        self.vm.error_occurred.connect(self._on_error_occurred)
        self.vm.filter_preset_changed.connect(self._on_filter_preset_changed)

    def _on_account_text_changed(self, text: str) -> None:
        clean = text.strip().replace("-", "").replace(" ", "")
        if len(clean) == 12:
            self.vm.lookup_account(clean)
        else:
            self.account_info_lbl.setText("")
            self.account_error.setVisible(False)

    def _on_lookup_clicked(self) -> None:
        self.vm.lookup_account(self.account_edit.text())

    def _on_preset_clicked(self, button: QPushButton) -> None:
        preset_code = button.property("preset_code")
        if preset_code == StatementViewModel.PRESET_CUSTOM:
            self.custom_container.setEnabled(True)
        else:
            self.custom_container.setEnabled(False)
            self.vm.select_preset(preset_code)

    def _on_apply_custom_clicked(self) -> None:
        start_qdate = self.start_date_edit.date()
        end_qdate = self.end_date_edit.date()
        start = date(start_qdate.year(), start_qdate.month(), start_qdate.day())
        end = date(end_qdate.year(), end_qdate.month(), end_qdate.day())
        self.vm.set_custom_date_range(start, end)

    def _on_filter_preset_changed(
        self, preset_name: str, start_date: Optional[date], end_date: Optional[date]
    ) -> None:
        if start_date:
            self.start_date_edit.setDate(QDate(start_date.year, start_date.month, start_date.day))
        if end_date:
            self.end_date_edit.setDate(QDate(end_date.year, end_date.month, end_date.day))

    def _on_account_found(self, acc: AccountDTO) -> None:
        self.account_error.setVisible(False)
        status_symbol = "● Active" if acc.is_active else "○ Closed"
        self.account_info_lbl.setText(
            f"{acc.holder_name}  •  {status_symbol}  •  Current Bal: ${acc.balance:,.2f} {acc.currency}"
        )
        self.account_info_lbl.setStyleSheet(
            "color: #34d399; font-weight: bold; font-size: 13px; margin-left: 12px;"
            if acc.is_active
            else "color: #f87171; font-weight: bold; font-size: 13px; margin-left: 12px;"
        )

    def _on_account_lookup_failed(self, error_msg: str) -> None:
        self.account_info_lbl.setText("")
        self.account_error.setText(error_msg)
        self.account_error.setVisible(True)
        self.reconciliation_badge.setVisible(False)
        self.btn_export_csv.setEnabled(False)
        self.btn_export_pdf.setEnabled(False)
        self.table.setRowCount(0)
        self._update_kpi_cards(
            Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), Decimal("0.00"), "USD"
        )

    def _on_loading_changed(self, is_loading: bool) -> None:
        self.lookup_btn.setEnabled(not is_loading)
        self.loading_indicator.setText("Loading statement..." if is_loading else "")

    def _on_error_occurred(self, error_msg: str) -> None:
        self.reconciliation_badge.setVisible(False)
        QMessageBox.warning(self, "Statement Error", error_msg)

    def _on_statement_loaded(self, statement: AccountStatementDTO) -> None:
        self.reconciliation_badge.setVisible(statement.is_reconciled())
        self.btn_export_csv.setEnabled(True)
        self.btn_export_pdf.setEnabled(True)

        # Update KPI Cards
        self._update_kpi_cards(
            statement.opening_balance,
            statement.total_credits,
            statement.total_debits,
            statement.closing_balance,
            statement.currency,
        )

        # Update table rows
        self._populate_table(statement.entries)

        # Update footer
        self.tx_count_lbl.setText(f"{statement.transaction_count} transactions in statement")
        start_str = (
            statement.start_date.strftime("%Y-%m-%d") if statement.start_date else "Inception"
        )
        end_str = statement.end_date.strftime("%Y-%m-%d")
        self.statement_period_lbl.setText(f"Period: {start_str} to {end_str}")

    def _on_export_csv_clicked(self) -> None:
        if not self.vm.current_statement:
            return

        stmt = self.vm.current_statement
        start_str = stmt.start_date.strftime("%Y%m%d") if stmt.start_date else "INCEPTION"
        end_str = stmt.end_date.strftime("%Y%m%d")
        default_filename = f"NovaBank_Statement_{stmt.account_number}_{start_str}_{end_str}.csv"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Statement to CSV",
            default_filename,
            "CSV Files (*.csv);;All Files (*)",
        )
        if file_path:
            self.vm.export_statement_csv(file_path)

    def _on_export_pdf_clicked(self) -> None:
        if not self.vm.current_statement:
            return

        stmt = self.vm.current_statement
        start_str = stmt.start_date.strftime("%Y%m%d") if stmt.start_date else "INCEPTION"
        end_str = stmt.end_date.strftime("%Y%m%d")
        default_filename = f"NovaBank_Statement_{stmt.account_number}_{start_str}_{end_str}.pdf"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Statement to PDF",
            default_filename,
            "PDF Documents (*.pdf);;All Files (*)",
        )
        if file_path:
            self.vm.export_statement_pdf(file_path)

    def _on_statement_exported(self, file_path: str) -> None:
        QMessageBox.information(
            self,
            "Export Successful",
            f"Account statement successfully exported to:\n{file_path}",
        )

    def _on_export_failed(self, error_msg: str) -> None:
        QMessageBox.critical(
            self,
            "Export Failed",
            f"Failed to export statement:\n{error_msg}",
        )

    def _update_kpi_cards(
        self,
        opening: Decimal,
        total_credits: Decimal,
        total_debits: Decimal,
        closing: Decimal,
        currency: str,
    ) -> None:
        def _set_card_val(card: QFrame, text: str):
            val_lbl = card.findChild(QLabel, "kpi_value")
            if val_lbl:
                val_lbl.setText(text)

        _set_card_val(self.card_opening, f"${opening:,.2f} {currency}")
        _set_card_val(self.card_credits, f"+${total_credits:,.2f} {currency}")
        _set_card_val(self.card_debits, f"-${total_debits:,.2f} {currency}")
        _set_card_val(self.card_closing, f"${closing:,.2f} {currency}")

    def _populate_table(self, entries: tuple[StatementEntryDTO, ...]) -> None:
        self.table.setRowCount(len(entries))

        for row, entry in enumerate(entries):
            # 0. Date & Time
            dt_str = entry.created_at.strftime("%Y-%m-%d %H:%M:%S")
            dt_item = QTableWidgetItem(dt_str)

            # 1. Reference ID
            ref_item = QTableWidgetItem(entry.transaction_ref)
            ref_item.setFont(self.font())

            # 2. Type
            type_item = QTableWidgetItem(entry.transaction_type)

            # 3. Description
            desc_item = QTableWidgetItem(entry.description)

            # 4. Debit
            debit_item = QTableWidgetItem(entry.formatted_debit)
            debit_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            debit_item.setForeground(Qt.GlobalColor.red)

            # 5. Credit
            credit_item = QTableWidgetItem(entry.formatted_credit)
            credit_item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )
            credit_item.setForeground(Qt.GlobalColor.green)

            # 6. Running Balance
            bal_item = QTableWidgetItem(entry.formatted_balance_after)
            bal_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            self.table.setItem(row, 0, dt_item)
            self.table.setItem(row, 1, ref_item)
            self.table.setItem(row, 2, type_item)
            self.table.setItem(row, 3, desc_item)
            self.table.setItem(row, 4, debit_item)
            self.table.setItem(row, 5, credit_item)
            self.table.setItem(row, 6, bal_item)

    def set_account(self, account: AccountDTO) -> None:
        """Programmatically switch view to customer account and load statement."""
        self.account_edit.setText(account.account_number)
        self.vm.set_account(account)
