"""Account Closure dialog with balance guardrails, reason tracking, and explicit teller confirmation."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.account_dto import AccountDTO


class AccountCloseDialog(QDialog):
    """Modal dialog managing account deactivation with zero-balance invariant checks."""

    REASONS = [
        "Customer Request",
        "Account Consolidation",
        "Customer Relocation",
        "Service Dissatisfaction",
        "Administrative / Operational",
        "Other",
    ]

    def __init__(self, account: AccountDTO, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.account = account
        self.setWindowTitle("Account Closure & Deactivation")
        self.setMinimumWidth(500)
        self.setStyleSheet(
            "QDialog { background-color: #FFFFFF; color: #172033; } QLabel { color: #172033; }"
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(20)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_lbl = QLabel("Terminate Customer Account")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033;")

        acc_num = f"{self.account.account_number[:4]}-{self.account.account_number[4:8]}-{self.account.account_number[8:]}"
        subtitle_lbl = QLabel(f"Account: {acc_num}  •  Holder: {self.account.holder_name}")
        subtitle_lbl.setStyleSheet("font-size: 13px; color: #64748B; font-family: Consolas, monospace;")

        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        layout.addLayout(title_box)

        # Guardrail Check: Balance must be zero
        has_balance = self.account.balance > Decimal("0.00")

        if has_balance:
            # Blocked View
            blocked_frame = QFrame()
            blocked_frame.setStyleSheet(
                "QFrame { background-color: #FEF2F2; border: 1px solid #FECACA; border-radius: 8px; padding: 18px; }"
            )
            blocked_layout = QVBoxLayout(blocked_frame)
            blocked_layout.setSpacing(10)

            warning_title = QLabel("Action Blocked: Non-Zero Balance")
            warning_title.setStyleSheet("color: #DC2626; font-weight: 700; font-size: 14px;")

            warning_msg = QLabel(
                f"This account currently holds an active balance of "
                f"${self.account.balance:,.2f} {self.account.currency}.\n\n"
                f"Per core banking invariants and audit rules, an account cannot be closed "
                f"while funds remain. Please perform a withdrawal or transfer to zero out "
                f"the balance before proceeding with closure."
            )
            warning_msg.setWordWrap(True)
            warning_msg.setStyleSheet("color: #991B1B; font-size: 13px; line-height: 1.4;")

            blocked_layout.addWidget(warning_title)
            blocked_layout.addWidget(warning_msg)
            layout.addWidget(blocked_frame)

            # Dismiss Button Only
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            dismiss_btn = QPushButton("Close")
            dismiss_btn.setProperty("class", "SecondaryButton")
            dismiss_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            dismiss_btn.clicked.connect(self.reject)
            btn_layout.addWidget(dismiss_btn)
            layout.addLayout(btn_layout)

        else:
            # Allowed View: Balance is exactly zero
            info_frame = QFrame()
            info_frame.setProperty("class", "CardFrame")
            form = QFormLayout(info_frame)
            form.setSpacing(12)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            balance_label = QLabel(
                f"${self.account.balance:,.2f} {self.account.currency} (Verified Zero)"
            )
            balance_label.setStyleSheet("color: #15803D; font-weight: 700; font-size: 13px;")

            self.reason_combo = QComboBox()
            self.reason_combo.addItems(self.REASONS)

            self.notes_edit = QLineEdit()
            self.notes_edit.setPlaceholderText("Additional closure notes or remarks (optional)")

            form.addRow("Verified Balance:", balance_label)
            form.addRow("Closure Reason *:", self.reason_combo)
            form.addRow("Notes / Remarks:", self.notes_edit)
            layout.addWidget(info_frame)

            # Confirmation Checkbox
            self.confirm_check = QCheckBox(
                "I confirm that customer identity has been verified and this account should be deactivated permanently."
            )
            self.confirm_check.setStyleSheet("color: #172033; font-size: 13px;")
            self.confirm_check.stateChanged.connect(self._on_check_changed)
            layout.addWidget(self.confirm_check)

            # Action Buttons
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setProperty("class", "SecondaryButton")
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.clicked.connect(self.reject)
            btn_layout.addWidget(cancel_btn)

            self.confirm_btn = QPushButton("Confirm Closure")
            self.confirm_btn.setEnabled(False)
            self.confirm_btn.setProperty("class", "DangerButton")
            self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.confirm_btn.clicked.connect(self.accept)
            btn_layout.addWidget(self.confirm_btn)

            layout.addLayout(btn_layout)

    def _on_check_changed(self, state: int) -> None:
        self.confirm_btn.setEnabled(state == Qt.CheckState.Checked.value)

    def get_closure_reason(self) -> str:
        """Return the formatted closure reason including notes."""
        if hasattr(self, "reason_combo"):
            reason = self.reason_combo.currentText()
            notes = self.notes_edit.text().strip() if hasattr(self, "notes_edit") else ""
            if notes:
                return f"{reason} - {notes}"
            return reason
        return "Customer Request"
