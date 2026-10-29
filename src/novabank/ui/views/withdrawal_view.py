"""Cash Withdrawal View with overdraft prevention, real-time balance calculation, and receipt slip."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
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
from novabank.application.dto.transaction_dto import TransactionDTO
from novabank.ui.viewmodels.transaction_viewmodel import TransactionViewModel

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class WithdrawalView(QWidget):
    """Cash withdrawal terminal with mathematical overdraft prevention."""

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
        self.vm = viewmodel or TransactionViewModel(banking_service, task_runner, parent=self)

        self._setup_ui()
        self._bind_viewmodel()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 28, 28, 28)
        main_layout.setSpacing(16)

        # 1. Header Section
        header_layout = QVBoxLayout()
        header_layout.setSpacing(2)

        title_lbl = QLabel("Cash Withdrawal Desk")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #f8fafc;")

        subtitle_lbl = QLabel(
            "Process cash withdrawals with real-time balance checks and overdraft prevention."
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

        # 2. Account Lookup Card
        lookup_card = self._create_card()
        lookup_layout = QVBoxLayout(lookup_card)
        lookup_layout.setSpacing(12)

        card_title = QLabel("1. Source Customer Account")
        card_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #cbd5e1;")
        lookup_layout.addWidget(card_title)

        acc_input_layout = QHBoxLayout()
        acc_input_layout.setSpacing(8)

        self.account_edit = QLineEdit()
        self.account_edit.setPlaceholderText("Enter 12-digit Account Number...")
        self.account_edit.setStyleSheet(
            "QLineEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 12px; color: #f8fafc; font-family: monospace; font-size: 14px; }"
        )
        acc_input_layout.addWidget(self.account_edit, stretch=2)

        self.verify_btn = QPushButton("Lookup Account")
        self.verify_btn.setStyleSheet(
            "QPushButton { background-color: #334155; border-radius: 6px; padding: 8px 16px; color: #f8fafc; font-weight: 500; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.verify_btn.clicked.connect(self._on_lookup_clicked)
        acc_input_layout.addWidget(self.verify_btn)
        lookup_layout.addLayout(acc_input_layout)

        self.account_error = self._create_error_label()
        lookup_layout.addWidget(self.account_error)

        # Verified Account Info Banner
        self.account_banner = QFrame()
        self.account_banner.setStyleSheet(
            "QFrame { background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; padding: 12px; }"
        )
        self.account_banner.setVisible(False)
        banner_layout = QHBoxLayout(self.account_banner)
        banner_layout.setContentsMargins(8, 8, 8, 8)

        banner_text_box = QVBoxLayout()
        self.banner_name = QLabel("Customer Name")
        self.banner_name.setStyleSheet("font-size: 15px; font-weight: bold; color: #f8fafc;")
        self.banner_details = QLabel("Balance: $0.00 USD  •  Status: Active")
        self.banner_details.setStyleSheet("color: #94a3b8; font-size: 12px;")
        banner_text_box.addWidget(self.banner_name)
        banner_text_box.addWidget(self.banner_details)
        banner_layout.addLayout(banner_text_box)
        banner_layout.addStretch()

        self.banner_badge = QLabel("● Active")
        self.banner_badge.setStyleSheet(
            "background-color: #064e3b; color: #34d399; font-weight: bold; padding: 4px 12px; border-radius: 10px;"
        )
        banner_layout.addWidget(self.banner_badge)
        lookup_layout.addWidget(self.account_banner)

        content_layout.addWidget(lookup_card)

        # 3. Transaction Input Card
        tx_card = self._create_card()
        tx_layout = QVBoxLayout(tx_card)
        tx_layout.setSpacing(12)

        tx_card_title = QLabel("2. Withdrawal Amount & Narration")
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

        self.desc_edit = QLineEdit("Counter Cash Withdrawal")
        self.desc_edit.setStyleSheet(
            "QLineEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 8px 12px; color: #f8fafc; }"
        )

        tx_form.addRow(
            "Withdrawal Amount ($) *:", self._wrap_field(self.amount_edit, self.amount_error)
        )
        tx_form.addRow("Description:", self.desc_edit)
        tx_layout.addLayout(tx_form)
        content_layout.addWidget(tx_card)

        # 4. Live Balance Deduction Preview Strip
        preview_card = self._create_card()
        preview_layout = QHBoxLayout(preview_card)
        preview_layout.setContentsMargins(16, 12, 16, 12)
        preview_layout.setSpacing(16)

        self.prev_bal_box = self._create_preview_stat("Current Balance", "$0.00", "#94a3b8")
        minus_sign = QLabel("-")
        minus_sign.setStyleSheet("font-size: 20px; color: #64748b; font-weight: bold;")
        self.withdraw_stat_box = self._create_preview_stat("Withdrawal Amount", "$0.00", "#f87171")
        equals_sign = QLabel("=")
        equals_sign.setStyleSheet("font-size: 20px; color: #64748b; font-weight: bold;")
        self.projected_bal_box = self._create_preview_stat("Remaining Balance", "$0.00", "#10b981")

        preview_layout.addLayout(self.prev_bal_box)
        preview_layout.addWidget(minus_sign, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_layout.addLayout(self.withdraw_stat_box)
        preview_layout.addWidget(equals_sign, alignment=Qt.AlignmentFlag.AlignCenter)
        preview_layout.addLayout(self.projected_bal_box)
        content_layout.addWidget(preview_card)

        # 5. Action Buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)

        self.status_msg = QLabel("")
        self.status_msg.setStyleSheet("color: #38bdf8; font-weight: 500;")
        action_layout.addWidget(self.status_msg)
        action_layout.addStretch()

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setStyleSheet(
            "QPushButton { background-color: #334155; border-radius: 6px; padding: 8px 18px; color: #f8fafc; }"
            "QPushButton:hover { background-color: #475569; }"
        )
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        action_layout.addWidget(self.clear_btn)

        self.submit_btn = QPushButton("Execute Withdrawal")
        self.submit_btn.setEnabled(False)
        self.submit_btn.setStyleSheet(
            "QPushButton { background-color: #dc2626; border-radius: 6px; padding: 8px 24px; color: #ffffff; font-weight: bold; font-size: 14px; }"
            "QPushButton:hover { background-color: #b91c1c; }"
            "QPushButton:disabled { background-color: #1e293b; color: #64748b; }"
        )
        self.submit_btn.clicked.connect(self._on_submit_clicked)
        action_layout.addWidget(self.submit_btn)

        content_layout.addLayout(action_layout)
        content_layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _create_card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px; }"
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
        val.setStyleSheet(f"color: {color_hex}; font-size: 16px; font-weight: bold;")
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
        self.account_edit.textChanged.connect(self._on_account_text_changed)
        self.amount_edit.textChanged.connect(self._on_amount_text_changed)
        self.desc_edit.textChanged.connect(self.vm.set_description)

        self.vm.account_found.connect(self._on_account_found)
        self.vm.account_lookup_failed.connect(self._on_account_lookup_failed)
        self.vm.validation_changed.connect(self._on_validation_changed)
        self.vm.submitting_changed.connect(self._on_submitting_changed)
        self.vm.transaction_completed.connect(self._on_transaction_completed)
        self.vm.transaction_failed.connect(self._on_transaction_failed)

    def _on_account_text_changed(self, text: str) -> None:
        clean = text.strip().replace("-", "").replace(" ", "")
        if len(clean) == 12:
            self.vm.lookup_source_account(clean)
        else:
            self.account_banner.setVisible(False)
            self.account_error.setVisible(False)
            self.vm.source_account = None
            self._update_preview()
            self.vm.validate_withdrawal()

    def _on_lookup_clicked(self) -> None:
        self.vm.lookup_source_account(self.account_edit.text())

    def _on_amount_text_changed(self, text: str) -> None:
        self.vm.set_amount(text)
        self._update_preview()
        self.vm.validate_withdrawal()

    def _update_preview(self) -> None:
        current, withdraw_amt, projected = self.vm.calculate_withdrawal_preview()
        curr_lbl = self.prev_bal_box.itemAt(1).widget()
        with_lbl = self.withdraw_stat_box.itemAt(1).widget()
        proj_lbl = self.projected_bal_box.itemAt(1).widget()

        if isinstance(curr_lbl, QLabel):
            curr_lbl.setText(f"${current:,.2f}")
        if isinstance(with_lbl, QLabel):
            with_lbl.setText(f"${withdraw_amt:,.2f}")
        if isinstance(proj_lbl, QLabel):
            proj_lbl.setText(f"${projected:,.2f}")
            if projected < Decimal("0.00"):
                proj_lbl.setStyleSheet("color: #f87171; font-size: 16px; font-weight: bold;")
            else:
                proj_lbl.setStyleSheet("color: #10b981; font-size: 16px; font-weight: bold;")

    def _on_account_found(self, acc: AccountDTO) -> None:
        self.account_error.setVisible(False)
        self.account_banner.setVisible(True)
        self.banner_name.setText(acc.holder_name)
        self.banner_details.setText(
            f"Available Balance: ${acc.balance:,.2f} {acc.currency}  •  Phone: {acc.phone_number}"
        )

        if acc.is_active:
            self.banner_badge.setText("● Active")
            self.banner_badge.setStyleSheet(
                "background-color: #064e3b; color: #34d399; font-weight: bold; padding: 4px 12px; border-radius: 10px;"
            )
        else:
            self.banner_badge.setText("○ Closed")
            self.banner_badge.setStyleSheet(
                "background-color: #450a0a; color: #f87171; font-weight: bold; padding: 4px 12px; border-radius: 10px;"
            )

        self._update_preview()
        self.vm.validate_withdrawal()

    def _on_account_lookup_failed(self, error_msg: str) -> None:
        self.account_banner.setVisible(False)
        self.account_error.setText(error_msg)
        self.account_error.setVisible(True)
        self._update_preview()

    def _on_validation_changed(self, is_valid: bool, errors: dict[str, str]) -> None:
        self.submit_btn.setEnabled(is_valid)

        if "amount" in errors:
            self.amount_error.setText(errors["amount"])
            self.amount_error.setVisible(True)
        else:
            self.amount_error.setText("")
            self.amount_error.setVisible(False)

        if "account" in errors:
            self.account_error.setText(errors["account"])
            self.account_error.setVisible(True)
        elif not self.account_error.text() or "inactive/closed" in self.account_error.text():
            self.account_error.setText("")
            self.account_error.setVisible(False)

    def _on_submitting_changed(self, is_submitting: bool) -> None:
        self.submit_btn.setEnabled(not is_submitting and self.submit_btn.isEnabled())
        self.clear_btn.setEnabled(not is_submitting)
        self.account_edit.setEnabled(not is_submitting)
        self.amount_edit.setEnabled(not is_submitting)
        self.desc_edit.setEnabled(not is_submitting)

        if is_submitting:
            self.status_msg.setText("Executing atomic withdrawal transaction...")
        else:
            self.status_msg.setText("")

    def _on_submit_clicked(self) -> None:
        self.vm.execute_withdrawal()

    def _on_clear_clicked(self) -> None:
        self.account_edit.clear()
        self.amount_edit.clear()
        self.desc_edit.setText("Counter Cash Withdrawal")
        self.account_banner.setVisible(False)
        self.account_error.setVisible(False)
        self.amount_error.setVisible(False)
        self.vm.source_account = None
        self.vm.set_amount("")
        self._update_preview()
        self.submit_btn.setEnabled(False)

    def _on_transaction_completed(self, dto: TransactionDTO) -> None:
        receipt_text = (
            f"WITHDRAWAL RECEIPT\n"
            f"-----------------------------------------\n"
            f"Reference:   {dto.transaction_ref}\n"
            f"Account:     {dto.account_number}\n"
            f"Amount:      -${dto.amount:,.2f} {dto.currency}\n"
            f"New Balance: ${dto.balance_after:,.2f} {dto.currency}\n"
            f"Description: {dto.description}\n"
            f"Date/Time:   {dto.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"-----------------------------------------\n"
            f"Cash dispensed and ledger updated successfully."
        )

        QMessageBox.information(
            self,
            "Withdrawal Successful",
            receipt_text,
            QMessageBox.StandardButton.Ok,
        )

        self.amount_edit.clear()
        self._update_preview()

    def _on_transaction_failed(self, error_msg: str) -> None:
        QMessageBox.critical(
            self,
            "Withdrawal Failed",
            f"Cash withdrawal could not be completed:\n\n{error_msg}",
        )
