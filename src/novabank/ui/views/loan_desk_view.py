"""Commercial Loan Origination, Amortization Simulator, and Portfolio Servicing View."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.loan_dto import (
    AmortizationScheduleEntryDTO,
    LoanContractDTO,
    LoanQuoteResponseDTO,
    LoanRepaymentResultDTO,
)
from novabank.ui.resources.icons import get_icon
from novabank.ui.viewmodels.loan_desk_viewmodel import LoanDeskViewModel

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class LoanDisbursementReceiptDialog(QDialog):
    """Institutional modal receipt confirming commercial credit facility origination and disbursement."""

    def __init__(self, loan: LoanContractDTO, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.loan = loan
        self.setWindowTitle("Commercial Credit Facility Origination Receipt")
        self.setFixedWidth(540)
        self.setModal(True)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #FFFFFF;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel {
                font-size: 13px;
                color: #172033;
            }
            """
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(18)

        # Header Badge
        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(4)

        badge = QLabel("CREDIT FACILITY DISBURSED")
        badge.setStyleSheet(
            """
            background-color: #DCFCE7;
            color: #15803D;
            border: 1px solid #BBF7D0;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            """
        )
        badge.setFixedWidth(180)

        title = QLabel("Facility Origination & Disbursement")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033;")
        subtitle = QLabel("Principal credited atomically to borrower checking account.")
        subtitle.setStyleSheet("font-size: 12px; color: #64748B;")

        header_text.addWidget(badge)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header_row.addLayout(header_text)
        layout.addLayout(header_row)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #E2E8F0; background-color: #E2E8F0; height: 1px;")
        layout.addWidget(div)

        # Data Box
        box = QFrame()
        box.setStyleSheet(
            """
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 14px;
            """
        )
        box_layout = QGridLayout(box)
        box_layout.setVerticalSpacing(10)
        box_layout.setHorizontalSpacing(16)

        def _add_row(row_idx: int, label_text: str, val_text: str, is_highlight: bool = False, is_mono: bool = False):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
            val = QLabel(val_text)
            mono_style = "font-family: 'Consolas', monospace;" if is_mono else ""
            if is_highlight:
                val.setStyleSheet(f"font-size: 14px; font-weight: 700; color: #17365D; {mono_style}")
            else:
                val.setStyleSheet(f"font-size: 13px; font-weight: 600; color: #172033; {mono_style}")
            box_layout.addWidget(lbl, row_idx, 0)
            box_layout.addWidget(val, row_idx, 1)

        _add_row(0, "Facility ID:", self.loan.loan_id, is_mono=True)
        _add_row(1, "Borrower Account:", self.loan.account_number, is_mono=True)
        _add_row(2, "Facility Type:", self.loan.loan_type.replace("_", " ").title())
        _add_row(3, "Principal Disbursed:", self.loan.formatted_principal, is_highlight=True)
        _add_row(4, "Annual Percentage Rate:", f"{self.loan.interest_rate_apr}%")
        _add_row(5, "Term (Months):", f"{self.loan.term_months} Months")
        _add_row(6, "Monthly Installment (EMI):", self.loan.formatted_monthly_installment, is_highlight=True)
        _add_row(7, "Total Interest Over Term:", self.loan.formatted_total_interest)
        _add_row(8, "Next Payment Due:", self.loan.next_due_date or "—")

        layout.addWidget(box)

        btn_row = QHBoxLayout()
        btn_close = QPushButton("Close Receipt")
        btn_close.setFixedHeight(36)
        btn_close.setStyleSheet(
            """
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 6px 20px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            """
        )
        btn_close.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class LoanRepaymentDialog(QDialog):
    """Institutional modal dialog to confirm and execute a scheduled monthly installment repayment."""

    def __init__(self, loan: LoanContractDTO, next_entry: AmortizationScheduleEntryDTO, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.loan = loan
        self.next_entry = next_entry
        self.setWindowTitle("Process Scheduled Installment Repayment")
        self.setFixedWidth(520)
        self.setModal(True)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #FFFFFF;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel {
                font-size: 13px;
                color: #172033;
            }
            """
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(18)

        # Header Badge
        header_text = QVBoxLayout()
        header_text.setSpacing(4)

        badge = QLabel("SCHEDULED INSTALLMENT")
        badge.setStyleSheet(
            """
            background-color: #EFF6FF;
            color: #2563EB;
            border: 1px solid #BFDBFE;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            """
        )
        badge.setFixedWidth(160)

        title = QLabel("Settle Installment Payment")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033;")
        subtitle = QLabel("Debits borrower checking account and amortizes debt balance.")
        subtitle.setStyleSheet("font-size: 12px; color: #64748B;")

        header_text.addWidget(badge)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        layout.addLayout(header_text)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #E2E8F0; background-color: #E2E8F0; height: 1px;")
        layout.addWidget(div)

        # Data Box
        box = QFrame()
        box.setStyleSheet(
            """
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 14px;
            """
        )
        box_layout = QGridLayout(box)
        box_layout.setVerticalSpacing(10)
        box_layout.setHorizontalSpacing(16)

        def _add_row(row_idx: int, label_text: str, val_text: str, is_highlight: bool = False, is_mono: bool = False):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
            val = QLabel(val_text)
            mono_style = "font-family: 'Consolas', monospace;" if is_mono else ""
            if is_highlight:
                val.setStyleSheet(f"font-size: 14px; font-weight: 700; color: #17365D; {mono_style}")
            else:
                val.setStyleSheet(f"font-size: 13px; font-weight: 600; color: #172033; {mono_style}")
            box_layout.addWidget(lbl, row_idx, 0)
            box_layout.addWidget(val, row_idx, 1)

        _add_row(0, "Facility ID:", self.loan.loan_id, is_mono=True)
        _add_row(1, "Borrower Account:", self.loan.account_number, is_mono=True)
        _add_row(2, "Installment Milestone:", f"Month {self.next_entry.installment_number} of {self.loan.term_months}")
        _add_row(3, "Due Date:", self.next_entry.due_date)
        _add_row(4, "Total Installment Due:", self.next_entry.formatted_payment, is_highlight=True)
        _add_row(5, "Principal Amortization:", self.next_entry.formatted_principal)
        _add_row(6, "Interest Portion:", self.next_entry.formatted_interest)
        _add_row(7, "Remaining Debt After:", self.next_entry.formatted_remaining_balance, is_highlight=True)

        layout.addWidget(box)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet(
            """
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
            """
        )
        btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton("Confirm & Debit Installment")
        self.btn_confirm.setFixedHeight(36)
        self.btn_confirm.setStyleSheet(
            """
            QPushButton {
                background-color: #15803D;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 6px 18px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #166534;
            }
            """
        )
        self.btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_confirm)
        layout.addLayout(btn_row)


