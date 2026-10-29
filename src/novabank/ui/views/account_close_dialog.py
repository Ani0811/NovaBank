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
        self.setMinimumWidth(480)
        self.setStyleSheet(
            "QDialog { background-color: #0f172a; color: #f8fafc; }QLabel { color: #f8fafc; }"
        )

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # Header Title
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_lbl = QLabel("Terminate Customer Account")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #f8fafc;")

        acc_num = f"{self.account.account_number[:4]}-{self.account.account_number[4:8]}-{self.account.account_number[8:]}"
        subtitle_lbl = QLabel(f"Account: {acc_num}  •  Holder: {self.account.holder_name}")
        subtitle_lbl.setStyleSheet("font-size: 12px; color: #94a3b8; font-family: monospace;")

        title_box.addWidget(title_lbl)
        title_box.addWidget(subtitle_lbl)
        layout.addLayout(title_box)

        # Guardrail Check: Balance must be zero
        has_balance = self.account.balance > Decimal("0.00")

        if has_balance:
            # Blocked View
            blocked_frame = QFrame()
            blocked_frame.setStyleSheet(
                "QFrame { background-color: #450a0a; border: 1px solid #dc2626; border-radius: 8px; padding: 16px; }"
            )
            blocked_layout = QVBoxLayout(blocked_frame)
            blocked_layout.setSpacing(8)

            warning_title = QLabel("Action Blocked: Non-Zero Balance")
            warning_title.setStyleSheet("color: #f87171; font-weight: bold; font-size: 14px;")

            warning_msg = QLabel(
                f"This account currently holds an active balance of "
                f"${self.account.balance:,.2f} {self.account.currency}.\n\n"
                f"Per core banking invariants and audit rules, an account cannot be closed "
                f"while funds remain. Please perform a withdrawal or transfer to zero out "
                f"the balance before proceeding with closure."
            )
            warning_msg.setWordWrap(True)
            warning_msg.setStyleSheet("color: #fecaca; font-size: 13px; line-height: 1.4;")

            blocked_layout.addWidget(warning_title)
            blocked_layout.addWidget(warning_msg)
            layout.addWidget(blocked_frame)

            # Dismiss Button Only
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()
            dismiss_btn = QPushButton("Close")
            dismiss_btn.setStyleSheet(
                "QPushButton { background-color: #334155; border-radius: 6px; padding: 8px 20px; color: #f8fafc; }"
                "QPushButton:hover { background-color: #475569; }"
            )
            dismiss_btn.clicked.connect(self.reject)
            btn_layout.addWidget(dismiss_btn)
            layout.addLayout(btn_layout)

        else:
            # Allowed View: Balance is exactly zero
            info_frame = QFrame()
            info_frame.setStyleSheet(
                "QFrame { background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 14px; }"
            )
            form = QFormLayout(info_frame)
            form.setSpacing(12)
            form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

            balance_label = QLabel(
                f"${self.account.balance:,.2f} {self.account.currency} (Verified Zero)"
            )
            balance_label.setStyleSheet("color: #34d399; font-weight: bold;")

            self.reason_combo = QComboBox()
            self.reason_combo.addItems(self.REASONS)
            self.reason_combo.setStyleSheet(
                "QComboBox { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 6px 10px; color: #f8fafc; }"
            )

            self.notes_edit = QLineEdit()
            self.notes_edit.setPlaceholderText("Additional closure notes or remarks (optional)")
            self.notes_edit.setStyleSheet(
                "QLineEdit { background-color: #0f172a; border: 1px solid #475569; border-radius: 6px; padding: 6px 10px; color: #f8fafc; }"
            )

            form.addRow("Verified Balance:", balance_label)
            form.addRow("Closure Reason *:", self.reason_combo)
            form.addRow("Notes / Remarks:", self.notes_edit)
            layout.addWidget(info_frame)

            # Confirmation Checkbox
            self.confirm_check = QCheckBox(
                "I confirm that customer identity has been verified and this account should be deactivated permanently."
            )
            self.confirm_check.setStyleSheet("color: #cbd5e1; font-size: 12px;")
            self.confirm_check.stateChanged.connect(self._on_check_changed)
            layout.addWidget(self.confirm_check)

            # Action Buttons
            btn_layout = QHBoxLayout()
            btn_layout.addStretch()

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setStyleSheet(
                "QPushButton { background-color: #334155; border-radius: 6px; padding: 8px 18px; color: #cbd5e1; }"
                "QPushButton:hover { background-color: #475569; }"
            )
            cancel_btn.clicked.connect(self.reject)
            btn_layout.addWidget(cancel_btn)

            self.confirm_btn = QPushButton("Confirm Closure")
            self.confirm_btn.setEnabled(False)
            self.confirm_btn.setStyleSheet(
                "QPushButton { background-color: #dc2626; border-radius: 6px; padding: 8px 20px; color: #ffffff; font-weight: bold; }"
                "QPushButton:hover { background-color: #b91c1c; }"
                "QPushButton:disabled { background-color: #1e293b; color: #64748b; }"
            )
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
