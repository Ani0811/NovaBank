"""Account-to-Account Fund Transfer View with dual-account validation and atomic receipt modal."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.transaction_dto import TransferResultDTO
from novabank.ui.viewmodels.transaction_viewmodel import TransactionViewModel

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class TransferReceiptDialog(QDialog):
    """Digital receipt modal dialog displaying dual transaction records and correlation ID."""

    def __init__(
        self, transfer_result: TransferResultDTO, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self.transfer_result = transfer_result
        self.setWindowTitle("Transfer Confirmation Receipt - NovaBank")
        self.setMinimumWidth(580)
        self.setStyleSheet(
            "QDialog { background-color: #0f172a; color: #f8fafc; font-family: 'Segoe UI', sans-serif; }"
            "QLabel { color: #f8fafc; }"
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        # Receipt Container Card
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 20px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(14)

        # Header
        header_layout = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        bank_name = QLabel("NOVABANK INTERNAL TRANSFER")
        bank_name.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #38bdf8; letter-spacing: 1px;"
        )
        rec_title = QLabel("Electronic Fund Transfer Receipt")
        rec_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")
        title_box.addWidget(bank_name)
        title_box.addWidget(rec_title)
        header_layout.addLayout(title_box)
        header_layout.addStretch()

        status_badge = QLabel("✓ SETTLED")
        status_badge.setStyleSheet(
            "background-color: #064e3b; color: #34d399; font-weight: bold; padding: 6px 14px; border-radius: 12px; font-size: 12px;"
        )
        header_layout.addWidget(status_badge)
        card_layout.addLayout(header_layout)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #334155; margin-top: 4px; margin-bottom: 4px;")
        card_layout.addWidget(divider)

        # Transfer Amount Display
        amt_box = QVBoxLayout()
        amt_box.setSpacing(2)
        amt_lbl = QLabel("TOTAL AMOUNT TRANSFERRED")
        amt_lbl.setStyleSheet("font-size: 11px; color: #94a3b8; font-weight: bold;")
        amt_val = QLabel(f"${self.transfer_result.amount:,.2f} {self.transfer_result.currency}")
        amt_val.setStyleSheet("font-size: 24px; font-weight: bold; color: #38bdf8;")
        amt_box.addWidget(amt_lbl)
        amt_box.addWidget(amt_val)
        card_layout.addLayout(amt_box)

        # Metadata Grid
        meta_grid = QGridLayout()
        meta_grid.setSpacing(8)

        meta_grid.addWidget(
            self._make_field("Correlation ID:", self.transfer_result.correlation_id), 0, 0
        )
        meta_grid.addWidget(
            self._make_field(
                "Execution Time:",
                self.transfer_result.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
            ),
            0,
            1,
        )
        card_layout.addLayout(meta_grid)

        # Dual Account Details
        accounts_layout = QHBoxLayout()
        accounts_layout.setSpacing(12)

        # Source Box (Debited)
        src_box = QFrame()
        src_box.setStyleSheet(
            "QFrame { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 12px; }"
        )
        src_layout = QVBoxLayout(src_box)
        src_layout.setSpacing(6)
        src_header = QLabel("DEBITED (SOURCE)")
        src_header.setStyleSheet("font-size: 11px; font-weight: bold; color: #f87171;")
        src_acc = QLabel(f"Acc: {self.transfer_result.source_transaction.account_number}")
        src_acc.setStyleSheet(
            "font-family: monospace; font-size: 13px; font-weight: bold; color: #f8fafc;"
        )
        src_ref = QLabel(f"Ref: {self.transfer_result.source_transaction.transaction_ref}")
        src_ref.setStyleSheet("font-size: 11px; color: #94a3b8; font-family: monospace;")
        src_bal = QLabel(
            f"New Bal: {self.transfer_result.source_transaction.formatted_balance_after}"
        )
        src_bal.setStyleSheet("font-size: 12px; color: #cbd5e1;")

        src_layout.addWidget(src_header)
        src_layout.addWidget(src_acc)
        src_layout.addWidget(src_ref)
        src_layout.addWidget(src_bal)
        accounts_layout.addWidget(src_box)

        # Destination Box (Credited)
        dst_box = QFrame()
        dst_box.setStyleSheet(
            "QFrame { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 12px; }"
        )
        dst_layout = QVBoxLayout(dst_box)
        dst_layout.setSpacing(6)
        dst_header = QLabel("CREDITED (DESTINATION)")
        dst_header.setStyleSheet("font-size: 11px; font-weight: bold; color: #34d399;")
        dst_acc = QLabel(f"Acc: {self.transfer_result.destination_transaction.account_number}")
        dst_acc.setStyleSheet(
            "font-family: monospace; font-size: 13px; font-weight: bold; color: #f8fafc;"
        )
        dst_ref = QLabel(f"Ref: {self.transfer_result.destination_transaction.transaction_ref}")
        dst_ref.setStyleSheet("font-size: 11px; color: #94a3b8; font-family: monospace;")
        dst_bal = QLabel(
            f"New Bal: {self.transfer_result.destination_transaction.formatted_balance_after}"
        )
        dst_bal.setStyleSheet("font-size: 12px; color: #cbd5e1;")

        dst_layout.addWidget(dst_header)
        dst_layout.addWidget(dst_acc)
        dst_layout.addWidget(dst_ref)
        dst_layout.addWidget(dst_bal)
        accounts_layout.addWidget(dst_box)

        card_layout.addLayout(accounts_layout)
        layout.addWidget(card)

        # Action Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.addStretch()

        print_btn = QPushButton("Print Receipt")
        print_btn.setStyleSheet(
            "QPushButton { background-color: #334155; border-radius: 6px; padding: 8px 18px; color: #f8fafc; font-weight: 500; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        print_btn.clicked.connect(self._on_print_clicked)
        btn_layout.addWidget(print_btn)

        close_btn = QPushButton("Done")
        close_btn.setStyleSheet(
            "QPushButton { background-color: #0284c7; border-radius: 6px; padding: 8px 24px; color: #ffffff; font-weight: bold; }"
            "QPushButton:hover { background-color: #0369a1; }"
        )
        close_btn.clicked.connect(self.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

    def _make_field(self, label: str, value: str) -> QWidget:
        container = QWidget()
        field_layout = QVBoxLayout(container)
        field_layout.setContentsMargins(0, 0, 0, 0)
        field_layout.setSpacing(2)
        lbl = QLabel(label)
        lbl.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        val = QLabel(value)
        val.setStyleSheet("color: #f8fafc; font-size: 12px; font-family: monospace;")
        field_layout.addWidget(lbl)
        field_layout.addWidget(val)
        return container

    def _on_print_clicked(self) -> None:
        QMessageBox.information(
            self,
            "Print Receipt",
            f"Transfer receipt {self.transfer_result.correlation_id} dispatched to system default printer.",
        )


class TransferView(QWidget):
    """Account-to-account fund transfer view with dual validation and live previews."""

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        viewmodel: Optional[TransactionViewModel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm = viewmodel or TransactionViewModel(
            banking_service, task_runner, mode="transfer", parent=self
        )

        self._setup_ui()
        self._bind_viewmodel()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 28, 28, 28)
        main_layout.setSpacing(16)

        # 1. Header Section
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)

        title_lbl = QLabel("Account-to-Account Fund Transfer")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #f8fafc;")

        subtitle_lbl = QLabel(
            "Execute instantaneous internal transfers between customer accounts with atomic ledger settlement."
        )
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #94a3b8;")

        header_layout.addWidget(title_lbl)
        header_layout.addWidget(subtitle_lbl)
        main_layout.addLayout(header_layout)

        # Scroll Area for Form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 16, 0)
        content_layout.setSpacing(16)

        # 2. Account Selection Grid (Source & Destination)
        acc_grid = QHBoxLayout()
        acc_grid.setSpacing(16)

        # 2A. Source Account Card
        source_card = self._create_card()
        source_layout = QVBoxLayout(source_card)
        source_layout.setSpacing(12)

        source_title = QLabel("1. Source Account (Debited)")
        source_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #cbd5e1;")
        source_layout.addWidget(source_title)

        source_input_layout = QHBoxLayout()
        source_input_layout.setSpacing(8)

        self.source_account_edit = QLineEdit()
        self.source_account_edit.setPlaceholderText("Enter 12-digit Source Account...")
        self.source_account_edit.setStyleSheet(
            "QLineEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 12px; color: #f8fafc; font-family: monospace; font-size: 14px; }"
        )
        source_input_layout.addWidget(self.source_account_edit, stretch=2)

        self.source_verify_btn = QPushButton("Lookup Source")
        self.source_verify_btn.setStyleSheet(
            "QPushButton { background-color: #334155; border-radius: 6px; padding: 8px 16px; color: #f8fafc; font-weight: 500; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.source_verify_btn.clicked.connect(self._on_source_lookup_clicked)
        source_input_layout.addWidget(self.source_verify_btn)
        source_layout.addLayout(source_input_layout)

        self.source_account_error = self._create_error_label()
        source_layout.addWidget(self.source_account_error)

        # Verified Source Account Banner
        self.source_banner = QFrame()
        self.source_banner.setStyleSheet(
            "QFrame { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 12px; }"
        )
        self.source_banner.setVisible(False)
        src_banner_layout = QHBoxLayout(self.source_banner)
        src_banner_layout.setContentsMargins(8, 8, 8, 8)

        src_text_box = QVBoxLayout()
        self.source_banner_name = QLabel("Customer Name")
        self.source_banner_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        self.source_banner_details = QLabel("Balance: $0.00 USD  •  Status: Active")
        self.source_banner_details.setStyleSheet("color: #94a3b8; font-size: 12px;")
        src_text_box.addWidget(self.source_banner_name)
        src_text_box.addWidget(self.source_banner_details)
        src_banner_layout.addLayout(src_text_box)
        src_banner_layout.addStretch()

        self.source_banner_badge = QLabel("● Active")
        self.source_banner_badge.setStyleSheet(
            "background-color: #064e3b; color: #34d399; font-weight: bold; padding: 4px 12px; border-radius: 10px;"
        )
        src_banner_layout.addWidget(self.source_banner_badge)
        source_layout.addWidget(self.source_banner)
        acc_grid.addWidget(source_card)

        # 2B. Destination Account Card
        dest_card = self._create_card()
        dest_layout = QVBoxLayout(dest_card)
        dest_layout.setSpacing(12)

        dest_title = QLabel("2. Destination Account (Credited)")
        dest_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #cbd5e1;")
        dest_layout.addWidget(dest_title)

        dest_input_layout = QHBoxLayout()
        dest_input_layout.setSpacing(8)

        self.dest_account_edit = QLineEdit()
        self.dest_account_edit.setPlaceholderText("Enter 12-digit Destination Account...")
        self.dest_account_edit.setStyleSheet(
            "QLineEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 12px; color: #f8fafc; font-family: monospace; font-size: 14px; }"
        )
        dest_input_layout.addWidget(self.dest_account_edit, stretch=2)

        self.dest_verify_btn = QPushButton("Lookup Destination")
        self.dest_verify_btn.setStyleSheet(
            "QPushButton { background-color: #334155; border-radius: 6px; padding: 8px 16px; color: #f8fafc; font-weight: 500; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.dest_verify_btn.clicked.connect(self._on_dest_lookup_clicked)
        dest_input_layout.addWidget(self.dest_verify_btn)
        dest_layout.addLayout(dest_input_layout)

        self.dest_account_error = self._create_error_label()
        dest_layout.addWidget(self.dest_account_error)

        # Verified Destination Account Banner
        self.dest_banner = QFrame()
        self.dest_banner.setStyleSheet(
            "QFrame { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 12px; }"
        )
        self.dest_banner.setVisible(False)
        dst_banner_layout = QHBoxLayout(self.dest_banner)
        dst_banner_layout.setContentsMargins(8, 8, 8, 8)

        dst_text_box = QVBoxLayout()
        self.dest_banner_name = QLabel("Customer Name")
        self.dest_banner_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        self.dest_banner_details = QLabel("Balance: $0.00 USD  •  Status: Active")
        self.dest_banner_details.setStyleSheet("color: #94a3b8; font-size: 12px;")
        dst_text_box.addWidget(self.dest_banner_name)
        dst_text_box.addWidget(self.dest_banner_details)
        dst_banner_layout.addLayout(dst_text_box)
        dst_banner_layout.addStretch()

        self.dest_banner_badge = QLabel("● Active")
        self.dest_banner_badge.setStyleSheet(
            "background-color: #064e3b; color: #34d399; font-weight: bold; padding: 4px 12px; border-radius: 10px;"
        )
        dst_banner_layout.addWidget(self.dest_banner_badge)
        dest_layout.addWidget(self.dest_banner)
        acc_grid.addWidget(dest_card)

        content_layout.addLayout(acc_grid)

        # 3. Transfer Details Card
        tx_card = self._create_card()
        tx_layout = QVBoxLayout(tx_card)
        tx_layout.setSpacing(12)

        tx_card_title = QLabel("3. Transfer Amount & Narration")
        tx_card_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #cbd5e1;")
        tx_layout.addWidget(tx_card_title)

        tx_form = QFormLayout()
        tx_form.setSpacing(10)
        tx_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("0.00")
        self.amount_edit.setStyleSheet(
            "QLineEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 12px; color: #f8fafc; font-size: 15px; font-weight: bold; }"
        )
        self.amount_error = self._create_error_label()

        self.desc_edit = QLineEdit("Internal Fund Transfer")
        self.desc_edit.setStyleSheet(
            "QLineEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 12px; color: #f8fafc; }"
        )

        tx_form.addRow(
            "Transfer Amount ($) *:", self._wrap_field(self.amount_edit, self.amount_error)
        )
        tx_form.addRow("Description:", self.desc_edit)
        tx_layout.addLayout(tx_form)
        content_layout.addWidget(tx_card)

        # 4. Live Dual Balance Settlement Preview Strip
        preview_card = self._create_card()
        preview_layout = QHBoxLayout(preview_card)
        preview_layout.setContentsMargins(16, 12, 16, 12)
        preview_layout.setSpacing(16)

        # Source Preview Box
        self.src_prev_box = self._create_preview_stat("Source Balance", "$0.00", "#94a3b8")
        minus_sign = QLabel("-")
        minus_sign.setStyleSheet("font-size: 20px; color: #64748b; font-weight: bold;")
        self.transfer_amt_box = self._create_preview_stat("Transfer Amount", "$0.00", "#38bdf8")
        equals_sign = QLabel("=")
        equals_sign.setStyleSheet("font-size: 20px; color: #64748b; font-weight: bold;")
        self.src_proj_box = self._create_preview_stat("Source Remainder", "$0.00", "#10b981")

        arrow_sign = QLabel("➔")
        arrow_sign.setStyleSheet(
            "font-size: 24px; color: #38bdf8; font-weight: bold; padding: 0 8px;"
        )

        self.dst_prev_box = self._create_preview_stat("Dest Current", "$0.00", "#94a3b8")
        plus_sign = QLabel("+")
        plus_sign.setStyleSheet("font-size: 20px; color: #64748b; font-weight: bold;")
        self.dst_proj_box = self._create_preview_stat("Dest Projected", "$0.00", "#10b981")

        preview_layout.addLayout(self.src_prev_box)
        preview_layout.addWidget(minus_sign, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_layout.addLayout(self.transfer_amt_box)
        preview_layout.addWidget(equals_sign, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_layout.addLayout(self.src_proj_box)

        preview_layout.addWidget(arrow_sign, alignment=Qt.AlignmentFlag.AlignCenter)

        preview_layout.addLayout(self.dst_prev_box)
        preview_layout.addWidget(plus_sign, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_layout.addLayout(self.dst_proj_box)

        content_layout.addWidget(preview_card)

        # 5. Action Buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)

        self.status_msg = QLabel("")
        self.status_msg.setStyleSheet("color: #38bdf8; font-weight: 500;")
        action_layout.addWidget(self.status_msg)
        action_layout.addStretch()

        self.clear_btn = QPushButton("Reset Form")
        self.clear_btn.setStyleSheet(
            "QPushButton { background-color: #334155; border-radius: 6px; padding: 10px 20px; color: #cbd5e1; font-weight: 500; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.clear_btn.clicked.connect(self.reset_form)
        action_layout.addWidget(self.clear_btn)

        self.submit_btn = QPushButton("Execute Transfer")
        self.submit_btn.setEnabled(False)
        self.submit_btn.setStyleSheet(
            "QPushButton { background-color: #0284c7; border-radius: 6px; padding: 10px 28px; color: #ffffff; font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background-color: #0369a1; }"
            "QPushButton:disabled { background-color: #1e293b; color: #64748b; }"
        )
        self.submit_btn.clicked.connect(self._on_submit_clicked)
        action_layout.addWidget(self.submit_btn)

        content_layout.addLayout(action_layout)
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _create_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 16px; }"
        )
        return card

    def _create_error_label(self) -> QLabel:
        lbl = QLabel("")
        lbl.setStyleSheet("color: #f87171; font-size: 11px;")
        lbl.setVisible(False)
        return lbl

    def _create_preview_stat(self, label: str, value: str, color_hex: str) -> QVBoxLayout:
        box = QVBoxLayout()
        box.setSpacing(2)
        lbl = QLabel(label)
        lbl.setStyleSheet(
            "color: #94a3b8; font-size: 11px; text-transform: uppercase; font-weight: bold;"
        )
        val = QLabel(value)
        val.setObjectName(f"preview_{label.replace(' ', '_').lower()}")
        val.setStyleSheet(f"color: {color_hex}; font-size: 15px; font-weight: bold;")
        box.addWidget(lbl)
        box.addWidget(val)
        return box

    def _wrap_field(self, field_widget: QWidget, error_label: QLabel) -> QWidget:
        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(field_widget)
        layout.addWidget(error_label)
        return container

    def _bind_viewmodel(self) -> None:
        self.source_account_edit.textChanged.connect(self._on_source_text_changed)
        self.dest_account_edit.textChanged.connect(self._on_dest_text_changed)
        self.amount_edit.textChanged.connect(self._on_amount_text_changed)
        self.desc_edit.textChanged.connect(self.vm.set_description)

        self.vm.account_found.connect(self._on_source_account_found)
        self.vm.account_lookup_failed.connect(self._on_source_lookup_failed)
        self.vm.destination_account_found.connect(self._on_dest_account_found)
        self.vm.destination_account_failed.connect(self._on_dest_lookup_failed)
        self.vm.validation_changed.connect(self._on_validation_changed)
        self.vm.submitting_changed.connect(self._on_submitting_changed)
        self.vm.transaction_completed.connect(self._on_transaction_completed)
        self.vm.transaction_failed.connect(self._on_transaction_failed)

    def _on_source_text_changed(self, text: str) -> None:
        clean = text.strip().replace("-", "").replace(" ", "")
        if len(clean) == 12:
            self.vm.lookup_source_account(clean)
        else:
            self.source_banner.setVisible(False)
            self.source_account_error.setVisible(False)
            self.vm.source_account = None
            self._update_preview()
            self.vm.validate_transfer()

    def _on_dest_text_changed(self, text: str) -> None:
        clean = text.strip().replace("-", "").replace(" ", "")
        if len(clean) == 12:
            self.vm.lookup_destination_account(clean)
        else:
            self.dest_banner.setVisible(False)
            self.dest_account_error.setVisible(False)
            self.vm.destination_account = None
            self._update_preview()
            self.vm.validate_transfer()

    def _on_source_lookup_clicked(self) -> None:
        self.vm.lookup_source_account(self.source_account_edit.text())

    def _on_dest_lookup_clicked(self) -> None:
        self.vm.lookup_destination_account(self.dest_account_edit.text())

    def _on_amount_text_changed(self, text: str) -> None:
        self.vm.set_amount(text)
        self._update_preview()
        self.vm.validate_transfer()

    def _update_preview(self) -> None:
        src_curr, dst_curr, amt, src_proj, dst_proj = self.vm.calculate_transfer_preview()

        src_lbl = self.src_prev_box.itemAt(1).widget()
        amt_lbl = self.transfer_amt_box.itemAt(1).widget()
        src_proj_lbl = self.src_proj_box.itemAt(1).widget()
        dst_lbl = self.dst_prev_box.itemAt(1).widget()
        dst_proj_lbl = self.dst_proj_box.itemAt(1).widget()

        if isinstance(src_lbl, QLabel):
            src_lbl.setText(f"${src_curr:,.2f}")
        if isinstance(amt_lbl, QLabel):
            amt_lbl.setText(f"${amt:,.2f}")
        if isinstance(src_proj_lbl, QLabel):
            src_proj_lbl.setText(f"${src_proj:,.2f}")
            if src_proj < Decimal("0.00"):
                src_proj_lbl.setStyleSheet("color: #f87171; font-size: 15px; font-weight: bold;")
            else:
                src_proj_lbl.setStyleSheet("color: #10b981; font-size: 15px; font-weight: bold;")
        if isinstance(dst_lbl, QLabel):
            dst_lbl.setText(f"${dst_curr:,.2f}")
        if isinstance(dst_proj_lbl, QLabel):
            dst_proj_lbl.setText(f"${dst_proj:,.2f}")

    def _on_source_account_found(self, acc: AccountDTO) -> None:
        self.source_account_error.setVisible(False)
        self.source_banner.setVisible(True)
        self.source_banner_name.setText(acc.holder_name)
        self.source_banner_details.setText(
            f"Available Balance: ${acc.balance:,.2f} {acc.currency}  •  Phone: {acc.phone_number}"
        )
        if acc.is_active:
            self.source_banner_badge.setText("● Active")
            self.source_banner_badge.setStyleSheet(
                "background-color: #064e3b; color: #34d399; font-weight: bold; padding: 4px 12px; border-radius: 10px;"
            )
        else:
            self.source_banner_badge.setText("○ Closed")
            self.source_banner_badge.setStyleSheet(
                "background-color: #450a0a; color: #f87171; font-weight: bold; padding: 4px 12px; border-radius: 10px;"
            )
        self._update_preview()
        self.vm.validate_transfer()

    def _on_source_lookup_failed(self, error_msg: str) -> None:
        self.source_banner.setVisible(False)
        self.source_account_error.setText(error_msg)
        self.source_account_error.setVisible(True)
        self._update_preview()

    def _on_dest_account_found(self, acc: AccountDTO) -> None:
        self.dest_account_error.setVisible(False)
        self.dest_banner.setVisible(True)
        self.dest_banner_name.setText(acc.holder_name)
        self.dest_banner_details.setText(
            f"Current Balance: ${acc.balance:,.2f} {acc.currency}  •  Phone: {acc.phone_number}"
        )
        if acc.is_active:
            self.dest_banner_badge.setText("● Active")
            self.dest_banner_badge.setStyleSheet(
                "background-color: #064e3b; color: #34d399; font-weight: bold; padding: 4px 12px; border-radius: 10px;"
            )
        else:
            self.dest_banner_badge.setText("○ Closed")
            self.dest_banner_badge.setStyleSheet(
                "background-color: #450a0a; color: #f87171; font-weight: bold; padding: 4px 12px; border-radius: 10px;"
            )
        self._update_preview()
        self.vm.validate_transfer()

    def _on_dest_lookup_failed(self, error_msg: str) -> None:
        self.dest_banner.setVisible(False)
        self.dest_account_error.setText(error_msg)
        self.dest_account_error.setVisible(True)
        self._update_preview()

    def _on_validation_changed(self, is_valid: bool, errors: dict[str, str]) -> None:
        self.submit_btn.setEnabled(is_valid)

        if "amount" in errors:
            self.amount_error.setText(errors["amount"])
            self.amount_error.setVisible(True)
        else:
            self.amount_error.setText("")
            self.amount_error.setVisible(False)

        if "source_account" in errors:
            self.source_account_error.setText(errors["source_account"])
            self.source_account_error.setVisible(True)
        elif self.vm.source_account:
            self.source_account_error.setVisible(False)

        if "destination_account" in errors:
            self.dest_account_error.setText(errors["destination_account"])
            self.dest_account_error.setVisible(True)
        elif self.vm.destination_account:
            self.dest_account_error.setVisible(False)

    def _on_submitting_changed(self, is_submitting: bool) -> None:
        self.submit_btn.setEnabled(not is_submitting)
        self.source_account_edit.setEnabled(not is_submitting)
        self.dest_account_edit.setEnabled(not is_submitting)
        self.amount_edit.setEnabled(not is_submitting)
        self.desc_edit.setEnabled(not is_submitting)
        self.source_verify_btn.setEnabled(not is_submitting)
        self.dest_verify_btn.setEnabled(not is_submitting)
        self.clear_btn.setEnabled(not is_submitting)

        if is_submitting:
            self.status_msg.setText("Executing atomic transfer settlement...")
            self.submit_btn.setText("Processing...")
        else:
            self.status_msg.setText("")
            self.submit_btn.setText("Execute Transfer")

    def _on_transaction_completed(self, result: object) -> None:
        if isinstance(result, TransferResultDTO):
            self.status_msg.setText("✓ Transfer completed successfully.")
            self._update_preview()

            # Display modal receipt
            receipt_dlg = TransferReceiptDialog(result, parent=self)
            receipt_dlg.exec()

            # Reset amount
            self.amount_edit.clear()

    def _on_transaction_failed(self, error_msg: str) -> None:
        self.status_msg.setText("")
        QMessageBox.critical(self, "Transfer Failed", f"Could not complete transfer:\n{error_msg}")

    def _on_submit_clicked(self) -> None:
        self.vm.execute_transfer(actor="teller")

    def reset_form(self) -> None:
        """Clear all inputs, account selections, and validation state."""
        self.source_account_edit.clear()
        self.dest_account_edit.clear()
        self.amount_edit.clear()
        self.desc_edit.setText("Internal Fund Transfer")

        self.source_banner.setVisible(False)
        self.dest_banner.setVisible(False)
        self.source_account_error.setVisible(False)
        self.dest_account_error.setVisible(False)
        self.amount_error.setVisible(False)
        self.status_msg.setText("")

        self.vm.source_account = None
        self.vm.destination_account = None
        self.vm.amount_str = ""
        self._update_preview()
        self.vm.validate_transfer()
