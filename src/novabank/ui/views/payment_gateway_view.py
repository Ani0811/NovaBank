"""Payment Gateway & Merchant Settlement View widget."""

from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, Signal
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
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.payment_dto import (
    PaymentRefundResultDTO,
    PaymentTransactionDTO,
)
from novabank.ui.resources.icons import get_icon
from novabank.ui.viewmodels.payment_gateway_viewmodel import PaymentGatewayViewModel

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class PaymentReceiptDialog(QDialog):
    """Institutional modal receipt confirming settled payment ingestion."""

    def __init__(self, payment: PaymentTransactionDTO, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.payment = payment
        self.setWindowTitle("Payment Settlement Receipt")
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

        # Header with Success Badge
        header_row = QHBoxLayout()
        header_text = QVBoxLayout()
        header_text.setSpacing(4)

        badge = QLabel("SETTLEMENT COMPLETED")
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
        badge.setFixedWidth(160)

        title = QLabel("Gateway Clearance Receipt")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033;")
        subtitle = QLabel("Dual-entry atomic ledger balance updated successfully.")
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

        # Receipt Data Box
        box = QFrame()
        box.setStyleSheet(
            """
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 14px;
            """
        )
        grid = QGridLayout(box)
        grid.setSpacing(10)

        def _row(row_idx: int, label: str, value: str, is_mono: bool = False, bold: bool = False):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #64748B; font-size: 12px;")
            val = QLabel(value)
            mono_str = "font-family: 'Consolas', monospace;" if is_mono else ""
            bold_str = "font-weight: 700;" if bold else ""
            val.setStyleSheet(f"color: #172033; font-size: 13px; {mono_str} {bold_str}")
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            grid.addWidget(lbl, row_idx, 0)
            grid.addWidget(val, row_idx, 1)

        _row(0, "Payment ID:", self.payment.payment_id, is_mono=True, bold=True)
        _row(1, "Account Number:", self.payment.account_number, is_mono=True)
        _row(2, "Channel Rail:", self.payment.channel)
        if self.payment.card_brand:
            brand_display = f"{self.payment.card_brand} (ending in {self.payment.last4})"
            _row(3, "Card Details:", brand_display)
        _row(4, "Merchant Name:", self.payment.merchant_name)
        _row(5, "Customer / Buyer:", self.payment.customer_name)
        _row(6, "Gross Amount:", f"${self.payment.amount:,.2f}", is_mono=True)
        _row(7, "Interchange Fee:", f"-${self.payment.fee:,.2f}", is_mono=True)
        _row(8, "Net Settlement:", f"${self.payment.net_amount:,.2f}", is_mono=True, bold=True)
        settled_str = self.payment.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
        _row(9, "Settled At:", settled_str)

        layout.addWidget(box)

        # Actions
        btn_layout = QHBoxLayout()
        btn_close = QPushButton("Close Receipt")
        btn_close.setFixedHeight(36)
        btn_close.setStyleSheet(
            """
            QPushButton {
                background-color: #17365D;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 6px 18px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1E4273;
            }
            """
        )
        btn_close.clicked.connect(self.accept)
        btn_layout.addStretch()
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)