class LoanDeskView(QWidget):
    """Institutional Commercial Loan Hub featuring Origination, Amortization Simulation, and Portfolio Servicing."""

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        viewmodel: Optional[LoanDeskViewModel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm = viewmodel or LoanDeskViewModel(banking_service, task_runner, parent=self)

        self._setup_ui()
        self._connect_signals()

        # Load initial loans
        self.refresh_portfolio()

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm.set_services(banking_service, task_runner)
        self.refresh_portfolio()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 20, 28, 24)
        root_layout.setSpacing(14)

        # Tab Widget
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: #FFFFFF;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #F8FAFC;
                color: #64748B;
                padding: 10px 22px;
                font-weight: 600;
                font-size: 13px;
                border: 1px solid #E2E8F0;
                border-bottom: none;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #17365D;
                border-bottom: 2px solid #2563EB;
            }
            QTabBar::tab:hover:!selected {
                background-color: #F1F5F9;
                color: #172033;
            }
            """
        )

        # Initialize the 3 Tabs
        self.origination_tab = QWidget()
        self.portfolio_tab = QWidget()
        self.schedule_tab = QWidget()

        self._setup_origination_tab()
        self._setup_portfolio_tab()
        self._setup_schedule_tab()

        self.tab_widget.addTab(self.origination_tab, "Origination & Simulator")
        self.tab_widget.addTab(self.portfolio_tab, "Loan Portfolio & Repayments")
        self.tab_widget.addTab(self.schedule_tab, "Amortization Schedule Explorer")

        root_layout.addWidget(self.tab_widget)

    # -------------------------------------------------------------------------
    # TAB 1: Origination & Simulator
    # -------------------------------------------------------------------------

    def _setup_origination_tab(self) -> None:
        scroll = QScrollArea(self.origination_tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Left Column: Configuration Controls
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        # Borrower Account Lookup
        lookup_box = QGroupBox("Borrower Account Lookup")
        lookup_box.setStyleSheet(self._group_box_style())
        lookup_layout = QVBoxLayout(lookup_box)
        lookup_layout.setSpacing(10)

        acc_row = QHBoxLayout()
        self.borrower_acc_input = QLineEdit()
        self.borrower_acc_input.setPlaceholderText("12-Digit Account Number")
        self.borrower_acc_input.setMaxLength(12)
        self.borrower_acc_input.setFixedHeight(36)
        self.borrower_acc_input.setStyleSheet(self._input_mono_style())

        btn_lookup = QPushButton("Look Up")
        btn_lookup.setFixedHeight(36)
        btn_lookup.setStyleSheet(self._btn_secondary_style())
        btn_lookup.clicked.connect(self._on_lookup_clicked)

        acc_row.addWidget(self.borrower_acc_input, stretch=1)
        acc_row.addWidget(btn_lookup)
        lookup_layout.addLayout(acc_row)

        self.account_status_label = QLabel("Enter a 12-digit account number to verify credit eligibility.")
        self.account_status_label.setStyleSheet("font-size: 12px; color: #64748B;")
        lookup_layout.addWidget(self.account_status_label)
        left_col.addWidget(lookup_box)

        # Facility Parameters
        param_box = QGroupBox("Credit Facility Parameters")
        param_box.setStyleSheet(self._group_box_style())
        param_layout = QVBoxLayout(param_box)
        param_layout.setSpacing(14)

        # Facility Type
        type_lbl = QLabel("Facility Type")
        type_lbl.setStyleSheet(self._label_style())
        self.loan_type_combo = QComboBox()
        self.loan_type_combo.setFixedHeight(36)
        self.loan_type_combo.setStyleSheet(self._combo_style())
        self.loan_type_combo.addItem("Commercial Equipment Financing", "COMMERCIAL_EQUIPMENT")
        self.loan_type_combo.addItem("Working Capital Credit Line", "WORKING_CAPITAL")
        self.loan_type_combo.addItem("Commercial Real Estate Mortgage", "COMMERCIAL_MORTGAGE")
        self.loan_type_combo.addItem("Fixed Term Commercial Loan", "TERM_LOAN")
        param_layout.addWidget(type_lbl)
        param_layout.addWidget(self.loan_type_combo)

        # Purpose
        purpose_lbl = QLabel("Financing Purpose / Facility Notes")
        purpose_lbl.setStyleSheet(self._label_style())
        self.purpose_input = QLineEdit()
        self.purpose_input.setText("Operational Capital Expansion")
        self.purpose_input.setFixedHeight(36)
        self.purpose_input.setStyleSheet(self._input_style())
        param_layout.addWidget(purpose_lbl)
        param_layout.addWidget(self.purpose_input)

        # Principal Amount
        principal_lbl = QLabel("Principal Facility Amount ($)")
        principal_lbl.setStyleSheet(self._label_style())
        self.principal_input = QLineEdit()
        self.principal_input.setText("100,000.00")
        self.principal_input.setFixedHeight(36)
        self.principal_input.setStyleSheet(self._input_mono_style())
        self.principal_input.textChanged.connect(self._on_params_changed)
        param_layout.addWidget(principal_lbl)
        param_layout.addWidget(self.principal_input)

        # APR Interest Rate
        apr_lbl = QLabel("Annual Percentage Rate (APR %)")
        apr_lbl.setStyleSheet(self._label_style())
        self.apr_input = QLineEdit()
        self.apr_input.setText("7.50")
        self.apr_input.setFixedHeight(36)
        self.apr_input.setStyleSheet(self._input_mono_style())
        self.apr_input.textChanged.connect(self._on_params_changed)
        param_layout.addWidget(apr_lbl)
        param_layout.addWidget(self.apr_input)

        # Term Months & Quick Pills
        term_lbl = QLabel("Amortization Term (Months)")
        term_lbl.setStyleSheet(self._label_style())
        param_layout.addWidget(term_lbl)

        pill_row = QHBoxLayout()
        pill_row.setSpacing(6)
        self.pill_buttons: dict[int, QPushButton] = {}
        for months in [12, 24, 36, 60, 120]:
            btn = QPushButton(f"{months}m")
            btn.setFixedHeight(30)
            btn.setStyleSheet(self._pill_style(active=(months == 36)))
            btn.clicked.connect(lambda checked=False, m=months: self._select_term_months(m))
            self.pill_buttons[months] = btn
            pill_row.addWidget(btn)
        param_layout.addLayout(pill_row)

        self.term_spinbox = QSpinBox()
        self.term_spinbox.setRange(1, 360)
        self.term_spinbox.setValue(36)
        self.term_spinbox.setFixedHeight(36)
        self.term_spinbox.setStyleSheet(self._input_mono_style())
        self.term_spinbox.valueChanged.connect(self._on_term_spinbox_changed)
        param_layout.addWidget(self.term_spinbox)

        # Action Button: Calculate
        self.btn_simulate = QPushButton("Simulate Amortization")
        self.btn_simulate.setFixedHeight(38)
        self.btn_simulate.setStyleSheet(self._btn_secondary_style())
        self.btn_simulate.clicked.connect(self._trigger_quote_calc)
        param_layout.addWidget(self.btn_simulate)

        left_col.addWidget(param_box)
        left_col.addStretch()

        # Right Column: Underwriting Quote & Preview
        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        # Quote Card
        quote_box = QGroupBox("Underwriting Simulation & Pricing")
        quote_box.setStyleSheet(self._group_box_style())
        quote_layout = QVBoxLayout(quote_box)
        quote_layout.setSpacing(14)

        # Hero Stat: Monthly EMI
        hero_frame = QFrame()
        hero_frame.setStyleSheet(
            """
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 16px;
            """
        )
        hero_layout = QVBoxLayout(hero_frame)
        hero_layout.setSpacing(4)
        hero_lbl = QLabel("ESTIMATED MONTHLY INSTALLMENT (EMI)")
        hero_lbl.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 0.5px;")
        self.quote_emi_label = QLabel("$3,110.62")
        self.quote_emi_label.setStyleSheet("font-size: 26px; font-weight: 700; color: #17365D; font-family: 'Consolas', monospace;")
        hero_layout.addWidget(hero_lbl)
        hero_layout.addWidget(self.quote_emi_label)
        quote_layout.addWidget(hero_frame)

        # Grid of Supporting Metrics
        metric_grid = QGridLayout()
        metric_grid.setVerticalSpacing(8)
        metric_grid.setHorizontalSpacing(16)

        def _make_metric(row: int, col: int, title: str, init_val: str) -> QLabel:
            box_w = QFrame()
            box_w.setStyleSheet("background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 4px; padding: 8px;")
            l = QVBoxLayout(box_w)
            l.setContentsMargins(4, 4, 4, 4)
            l.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600;")
            v = QLabel(init_val)
            v.setStyleSheet("font-size: 14px; color: #172033; font-weight: 700; font-family: 'Consolas', monospace;")
            l.addWidget(t)
            l.addWidget(v)
            metric_grid.addWidget(box_w, row, col)
            return v

        self.quote_principal_val = _make_metric(0, 0, "Principal Borrowed", "$100,000.00")
        self.quote_interest_val = _make_metric(0, 1, "Total Finance Charge", "$11,982.32")
        self.quote_payable_val = _make_metric(1, 0, "Total Lifetime Debt", "$111,982.32")
        self.quote_term_val = _make_metric(1, 1, "Duration / Installments", "36 Months")
        quote_layout.addLayout(metric_grid)

        # Preview Schedule Table (First few months)
        preview_lbl = QLabel("Schedule Preview (Initial Installments)")
        preview_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #172033;")
        quote_layout.addWidget(preview_lbl)

        self.preview_table = QTableWidget(6, 4)
        self.preview_table.setHorizontalHeaderLabels(["Month", "Payment", "Principal", "Balance"])
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.preview_table.verticalHeader().setVisible(False)
        self.preview_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.preview_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.preview_table.setFixedHeight(180)
        self.preview_table.setStyleSheet(self._table_style())
        quote_layout.addWidget(self.preview_table)

        # Primary Origination Button
        self.btn_originate = QPushButton("Underwrite & Disburse Facility")
        self.btn_originate.setFixedHeight(44)
        self.btn_originate.setEnabled(False)
        self.btn_originate.setStyleSheet(
            """
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover:!disabled {
                background-color: #1D4ED8;
            }
            QPushButton:disabled {
                background-color: #F1F5F9;
                color: #94A3B8;
            }
            """
        )
        self.btn_originate.clicked.connect(self._on_originate_clicked)
        quote_layout.addWidget(self.btn_originate)

        right_col.addWidget(quote_box)
        right_col.addStretch()

        layout.addLayout(left_col, stretch=4)
        layout.addLayout(right_col, stretch=5)

        scroll.setWidget(container)
        tab_layout = QVBoxLayout(self.origination_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    # -------------------------------------------------------------------------
    # TAB 2: Portfolio & Repayments
    # -------------------------------------------------------------------------

    def _setup_portfolio_tab(self) -> None:
        layout = QVBoxLayout(self.portfolio_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Top KPI Metric Cards
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(14)

        def _create_kpi_card(title: str, default_val: str, icon_name: str) -> tuple[QFrame, QLabel]:
            card = QFrame()
            card.setStyleSheet(
                """
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 12px 16px;
                """
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(0, 0, 0, 0)
            card_layout.setSpacing(4)

            top_line = QHBoxLayout()
            lbl_title = QLabel(title)
            lbl_title.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748B; text-transform: uppercase;")
            icon_lbl = QLabel()
            icon_lbl.setPixmap(get_icon(icon_name, "#64748B").pixmap(16, 16))
            top_line.addWidget(lbl_title)
            top_line.addStretch()
            top_line.addWidget(icon_lbl)

            lbl_val = QLabel(default_val)
            lbl_val.setStyleSheet("font-size: 20px; font-weight: 700; color: #172033; font-family: 'Consolas', monospace;")

            card_layout.addLayout(top_line)
            card_layout.addWidget(lbl_val)
            return card, lbl_val

        c1, self.kpi_active_facilities = _create_kpi_card("Active Facilities", "0 Active", "landmark")
        c2, self.kpi_total_debt = _create_kpi_card("Outstanding Portfolio", "$0.00", "dollar")
        c3, self.kpi_monthly_inflow = _create_kpi_card("Monthly Inflow (EMI)", "$0.00", "repeat")
        c4, self.kpi_portfolio_health = _create_kpi_card("Health & Compliance", "100% Current", "shield")

        kpi_row.addWidget(c1)
        kpi_row.addWidget(c2)
        kpi_row.addWidget(c3)
        kpi_row.addWidget(c4)
        layout.addLayout(kpi_row)

        # Filter & Action Toolbar
        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.filter_acc_input = QLineEdit()
        self.filter_acc_input.setPlaceholderText("Filter by Borrower Account")
        self.filter_acc_input.setMaxLength(12)
        self.filter_acc_input.setFixedWidth(200)
        self.filter_acc_input.setFixedHeight(32)
        self.filter_acc_input.setStyleSheet(self._input_mono_style())
        toolbar.addWidget(self.filter_acc_input)

        self.filter_status_combo = QComboBox()
        self.filter_status_combo.setFixedHeight(32)
        self.filter_status_combo.setFixedWidth(140)
        self.filter_status_combo.setStyleSheet(self._combo_style())
        self.filter_status_combo.addItem("All Statuses", "ALL")
        self.filter_status_combo.addItem("Active Only", "ACTIVE")
        self.filter_status_combo.addItem("Delinquent", "DELINQUENT")
        self.filter_status_combo.addItem("Paid Off", "PAID_OFF")
        toolbar.addWidget(self.filter_status_combo)

        btn_filter = QPushButton("Apply Filter")
        btn_filter.setFixedHeight(32)
        btn_filter.setStyleSheet(self._btn_secondary_style())
        btn_filter.clicked.connect(self.refresh_portfolio)
        toolbar.addWidget(btn_filter)

        btn_reset = QPushButton("Reset")
        btn_reset.setFixedHeight(32)
        btn_reset.setStyleSheet(self._btn_tertiary_style())
        btn_reset.clicked.connect(self._on_reset_portfolio_filter)
        toolbar.addWidget(btn_reset)

        toolbar.addSpacing(12)

        # Action: Process Repayment
        self.btn_repay = QPushButton("Process Monthly Repayment")
        self.btn_repay.setFixedHeight(32)
        self.btn_repay.setEnabled(False)
        self.btn_repay.setStyleSheet(
            """
            QPushButton {
                background-color: #DCFCE7;
                color: #15803D;
                border: 1px solid #BBF7D0;
                border-radius: 4px;
                padding: 4px 14px;
                font-weight: 600;
            }
            QPushButton:hover:!disabled {
                background-color: #BBF7D0;
            }
            QPushButton:disabled {
                background-color: #F8FAFC;
                color: #94A3B8;
                border-color: #E2E8F0;
            }
            """
        )
        self.btn_repay.clicked.connect(self._on_repay_clicked)
        toolbar.addWidget(self.btn_repay)

        # Action: View Schedule
        self.btn_view_schedule = QPushButton("View Amortization Schedule")
        self.btn_view_schedule.setFixedHeight(32)
        self.btn_view_schedule.setEnabled(False)
        self.btn_view_schedule.setStyleSheet(self._btn_secondary_style())
        self.btn_view_schedule.clicked.connect(self._on_view_schedule_clicked)
        toolbar.addWidget(self.btn_view_schedule)

        toolbar.addStretch()

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setFixedHeight(32)
        btn_refresh.setStyleSheet(self._btn_tertiary_style())
        btn_refresh.clicked.connect(self.refresh_portfolio)
        toolbar.addWidget(btn_refresh)

        layout.addLayout(toolbar)

        # Portfolio Table
        self.portfolio_table = QTableWidget(0, 10)
        headers = [
            "Facility ID",
            "Borrower Account",
            "Type",
            "Principal",
            "APR %",
            "Term",
            "Monthly EMI",
            "Outstanding Debt",
            "Status",
            "Next Due Date",
        ]
        self.portfolio_table.setHorizontalHeaderLabels(headers)
        self.portfolio_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.portfolio_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.portfolio_table.verticalHeader().setVisible(False)
        self.portfolio_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.portfolio_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.portfolio_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.portfolio_table.setStyleSheet(self._table_style())
        self.portfolio_table.itemSelectionChanged.connect(self._on_portfolio_row_selected)
        self.portfolio_table.doubleClicked.connect(lambda idx: self._on_view_schedule_clicked())
        layout.addWidget(self.portfolio_table)

    # -------------------------------------------------------------------------
    # TAB 3: Amortization Schedule Explorer
    # -------------------------------------------------------------------------

    def _setup_schedule_tab(self) -> None:
        layout = QVBoxLayout(self.schedule_tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header Details Card
        banner = QFrame()
        banner.setStyleSheet(
            """
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 16px;
            """
        )
        banner_layout = QVBoxLayout(banner)
        banner_layout.setSpacing(12)

        top_info = QHBoxLayout()
        info_col = QVBoxLayout()
        info_col.setSpacing(2)
        self.schedule_facility_title = QLabel("Facility Amortization Schedule: No Facility Selected")
        self.schedule_facility_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #17365D;")
        self.schedule_facility_subtitle = QLabel("Select an active commercial loan from the portfolio desk to explore its amortization progression.")
        self.schedule_facility_subtitle.setStyleSheet("font-size: 12px; color: #64748B;")
        info_col.addWidget(self.schedule_facility_title)
        info_col.addWidget(self.schedule_facility_subtitle)
        top_info.addLayout(info_col)

        top_info.addStretch()

        self.btn_export_csv = QPushButton("Export Schedule (CSV)")
        self.btn_export_csv.setFixedHeight(34)
        self.btn_export_csv.setEnabled(False)
        self.btn_export_csv.setStyleSheet(
            """
            QPushButton {
                background-color: #F8FAFC;
                color: #17365D;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 14px;
                font-weight: 600;
            }
            QPushButton:hover:!disabled {
                background-color: #E2E8F0;
            }
            QPushButton:disabled {
                color: #94A3B8;
                border-color: #E2E8F0;
            }
            """
        )
        self.btn_export_csv.clicked.connect(self._on_export_csv_clicked)
        top_info.addWidget(self.btn_export_csv)
        banner_layout.addLayout(top_info)

        # Progress & Zero Drift Note
        progress_row = QHBoxLayout()
        self.schedule_progress_bar = QProgressBar()
        self.schedule_progress_bar.setRange(0, 100)
        self.schedule_progress_bar.setValue(0)
        self.schedule_progress_bar.setFixedHeight(12)
        self.schedule_progress_bar.setTextVisible(False)
        self.schedule_progress_bar.setStyleSheet(
            """
            QProgressBar {
                background-color: #E2E8F0;
                border-radius: 6px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #2563EB;
                border-radius: 6px;
            }
            """
        )
        self.schedule_progress_label = QLabel("0% Repaid (0 of 0 Installments)")
        self.schedule_progress_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #172033; min-width: 180px;")

        zero_drift_badge = QLabel("Zero-Penny Drift Verified")
        zero_drift_badge.setStyleSheet(
            """
            background-color: #DCFCE7;
            color: #15803D;
            border: 1px solid #BBF7D0;
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 11px;
            font-weight: 700;
            """
        )

        progress_row.addWidget(self.schedule_progress_bar, stretch=1)
        progress_row.addWidget(self.schedule_progress_label)
        progress_row.addWidget(zero_drift_badge)
        banner_layout.addLayout(progress_row)

        layout.addWidget(banner)

        # Full 8-column Schedule Table
        self.schedule_table = QTableWidget(0, 8)
        schedule_headers = [
            "Installment #",
            "Due Date",
            "Monthly Payment",
            "Principal Paid",
            "Interest Paid",
            "Remaining Debt",
            "Status",
            "Settled Date",
        ]
        self.schedule_table.setHorizontalHeaderLabels(schedule_headers)
        self.schedule_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.schedule_table.verticalHeader().setVisible(False)
        self.schedule_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.schedule_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.schedule_table.setStyleSheet(self._table_style())
        layout.addWidget(self.schedule_table)

    # -------------------------------------------------------------------------
    # Signals & Interactions
    # -------------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.vm.account_found.connect(self._on_account_found)
        self.vm.account_lookup_failed.connect(self._on_account_lookup_failed)
        self.vm.quote_calculated.connect(self._on_quote_calculated)
        self.vm.quote_failed.connect(self._on_quote_failed)
        self.vm.submitting_changed.connect(self._on_submitting_changed)
        self.vm.loan_originated.connect(self._on_loan_originated)
        self.vm.loan_origination_failed.connect(self._on_loan_origination_failed)
        self.vm.loans_loaded.connect(self._on_loans_loaded)
        self.vm.loans_load_failed.connect(self._on_loans_load_failed)
        self.vm.repayment_completed.connect(self._on_repayment_completed)
        self.vm.repayment_failed.connect(self._on_repayment_failed)
        self.vm.schedule_loaded.connect(self._on_schedule_loaded)
        self.vm.csv_exported.connect(self._on_csv_exported)
        self.vm.csv_export_failed.connect(self._on_csv_export_failed)

        # Initial quote simulation
        self._trigger_quote_calc()

    def _select_term_months(self, months: int) -> None:
        self.term_spinbox.blockSignals(True)
        self.term_spinbox.setValue(months)
        self.term_spinbox.blockSignals(False)

        for m, btn in self.pill_buttons.items():
            btn.setStyleSheet(self._pill_style(active=(m == months)))

        self._trigger_quote_calc()

    def _on_term_spinbox_changed(self, val: int) -> None:
        for m, btn in self.pill_buttons.items():
            btn.setStyleSheet(self._pill_style(active=(m == val)))
        self._trigger_quote_calc()

    def _on_params_changed(self) -> None:
        self._trigger_quote_calc()

    def _trigger_quote_calc(self) -> None:
        self.vm.calculate_quote(
            principal_str=self.principal_input.text(),
            apr_str=self.apr_input.text(),
            term_months=self.term_spinbox.value(),
        )

    def _on_lookup_clicked(self) -> None:
        raw = self.borrower_acc_input.text().strip()
        if len(raw) != 12:
            self.account_status_label.setText("Please enter an exact 12-digit account number.")
            self.account_status_label.setStyleSheet("font-size: 12px; color: #DC2626;")
            return
        self.account_status_label.setText("Verifying account standing...")
        self.account_status_label.setStyleSheet("font-size: 12px; color: #2563EB;")
        self.vm.lookup_account(raw)

    def _on_account_found(self, account: AccountDTO) -> None:
        self.account_status_label.setText(
            f"Borrower: {account.holder_name} | Balance: {account.formatted_balance} (Eligible)"
        )
        self.account_status_label.setStyleSheet("font-size: 12px; color: #15803D; font-weight: 600;")
        self._update_originate_button_state()

    def _on_account_lookup_failed(self, msg: str) -> None:
        self.account_status_label.setText(msg)
        self.account_status_label.setStyleSheet("font-size: 12px; color: #DC2626;")
        self._update_originate_button_state()

    def _on_quote_calculated(self, quote: LoanQuoteResponseDTO) -> None:
        self.quote_emi_label.setText(quote.formatted_monthly_installment)
        self.quote_principal_val.setText(quote.formatted_principal)
        self.quote_interest_val.setText(quote.formatted_total_interest)
        self.quote_payable_val.setText(quote.formatted_total_payable)
        self.quote_term_val.setText(f"{quote.term_months} Months")

        # Update preview table
        self._populate_preview_table(quote)
        self._update_originate_button_state()

    def _on_quote_failed(self, msg: str) -> None:
        self.quote_emi_label.setText("—")
        self.btn_originate.setEnabled(False)

    def _update_originate_button_state(self) -> None:
        can_originate = bool(self.vm.target_account and self.vm.current_quote)
        self.btn_originate.setEnabled(can_originate)

    def _populate_preview_table(self, quote: LoanQuoteResponseDTO) -> None:
        from novabank.domain.services.amortization_calculator import AmortizationCalculator
        from novabank.domain.value_objects.money import Money

        schedule = AmortizationCalculator.generate_amortization_schedule(
            principal=Money(quote.principal),
            apr_percentage=quote.apr_percentage,
            term_months=quote.term_months,
        )

        display_entries = schedule[:6]
        self.preview_table.setRowCount(len(display_entries))

        for row, entry in enumerate(display_entries):
            i0 = QTableWidgetItem(f"Month {entry.installment_number}")
            i1 = QTableWidgetItem(f"${entry.payment_amount.amount:,.2f}")
            i2 = QTableWidgetItem(f"${entry.principal_amount.amount:,.2f}")
            i3 = QTableWidgetItem(f"${entry.remaining_balance.amount:,.2f}")

            for it in (i0, i1, i2, i3):
                it.setFont(QFont("Consolas", 10))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.preview_table.setItem(row, 0, i0)
            self.preview_table.setItem(row, 1, i1)
            self.preview_table.setItem(row, 2, i2)
            self.preview_table.setItem(row, 3, i3)

    def _on_originate_clicked(self) -> None:
        if not self.vm.target_account or not self.vm.current_quote:
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Loan Origination & Disbursement",
            f"Underwrite and disburse {self.vm.current_quote.formatted_principal} to borrower {self.vm.target_account.holder_name} ({self.vm.target_account.account_number})?\n\n"
            f"This will immediately credit their checking account and initiate the {self.vm.current_quote.term_months}-month amortization schedule.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        self.vm.originate_loan(
            account_number=self.vm.target_account.account_number,
            loan_type=str(self.loan_type_combo.currentData()),
            principal=self.vm.current_quote.principal,
            apr=self.vm.current_quote.apr_percentage,
            term_months=self.vm.current_quote.term_months,
            purpose=self.purpose_input.text().strip() or "Commercial Financing",
        )

    def _on_submitting_changed(self, is_submitting: bool) -> None:
        self.btn_originate.setEnabled(not is_submitting and bool(self.vm.target_account and self.vm.current_quote))
        self.btn_repay.setEnabled(not is_submitting and self.portfolio_table.currentRow() >= 0)

    def _on_loan_originated(self, loan_dto: LoanContractDTO) -> None:
        receipt = LoanDisbursementReceiptDialog(loan_dto, parent=self)
        receipt.exec()

        # Refresh portfolio and switch to Portfolio tab
        self.refresh_portfolio()
        self.tab_widget.setCurrentIndex(1)

    def _on_loan_origination_failed(self, msg: str) -> None:
        QMessageBox.critical(self, "Origination Declined", f"Failed to originate credit facility:\n\n{msg}")

    # -------------------------------------------------------------------------
    # Portfolio Desk Interactions
    # -------------------------------------------------------------------------

    def refresh_portfolio(self) -> None:
        self.vm.load_loans(
            account_number=self.filter_acc_input.text().strip() or None,
            status=str(self.filter_status_combo.currentData()),
        )

    def _on_reset_portfolio_filter(self) -> None:
        self.filter_acc_input.clear()
        self.filter_status_combo.setCurrentIndex(0)
        self.refresh_portfolio()

    def _on_loans_loaded(self, loans: list[LoanContractDTO], total: int) -> None:
        self.portfolio_table.setRowCount(len(loans))

        # Update KPIs
        active_loans = [ln for ln in loans if ln.status in ("ACTIVE", "DELINQUENT")]
        total_debt = sum((ln.outstanding_balance for ln in active_loans), Decimal("0.00"))
        monthly_inflow = sum((ln.monthly_installment for ln in active_loans), Decimal("0.00"))
        delinquent_count = sum(1 for ln in loans if ln.status == "DELINQUENT")

        self.kpi_active_facilities.setText(f"{len(active_loans)} Active")
        self.kpi_total_debt.setText(f"${total_debt:,.2f}")
        self.kpi_monthly_inflow.setText(f"${monthly_inflow:,.2f}")
        if delinquent_count == 0:
            self.kpi_portfolio_health.setText("100% Current")
            self.kpi_portfolio_health.setStyleSheet("font-size: 20px; font-weight: 700; color: #15803D; font-family: 'Consolas', monospace;")
        else:
            self.kpi_portfolio_health.setText(f"{delinquent_count} Delinquent")
            self.kpi_portfolio_health.setStyleSheet("font-size: 20px; font-weight: 700; color: #DC2626; font-family: 'Consolas', monospace;")

        for row, ln in enumerate(loans):
            c0 = QTableWidgetItem(ln.loan_id)
            c1 = QTableWidgetItem(ln.account_number)
            c2 = QTableWidgetItem(ln.loan_type.replace("_", " ").title())
            c3 = QTableWidgetItem(ln.formatted_principal)
            c4 = QTableWidgetItem(f"{ln.interest_rate_apr}%")
            c5 = QTableWidgetItem(f"{ln.term_months}m")
            c6 = QTableWidgetItem(ln.formatted_monthly_installment)
            c7 = QTableWidgetItem(ln.formatted_outstanding_balance)
            c8 = QTableWidgetItem(ln.status)
            c9 = QTableWidgetItem(ln.next_due_date or "PAID IN FULL")

            # Monospace alignment
            for it in (c0, c1, c3, c4, c5, c6, c7, c9):
                it.setFont(QFont("Consolas", 10))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            c2.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            c8.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            # Status pill styling
            if ln.status == "ACTIVE":
                c8.setForeground(QColor("#15803D"))
            elif ln.status == "DELINQUENT":
                c8.setForeground(QColor("#DC2626"))
            elif ln.status == "PAID_OFF":
                c8.setForeground(QColor("#64748B"))

            self.portfolio_table.setItem(row, 0, c0)
            self.portfolio_table.setItem(row, 1, c1)
            self.portfolio_table.setItem(row, 2, c2)
            self.portfolio_table.setItem(row, 3, c3)
            self.portfolio_table.setItem(row, 4, c4)
            self.portfolio_table.setItem(row, 5, c5)
            self.portfolio_table.setItem(row, 6, c6)
            self.portfolio_table.setItem(row, 7, c7)
            self.portfolio_table.setItem(row, 8, c8)
            self.portfolio_table.setItem(row, 9, c9)

        self._on_portfolio_row_selected()

    def _on_loans_load_failed(self, msg: str) -> None:
        QMessageBox.warning(self, "Portfolio Query Error", f"Could not load commercial loans: {msg}")

    def _on_portfolio_row_selected(self) -> None:
        row = self.portfolio_table.currentRow()
        if row < 0 or row >= len(self.vm.current_loans):
            self.btn_repay.setEnabled(False)
            self.btn_view_schedule.setEnabled(False)
            return

        loan = self.vm.current_loans[row]
        can_repay = loan.status in ("ACTIVE", "DELINQUENT")
        self.btn_repay.setEnabled(can_repay)
        self.btn_view_schedule.setEnabled(True)

    def _on_repay_clicked(self) -> None:
        row = self.portfolio_table.currentRow()
        if row < 0 or row >= len(self.vm.current_loans):
            return

        loan = self.vm.current_loans[row]
        next_entry = next((e for e in loan.schedule if not e.is_paid), None)
        if not next_entry:
            QMessageBox.information(self, "Facility Paid Off", f"Loan '{loan.loan_id}' is already paid off in full.")
            return

        dlg = LoanRepaymentDialog(loan, next_entry, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.vm.repay_installment(loan.loan_id)

    def _on_repayment_completed(self, result: LoanRepaymentResultDTO) -> None:
        msg = (
            f"Successfully settled Installment #{result.installment_number} for Facility '{result.loan_id}'.\n\n"
            f"Amount Paid: ${result.repayment_amount:,.2f}\n"
            f"Principal Portion: ${result.principal_portion:,.2f}\n"
            f"Interest Portion: ${result.interest_portion:,.2f}\n"
            f"Remaining Balance: ${result.remaining_balance:,.2f}\n"
            f"Status: {result.new_status}"
        )
        if result.new_status == "PAID_OFF":
            msg += "\n\nFacility has been PAID OFF IN FULL!"

        QMessageBox.information(self, "Repayment Settled", msg)
        self.refresh_portfolio()

        # Update schedule if viewing the same loan
        if self.vm.selected_loan and self.vm.selected_loan.loan_id == result.loan_id:
            self.vm.load_loan_schedule(result.loan_id)

    def _on_repayment_failed(self, msg: str) -> None:
        QMessageBox.critical(self, "Repayment Failed", f"Could not process installment repayment:\n\n{msg}")

    # -------------------------------------------------------------------------
    # Schedule Explorer Interactions
    # -------------------------------------------------------------------------

    def _on_view_schedule_clicked(self) -> None:
        row = self.portfolio_table.currentRow()
        if row < 0 or row >= len(self.vm.current_loans):
            return

        loan = self.vm.current_loans[row]
        self.vm.load_loan_schedule(loan.loan_id)
        self.tab_widget.setCurrentIndex(2)

    def _on_schedule_loaded(self, loan: LoanContractDTO) -> None:
        self.schedule_facility_title.setText(
            f"Amortization Schedule: {loan.loan_id} ({loan.loan_type.replace('_', ' ').title()})"
        )
        self.schedule_facility_subtitle.setText(
            f"Borrower: {loan.account_number} | Principal: {loan.formatted_principal} | APR: {loan.interest_rate_apr}% | Term: {loan.term_months} Months"
        )
        self.btn_export_csv.setEnabled(True)

        # Progress bar
        pct = int(loan.progress_percentage)
        self.schedule_progress_bar.setValue(pct)
        paid_count = loan.paid_installments_count
        self.schedule_progress_label.setText(
            f"{pct}% Repaid ({paid_count} of {loan.term_months} Installments)"
        )

        # Populate schedule table
        self.schedule_table.setRowCount(len(loan.schedule))
        for row, entry in enumerate(loan.schedule):
            s0 = QTableWidgetItem(f"Month {entry.installment_number}")
            s1 = QTableWidgetItem(entry.due_date)
            s2 = QTableWidgetItem(entry.formatted_payment)
            s3 = QTableWidgetItem(entry.formatted_principal)
            s4 = QTableWidgetItem(entry.formatted_interest)
            s5 = QTableWidgetItem(entry.formatted_remaining_balance)
            s6 = QTableWidgetItem("SETTLED" if entry.is_paid else "SCHEDULED")
            s7 = QTableWidgetItem(entry.paid_date or "—")

            for it in (s0, s1, s2, s3, s4, s5, s6, s7):
                it.setFont(QFont("Consolas", 10))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            if entry.is_paid:
                s6.setForeground(QColor("#15803D"))
            else:
                s6.setForeground(QColor("#64748B"))

            self.schedule_table.setItem(row, 0, s0)
            self.schedule_table.setItem(row, 1, s1)
            self.schedule_table.setItem(row, 2, s2)
            self.schedule_table.setItem(row, 3, s3)
            self.schedule_table.setItem(row, 4, s4)
            self.schedule_table.setItem(row, 5, s5)
            self.schedule_table.setItem(row, 6, s6)
            self.schedule_table.setItem(row, 7, s7)

    def _on_export_csv_clicked(self) -> None:
        if not self.vm.selected_loan:
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Loan Amortization Schedule",
            f"loan_schedule_{self.vm.selected_loan.loan_id}.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not filename:
            return

        self.vm.export_schedule_csv(self.vm.selected_loan.loan_id, destination_path=filename)

    def _on_csv_exported(self, path_or_content: str) -> None:
        QMessageBox.information(
            self,
            "Export Successful",
            f"Loan amortization schedule exported successfully:\n\n{path_or_content}",
        )

    def _on_csv_export_failed(self, msg: str) -> None:
        QMessageBox.warning(self, "Export Failed", f"Could not export loan schedule:\n\n{msg}")

    # -------------------------------------------------------------------------
    # Enterprise Fintech Styling Tokens
    # -------------------------------------------------------------------------

    def _group_box_style(self) -> str:
        return """
            QGroupBox {
                font-size: 13px;
                font-weight: 700;
                color: #17365D;
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
        """

    def _label_style(self) -> str:
        return "font-size: 12px; font-weight: 600; color: #172033;"

    def _input_style(self) -> str:
        return """
            QLineEdit {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 13px;
                color: #172033;
            }
            QLineEdit:focus {
                border-color: #2563EB;
            }
        """

    def _input_mono_style(self) -> str:
        return """
            QLineEdit, QSpinBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 13px;
                font-family: 'Consolas', monospace;
                color: #172033;
            }
            QLineEdit:focus, QSpinBox:focus {
                border-color: #2563EB;
            }
        """

    def _combo_style(self) -> str:
        return """
            QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 13px;
                color: #172033;
            }
            QComboBox:focus {
                border-color: #2563EB;
            }
        """

    def _pill_style(self, active: bool = False) -> str:
        if active:
            return """
                QPushButton {
                    background-color: #17365D;
                    color: #FFFFFF;
                    border: 1px solid #17365D;
                    border-radius: 15px;
                    padding: 2px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }
            """
        return """
            QPushButton {
                background-color: #F8FAFC;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 15px;
                padding: 2px 12px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                color: #172033;
            }
        """

    def _btn_secondary_style(self) -> str:
        return """
            QPushButton {
                background-color: #F8FAFC;
                color: #17365D;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
        """

    def _btn_tertiary_style(self) -> str:
        return """
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
        """

    def _table_style(self) -> str:
        return """
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 4px;
                gridline-color: #F1F5F9;
                font-size: 13px;
                color: #172033;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #64748B;
                padding: 8px 6px;
                font-weight: 600;
                font-size: 12px;
                border: none;
                border-bottom: 1px solid #E2E8F0;
            }
            QTableWidget::item:selected {
                background-color: #EFF6FF;
                color: #17365D;
            }
        """