class RefundConfirmationDialog(QDialog):
    """Confirmation modal for issuing a payment refund."""

    def __init__(self, payment: PaymentTransactionDTO, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.payment = payment
        self.setWindowTitle("Issue Gateway Refund")
        self.setFixedWidth(460)
        self.setModal(True)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #FFFFFF;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            """
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Confirm Payment Reversal & Refund")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #DC2626;")
        layout.addWidget(title)

        desc = QLabel(
            f"This action will immediately debit <b>${self.payment.net_amount:,.2f}</b> from "
            f"account <b>{self.payment.account_number}</b> to reverse payment <b>{self.payment.payment_id}</b>."
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("font-size: 13px; color: #172033; line-height: 1.4;")
        layout.addWidget(desc)

        reason_lbl = QLabel("Reason for Refund:")
        reason_lbl.setStyleSheet("font-weight: 600; font-size: 12px; color: #172033;")
        layout.addWidget(reason_lbl)

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("e.g. Customer returned goods / order cancellation")
        self.reason_input.setFixedHeight(34)
        self.reason_input.setStyleSheet(
            """
            QLineEdit {
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 13px;
                background-color: #FFFFFF;
            }
            QLineEdit:focus {
                border-color: #2563EB;
            }
            """
        )
        layout.addWidget(self.reason_input)

        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setFixedHeight(34)
        btn_cancel.setStyleSheet(
            """
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 14px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
            """
        )
        btn_cancel.clicked.connect(self.reject)

        self.btn_confirm = QPushButton("Confirm && Execute Refund")
        self.btn_confirm.setFixedHeight(34)
        self.btn_confirm.setStyleSheet(
            """
            QPushButton {
                background-color: #DC2626;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 4px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #B91C1C;
            }
            """
        )
        self.btn_confirm.clicked.connect(self._on_confirm)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(self.btn_confirm)
        layout.addLayout(btn_row)

    def _on_confirm(self) -> None:
        reason = self.reason_input.text().strip()
        if not reason:
            QMessageBox.warning(self, "Reason Required", "Please provide a valid reason for this refund.")
            return
        self.accept()

    def get_reason(self) -> str:
        return self.reason_input.text().strip()


class PaymentGatewayView(QWidget):
    """Comprehensive Payment Gateway Virtual Terminal & Merchant Settlement Ledger."""

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        viewmodel: Optional[PaymentGatewayViewModel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm = viewmodel or PaymentGatewayViewModel(banking_service, task_runner, parent=self)

        self._setup_ui()
        self._connect_signals()

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm.set_services(banking_service, task_runner)

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 20, 28, 24)
        root_layout.setSpacing(14)

        # Main Tab Widget
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: #FFFFFF;
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-bottom: none;
                padding: 8px 18px;
                margin-right: 4px;
                font-size: 13px;
                font-weight: 600;
                color: #64748B;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background: #FFFFFF;
                color: #17365D;
                border-bottom: 2px solid #2563EB;
            }
            QTabBar::tab:hover:!selected {
                background: #F1F5F9;
                color: #172033;
            }
            """
        )

        # Tab 1: Virtual Terminal
        self.terminal_tab = self._build_terminal_tab()
        self.tab_widget.addTab(
            self.terminal_tab,
            get_icon("credit_card", color="#2563EB", size=16),
            "Virtual Terminal (Process Payment)",
        )

        # Tab 2: Gateway Ledger & Settlements
        self.ledger_tab = self._build_ledger_tab()
        self.tab_widget.addTab(
            self.ledger_tab,
            get_icon("transactions", color="#2563EB", size=16),
            "Gateway Ledger && Settlements",
        )

        self.tab_widget.currentChanged.connect(self._on_tab_changed)
        root_layout.addWidget(self.tab_widget)

    def _build_terminal_tab(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(24)

        # Left Column: Inputs Form (stretch=3)
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        # Section A: Account Target
        acc_box = QFrame()
        acc_box.setStyleSheet(
            """
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 12px;
            }
            """
        )
        acc_layout = QVBoxLayout(acc_box)
        acc_layout.setSpacing(8)

        acc_title = QLabel("1. MERCHANT DESTINATION ACCOUNT")
        acc_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 0.5px;")
        acc_layout.addWidget(acc_title)

        acc_input_row = QHBoxLayout()
        self.acc_input = QLineEdit()
        self.acc_input.setPlaceholderText("Enter 12-digit NovaBank account (e.g. 100012345678)")
        self.acc_input.setMaxLength(14)
        self.acc_input.setFixedHeight(36)
        self.acc_input.setStyleSheet(
            """
            QLineEdit {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 13px;
                font-family: 'Consolas', monospace;
            }
            QLineEdit:focus {
                border-color: #2563EB;
            }
            """
        )
        self.acc_input.textChanged.connect(self._on_account_text_changed)
        acc_input_row.addWidget(self.acc_input)
        acc_layout.addLayout(acc_input_row)

        # Account Verification Pill / Banner
        self.acc_status_banner = QLabel("Enter 12 digits to verify account credentials")
        self.acc_status_banner.setStyleSheet("font-size: 12px; color: #64748B; padding: 2px 0;")
        acc_layout.addWidget(self.acc_status_banner)
        left_col.addWidget(acc_box)

        # Section B: Payment Rail Selection
        rail_box = QFrame()
        rail_box.setStyleSheet(
            """
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 12px;
            }
            """
        )
        rail_layout = QVBoxLayout(rail_box)
        rail_layout.setSpacing(10)

        rail_title = QLabel("2. PAYMENT CHANNEL & INGESTION RAIL")
        rail_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 0.5px;")
        rail_layout.addWidget(rail_title)

        self.channel_combo = QComboBox()
        self.channel_combo.setFixedHeight(36)
        self.channel_combo.addItems(
            [
                "CARD — Credit / Debit Card (2.9% + $0.30)",
                "ACH — Direct Debit Network (0.8% cap $5.00)",
                "FEDNOW — Instant Clearing ($0.25 flat)",
                "WIRE — Wholesale RTGS ($15.00 flat)",
            ]
        )
        self.channel_combo.setStyleSheet(
            """
            QComboBox {
                background: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: 500;
            }
            QComboBox:focus {
                border-color: #2563EB;
            }
            """
        )
        self.channel_combo.currentIndexChanged.connect(self._on_channel_changed)
        rail_layout.addWidget(self.channel_combo)

        # Stacked credentials for channels
        self.credentials_stack = QStackedWidget()

        # Page 0: Card Details
        card_page = QWidget()
        card_layout = QVBoxLayout(card_page)
        card_layout.setContentsMargins(0, 4, 0, 0)
        card_layout.setSpacing(10)

        card_no_row = QHBoxLayout()
        self.card_num_input = QLineEdit()
        self.card_num_input.setPlaceholderText("Card Number (e.g. 4242 •••• •••• 4242)")
        self.card_num_input.setMaxLength(19)
        self.card_num_input.setFixedHeight(34)
        self.card_num_input.setStyleSheet("font-family: 'Consolas', monospace; font-size: 13px; padding: 4px 10px;")
        self.card_num_input.textChanged.connect(self._on_card_number_changed)

        self.card_brand_badge = QLabel("")
        self.card_brand_badge.setStyleSheet(
            """
            background-color: #EFF6FF;
            color: #1D4ED8;
            border: 1px solid #DBEAFE;
            border-radius: 4px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 700;
            """
        )
        self.card_brand_badge.setVisible(False)

        card_no_row.addWidget(self.card_num_input, stretch=1)
        card_no_row.addWidget(self.card_brand_badge)
        card_layout.addLayout(card_no_row)

        card_details_row = QHBoxLayout()
        self.card_holder_input = QLineEdit()
        self.card_holder_input.setPlaceholderText("Cardholder Full Name")
        self.card_holder_input.setFixedHeight(34)

        self.card_exp_input = QLineEdit()
        self.card_exp_input.setPlaceholderText("MM/YY")
        self.card_exp_input.setMaxLength(5)
        self.card_exp_input.setFixedWidth(80)
        self.card_exp_input.setFixedHeight(34)
        self.card_exp_input.setStyleSheet("font-family: 'Consolas', monospace;")

        self.card_cvv_input = QLineEdit()
        self.card_cvv_input.setPlaceholderText("CVV")
        self.card_cvv_input.setMaxLength(4)
        self.card_cvv_input.setFixedWidth(70)
        self.card_cvv_input.setFixedHeight(34)
        self.card_cvv_input.setStyleSheet("font-family: 'Consolas', monospace;")

        self.card_zip_input = QLineEdit()
        self.card_zip_input.setPlaceholderText("Zip")
        self.card_zip_input.setMaxLength(10)
        self.card_zip_input.setFixedWidth(80)
        self.card_zip_input.setFixedHeight(34)

        card_details_row.addWidget(self.card_holder_input, stretch=1)
        card_details_row.addWidget(self.card_exp_input)
        card_details_row.addWidget(self.card_cvv_input)
        card_details_row.addWidget(self.card_zip_input)
        card_layout.addLayout(card_details_row)

        self.credentials_stack.addWidget(card_page)

        # Page 1: ACH Details
        ach_page = QWidget()
        ach_layout = QVBoxLayout(ach_page)
        ach_layout.setContentsMargins(0, 4, 0, 0)
        ach_layout.setSpacing(10)

        ach_row = QHBoxLayout()
        self.ach_routing_input = QLineEdit()
        self.ach_routing_input.setPlaceholderText("ABA Routing Transit (9 Digits, e.g. 121000358)")
        self.ach_routing_input.setMaxLength(9)
        self.ach_routing_input.setFixedHeight(34)
        self.ach_routing_input.setStyleSheet("font-family: 'Consolas', monospace;")

        self.ach_account_input = QLineEdit()
        self.ach_account_input.setPlaceholderText("Customer External Account Number")
        self.ach_account_input.setFixedHeight(34)
        self.ach_account_input.setStyleSheet("font-family: 'Consolas', monospace;")

        ach_row.addWidget(self.ach_routing_input, stretch=1)
        ach_row.addWidget(self.ach_account_input, stretch=1)
        ach_layout.addLayout(ach_row)

        self.credentials_stack.addWidget(ach_page)

        # Page 2: FedNow Details
        fednow_page = QWidget()
        fednow_layout = QVBoxLayout(fednow_page)
        fednow_layout.setContentsMargins(0, 4, 0, 0)
        fednow_layout.setSpacing(8)

        self.fednow_memo_input = QLineEdit()
        self.fednow_memo_input.setPlaceholderText("FedNow Clearing Routing / Participant Identifier")
        self.fednow_memo_input.setFixedHeight(34)
        fednow_layout.addWidget(self.fednow_memo_input)

        self.credentials_stack.addWidget(fednow_page)

        # Page 3: Wire Details
        wire_page = QWidget()
        wire_layout = QVBoxLayout(wire_page)
        wire_layout.setContentsMargins(0, 4, 0, 0)
        wire_layout.setSpacing(8)

        self.wire_memo_input = QLineEdit()
        self.wire_memo_input.setPlaceholderText("Fedwire / SWIFT Identifier & IMAD Reference")
        self.wire_memo_input.setFixedHeight(34)
        wire_layout.addWidget(self.wire_memo_input)

        self.credentials_stack.addWidget(wire_page)

        rail_layout.addWidget(self.credentials_stack)
        left_col.addWidget(rail_box)

        # Section C: Transaction Amount & Description
        tx_box = QFrame()
        tx_box.setStyleSheet(
            """
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                padding: 12px;
            }
            """
        )
        tx_layout = QVBoxLayout(tx_box)
        tx_layout.setSpacing(10)

        tx_title = QLabel("3. TRANSACTION DETAILS")
        tx_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748B; letter-spacing: 0.5px;")
        tx_layout.addWidget(tx_title)

        amt_row = QHBoxLayout()
        self.amt_input = QLineEdit()
        self.amt_input.setPlaceholderText("0.00")
        self.amt_input.setFixedHeight(36)
        self.amt_input.setStyleSheet(
            """
            QLineEdit {
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 15px;
                font-weight: 700;
                font-family: 'Consolas', monospace;
                color: #172033;
            }
            QLineEdit:focus {
                border-color: #2563EB;
            }
            """
        )
        self.amt_input.textChanged.connect(self._on_amount_changed)

        amt_prefix = QLabel("$")
        amt_prefix.setStyleSheet("font-size: 16px; font-weight: 700; color: #64748B;")
        amt_row.addWidget(amt_prefix)
        amt_row.addWidget(self.amt_input, stretch=1)
        tx_layout.addLayout(amt_row)

        desc_row = QHBoxLayout()
        self.desc_input = QLineEdit()
        self.desc_input.setPlaceholderText("Payment memo / merchant invoice (e.g. Order #1089)")
        self.desc_input.setFixedHeight(34)
        desc_row.addWidget(self.desc_input)
        tx_layout.addLayout(desc_row)

        left_col.addWidget(tx_box)
        layout.addLayout(left_col, stretch=3)

        # Right Column: Fee Preview & Actions (stretch=2)
        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        # Interchange Fee Breakdown Card
        fee_card = QFrame()
        fee_card.setStyleSheet(
            """
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 16px;
            }
            """
        )
        fee_layout = QVBoxLayout(fee_card)
        fee_layout.setSpacing(12)

        fee_title = QLabel("SETTLEMENT BREAKDOWN")
        fee_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #475569; letter-spacing: 0.5px;")
        fee_layout.addWidget(fee_title)

        grid_fee = QGridLayout()
        grid_fee.setSpacing(8)

        lbl_g = QLabel("Gross Ingestion:")
        lbl_g.setStyleSheet("color: #64748B; font-size: 12px;")
        self.val_gross = QLabel("$0.00")
        self.val_gross.setStyleSheet("font-family: 'Consolas', monospace; font-size: 13px; color: #172033;")

        lbl_f = QLabel("Interchange / Scheme Fee:")
        lbl_f.setStyleSheet("color: #64748B; font-size: 12px;")
        self.val_fee = QLabel("-$0.00")
        self.val_fee.setStyleSheet("font-family: 'Consolas', monospace; font-size: 13px; color: #DC2626;")

        lbl_n = QLabel("Net Merchant Credit:")
        lbl_n.setStyleSheet("color: #172033; font-size: 13px; font-weight: 700;")
        self.val_net = QLabel("$0.00")
        self.val_net.setStyleSheet("font-family: 'Consolas', monospace; font-size: 20px; font-weight: 700; color: #15803D;")

        grid_fee.addWidget(lbl_g, 0, 0)
        grid_fee.addWidget(self.val_gross, 0, 1)
        grid_fee.addWidget(lbl_f, 1, 0)
        grid_fee.addWidget(self.val_fee, 1, 1)
        grid_fee.addWidget(lbl_n, 2, 0)
        grid_fee.addWidget(self.val_net, 2, 1)
        fee_layout.addLayout(grid_fee)

        div_fee = QFrame()
        div_fee.setFrameShape(QFrame.Shape.HLine)
        div_fee.setStyleSheet("color: #E2E8F0; background-color: #E2E8F0; height: 1px;")
        fee_layout.addWidget(div_fee)

        self.sla_label = QLabel("Rail SLA: Card Clearance Real-Time Atomic Settlement")
        self.sla_label.setStyleSheet("font-size: 11px; color: #64748B;")
        fee_layout.addWidget(self.sla_label)

        right_col.addWidget(fee_card)

        # Action Buttons
        self.btn_submit = QPushButton("Authorize && Settle Payment")
        self.btn_submit.setFixedHeight(44)
        self.btn_submit.setStyleSheet(
            """
            QPushButton {
                background-color: #17365D;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #1E4273;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
            }
            """
        )
        self.btn_submit.clicked.connect(self._on_submit_clicked)
        right_col.addWidget(self.btn_submit)

        self.btn_reset = QPushButton("Reset Terminal")
        self.btn_reset.setFixedHeight(34)
        self.btn_reset.setStyleSheet(
            """
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
            """
        )
        self.btn_reset.clicked.connect(self._reset_terminal_fields)
        right_col.addWidget(self.btn_reset)

        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet("color: #DC2626; font-size: 12px; font-weight: 600;")
        self.error_label.setVisible(False)
        right_col.addWidget(self.error_label)

        right_col.addStretch()
        layout.addLayout(right_col, stretch=2)

        scroll.setWidget(content)
        return scroll

    def _build_ledger_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 16, 20, 20)
        layout.setSpacing(12)

        # Filter Bar
        filter_bar = QHBoxLayout()
        filter_bar.setSpacing(10)

        self.filter_acc = QLineEdit()
        self.filter_acc.setPlaceholderText("Filter Account Number...")
        self.filter_acc.setFixedWidth(160)
        self.filter_acc.setFixedHeight(32)
        filter_bar.addWidget(self.filter_acc)

        self.filter_channel = QComboBox()
        self.filter_channel.setFixedHeight(32)
        self.filter_channel.addItems(["ALL Channels", "CARD", "ACH", "FEDNOW", "WIRE"])
        filter_bar.addWidget(self.filter_channel)

        self.filter_status = QComboBox()
        self.filter_status.setFixedHeight(32)
        self.filter_status.addItems(["ALL Statuses", "SETTLED", "REFUNDED", "DECLINED"])
        filter_bar.addWidget(self.filter_status)

        btn_filter = QPushButton("Apply Filter")
        btn_filter.setFixedHeight(32)
        btn_filter.setStyleSheet(
            """
            QPushButton {
                background-color: #2563EB;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #1D4ED8;
            }
            """
        )
        btn_filter.clicked.connect(self.refresh_ledger)
        filter_bar.addWidget(btn_filter)

        btn_reset_filter = QPushButton("Reset")
        btn_reset_filter.setFixedHeight(32)
        btn_reset_filter.setStyleSheet(
            """
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 12px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
            """
        )
        btn_reset_filter.clicked.connect(self._reset_filters)
        filter_bar.addWidget(btn_reset_filter)

        self.btn_refund = QPushButton("Issue Refund")
        self.btn_refund.setFixedHeight(32)
        self.btn_refund.setEnabled(False)
        self.btn_refund.setStyleSheet(
            """
            QPushButton {
                background-color: #FEE2E2;
                color: #DC2626;
                border: 1px solid #FECACA;
                border-radius: 4px;
                padding: 4px 12px;
                font-weight: 600;
            }
            QPushButton:hover:!disabled {
                background-color: #FCA5A5;
            }
            QPushButton:disabled {
                background-color: #F8FAFC;
                color: #94A3B8;
                border-color: #E2E8F0;
            }
            """
        )
        self.btn_refund.clicked.connect(self._on_refund_selected_clicked)
        filter_bar.addWidget(self.btn_refund)

        filter_bar.addStretch()

        self.btn_export = QPushButton("Export Gateway CSV")
        self.btn_export.setFixedHeight(32)
        self.btn_export.setStyleSheet(
            """
            QPushButton {
                background-color: #F8FAFC;
                color: #17365D;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
            }
            """
        )
        self.btn_export.clicked.connect(self._on_export_csv_clicked)
        filter_bar.addWidget(self.btn_export)

        layout.addLayout(filter_bar)

        # Summary Info Label
        self.ledger_summary_lbl = QLabel("Showing 0 gateway transactions")
        self.ledger_summary_lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
        layout.addWidget(self.ledger_summary_lbl)

        # Transactions Table
        self.table = QTableWidget()
        self.table.setColumnCount(10)
        self.table.setHorizontalHeaderLabels(
            [
                "Payment ID",
                "Timestamp",
                "Account",
                "Channel",
                "Routing / Brand",
                "Merchant",
                "Gross Amount",
                "Fee",
                "Net Settled",
                "Status",
            ]
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_table_selection_changed)
        self.table.setStyleSheet(
            """
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                gridline-color: #F1F5F9;
                font-size: 12px;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #475569;
                font-weight: 600;
                border: none;
                border-bottom: 1px solid #E2E8F0;
                padding: 8px 10px;
            }
            """
        )
        header = self.table.horizontalHeader()
        widths = [155, 125, 110, 80, 125, 150, 105, 85, 105, 85]
        for col_idx, col_w in enumerate(widths):
            header.setSectionResizeMode(col_idx, QHeaderView.ResizeMode.Interactive)
            self.table.setColumnWidth(col_idx, col_w)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)

        layout.addWidget(self.table)
        return widget

    def _connect_signals(self) -> None:
        self.vm.account_found.connect(self._on_account_found)
        self.vm.account_lookup_failed.connect(self._on_account_lookup_failed)
        self.vm.fee_calculated.connect(self._on_fee_calculated)
        self.vm.card_brand_detected.connect(self._on_card_brand_detected)
        self.vm.submitting_changed.connect(self._on_submitting_changed)
        self.vm.payment_completed.connect(self._on_payment_completed)
        self.vm.payment_failed.connect(self._on_payment_failed)
        self.vm.refund_completed.connect(self._on_refund_completed)
        self.vm.refund_failed.connect(self._on_refund_failed)
        self.vm.payments_loaded.connect(self._on_payments_loaded)
        self.vm.payments_load_failed.connect(self._on_payments_load_failed)
        self.vm.csv_exported.connect(self._on_csv_exported)
        self.vm.csv_export_failed.connect(self._on_csv_export_failed)

    def _on_tab_changed(self, index: int) -> None:
        if index == 1:
            self.refresh_ledger()

    def _on_account_text_changed(self, text: str) -> None:
        clean = text.strip().replace("-", "").replace(" ", "")
        if len(clean) == 12:
            self.acc_status_banner.setText("Verifying account...")
            self.acc_status_banner.setStyleSheet("color: #2563EB; font-size: 12px;")
            self.vm.lookup_account(clean)
        else:
            self.vm.target_account = None
            self.acc_status_banner.setText("Enter 12 digits to verify account credentials")
            self.acc_status_banner.setStyleSheet("color: #64748B; font-size: 12px;")

    def _on_account_found(self, account: AccountDTO) -> None:
        self.acc_status_banner.setText(
            f"✓ Verified: {account.holder_name} | Available: ${account.balance:,.2f}"
        )
        self.acc_status_banner.setStyleSheet("color: #15803D; font-weight: 600; font-size: 12px;")

    def _on_account_lookup_failed(self, error: str) -> None:
        self.acc_status_banner.setText(f"✕ {error}")
        self.acc_status_banner.setStyleSheet("color: #DC2626; font-size: 12px;")

    def _on_channel_changed(self, index: int) -> None:
        channels = ["CARD", "ACH", "FEDNOW", "WIRE"]
        ch = channels[index] if index < len(channels) else "CARD"
        self.credentials_stack.setCurrentIndex(index)
        self.vm.set_channel(ch)

        sla_texts = [
            "Rail SLA: Card Clearance Real-Time Atomic Settlement",
            "Rail SLA: Automated Clearing House (ACH) Same-Day Window",
            "Rail SLA: FedNow 24/7/365 Instant Settlement Finality",
            "Rail SLA: Wholesale Fedwire / RTGS Same-Day Immediate",
        ]
        if index < len(sla_texts):
            self.sla_label.setText(sla_texts[index])

    def _on_amount_changed(self, text: str) -> None:
        self.vm.set_amount(text)

    def _on_card_number_changed(self, text: str) -> None:
        self.vm.set_card_number(text)

    def _on_card_brand_detected(self, brand: str) -> None:
        if brand and brand != "UNKNOWN":
            self.card_brand_badge.setText(brand)
            self.card_brand_badge.setVisible(True)
        else:
            self.card_brand_badge.setVisible(False)

    def _on_fee_calculated(self, gross: Decimal, fee: Decimal, net: Decimal) -> None:
        self.val_gross.setText(f"${gross:,.2f}")
        self.val_fee.setText(f"-${fee:,.2f}")
        self.val_net.setText(f"${net:,.2f}")

    def _on_submitting_changed(self, is_submitting: bool) -> None:
        self.btn_submit.setEnabled(not is_submitting)
        if is_submitting:
            self.btn_submit.setText("Authorizing & Settling...")
        else:
            self.btn_submit.setText("Authorize && Settle Payment")

    def _on_submit_clicked(self) -> None:
        self.error_label.setVisible(False)
        acc_text = self.acc_input.text().strip().replace("-", "").replace(" ", "")
        if not acc_text or len(acc_text) != 12:
            self._show_error("Please specify a valid 12-digit destination account number.")
            return

        try:
            amt = Decimal(self.amt_input.text().strip().replace("$", "").replace(",", ""))
            if amt <= Decimal("0.00"):
                self._show_error("Payment amount must be greater than zero.")
                return
        except (InvalidOperation, ValueError):
            self._show_error("Please enter a valid numeric payment amount.")
            return

        channel_enum = ["CARD", "ACH", "FEDNOW", "WIRE"][self.channel_combo.currentIndex()]
        card_num = self.card_num_input.text().strip() if channel_enum == "CARD" else None
        card_exp = self.card_exp_input.text().strip() if channel_enum == "CARD" else None
        card_cvv = self.card_cvv_input.text().strip() if channel_enum == "CARD" else None
        card_zip = self.card_zip_input.text().strip() if channel_enum == "CARD" else None
        routing = self.ach_routing_input.text().strip() if channel_enum == "ACH" else None

        cust_name = self.card_holder_input.text().strip() if channel_enum == "CARD" else "Authorized Payer"
        desc = self.desc_input.text().strip()

        self.vm.submit_payment(
            account_number=acc_text,
            channel=channel_enum,
            amount=amt,
            merchant_name="NovaBank Merchant Store",
            customer_name=cust_name or "Valued Customer",
            description=desc,
            card_number=card_num,
            card_exp=card_exp,
            card_cvv=card_cvv,
            card_zip=card_zip,
            routing_number=routing,
        )

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)

    def _on_payment_completed(self, dto: PaymentTransactionDTO) -> None:
        self.error_label.setVisible(False)
        self._reset_terminal_fields()
        # Open receipt dialog
        dialog = PaymentReceiptDialog(dto, parent=self)
        dialog.exec()

    def _on_payment_failed(self, error: str) -> None:
        self._show_error(f"Clearance Failed: {error}")

    def _reset_terminal_fields(self) -> None:
        self.amt_input.clear()
        self.card_num_input.clear()
        self.card_holder_input.clear()
        self.card_exp_input.clear()
        self.card_cvv_input.clear()
        self.card_zip_input.clear()
        self.ach_routing_input.clear()
        self.ach_account_input.clear()
        self.fednow_memo_input.clear()
        self.wire_memo_input.clear()
        self.desc_input.clear()
        self.error_label.setVisible(False)
        self.vm.update_fee_preview()

    # --- Tab 2: Ledger Methods ---

    def refresh_ledger(self) -> None:
        acc = self.filter_acc.text().strip()
        ch = self.filter_channel.currentText()
        ch_val = ch.replace("ALL Channels", "ALL")
        st = self.filter_status.currentText()
        st_val = st.replace("ALL Statuses", "ALL")

        self.vm.load_payments(
            account_number=acc if acc else None,
            channel=ch_val,
            status=st_val,
        )

    def _reset_filters(self) -> None:
        self.filter_acc.clear()
        self.filter_channel.setCurrentIndex(0)
        self.filter_status.setCurrentIndex(0)
        self.refresh_ledger()

    def _on_payments_loaded(self, payments: list[PaymentTransactionDTO], total: int) -> None:
        self.ledger_summary_lbl.setText(f"Showing {len(payments)} of {total} gateway transactions")
        self.table.clearContents()
        self.table.setRowCount(len(payments))

        for row, p in enumerate(payments):
            # 0. Payment ID
            it_id = QTableWidgetItem(p.payment_id)
            it_id.setFont(QFont("Consolas", 10))
            self.table.setItem(row, 0, it_id)

            # 1. Timestamp
            ts_str = p.created_at.strftime("%Y-%m-%d %H:%M")
            self.table.setItem(row, 1, QTableWidgetItem(ts_str))

            # 2. Account
            it_acc = QTableWidgetItem(p.account_number)
            it_acc.setFont(QFont("Consolas", 10))
            self.table.setItem(row, 2, it_acc)

            # 3. Channel
            self.table.setItem(row, 3, QTableWidgetItem(p.channel))

            # 4. Details / Routing
            detail = ""
            if p.card_brand:
                detail = f"{p.card_brand} ···· {p.last4}"
            elif p.channel == "ACH":
                detail = "ACH Direct"
            else:
                detail = p.channel
            self.table.setItem(row, 4, QTableWidgetItem(detail))

            # 5. Merchant
            self.table.setItem(row, 5, QTableWidgetItem(p.merchant_name))

            # 6. Gross
            it_gross = QTableWidgetItem(f"${p.amount:,.2f}")
            it_gross.setFont(QFont("Consolas", 10))
            it_gross.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 6, it_gross)

            # 7. Fee
            it_fee = QTableWidgetItem(f"-${p.fee:,.2f}")
            it_fee.setFont(QFont("Consolas", 10))
            it_fee.setForeground(QColor("#DC2626"))
            it_fee.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 7, it_fee)

            # 8. Net Settled
            it_net = QTableWidgetItem(f"${p.net_amount:,.2f}")
            it_net.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            it_net.setForeground(QColor("#15803D"))
            it_net.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 8, it_net)

            # 9. Status
            it_status = QTableWidgetItem(p.status)
            it_status.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            if p.status == "SETTLED":
                it_status.setForeground(QColor("#15803D"))
            elif p.status == "REFUNDED":
                it_status.setForeground(QColor("#7E22CE"))
            else:
                it_status.setForeground(QColor("#DC2626"))
            it_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(row, 9, it_status)

        self._on_table_selection_changed()

    def _on_table_selection_changed(self) -> None:
        selected_rows = self.table.selectedIndexes()
        if not selected_rows:
            self.btn_refund.setEnabled(False)
            return
        row = selected_rows[0].row()
        if 0 <= row < len(self.vm.current_payments):
            payment = self.vm.current_payments[row]
            self.btn_refund.setEnabled(payment.status == "SETTLED")
        else:
            self.btn_refund.setEnabled(False)

    def _on_refund_selected_clicked(self) -> None:
        selected_rows = self.table.selectedIndexes()
        if not selected_rows:
            return
        row = selected_rows[0].row()
        if 0 <= row < len(self.vm.current_payments):
            payment = self.vm.current_payments[row]
            self._on_refund_requested(payment)

    def _on_payments_load_failed(self, error: str) -> None:
        self.ledger_summary_lbl.setText(f"Failed to load payments: {error}")

    def _on_refund_requested(self, payment: PaymentTransactionDTO) -> None:
        dialog = RefundConfirmationDialog(payment, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            reason = dialog.get_reason()
            self.vm.issue_refund(payment.payment_id, reason)

    def _on_refund_completed(self, dto: PaymentRefundResultDTO) -> None:
        QMessageBox.information(
            self,
            "Refund Processed",
            f"Successfully refunded payment {dto.payment_id}.\n"
            f"Debit reversal of ${dto.refunded_amount:,.2f} applied to account {dto.account_number}.",
        )
        self.refresh_ledger()

    def _on_refund_failed(self, error: str) -> None:
        QMessageBox.critical(self, "Refund Failed", f"Could not process refund:\n{error}")

    def _on_export_csv_clicked(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Gateway Transactions to CSV",
            "novabank_gateway_settlements.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if file_path:
            self.vm.export_csv(file_path)

    def _on_csv_exported(self, path: str) -> None:
        QMessageBox.information(
            self,
            "CSV Export Successful",
            f"Gateway transaction records successfully exported to:\n{path}",
        )

    def _on_csv_export_failed(self, error: str) -> None:
        QMessageBox.critical(self, "CSV Export Failed", f"Failed to export CSV:\n{error}")
