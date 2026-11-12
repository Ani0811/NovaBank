"""Account Detail View presenting customer profile inspection, contact modification, and account closure."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
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
from novabank.ui.resources.icons import get_icon
from novabank.ui.viewmodels.account_detail_viewmodel import AccountDetailViewModel
from novabank.ui.views.account_close_dialog import AccountCloseDialog

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class AccountDetailView(QWidget):
    """Institutional view widget for inspecting and modifying customer account details."""

    # Navigation signal to return to accounts directory
    back_requested = Signal()

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        viewmodel: Optional[AccountDetailViewModel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm = viewmodel or AccountDetailViewModel(banking_service, task_runner, parent=self)

        self._setup_ui()
        self._bind_viewmodel()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 24, 28, 28)
        main_layout.setSpacing(16)

        # 1. Navigation Header
        top_bar = QHBoxLayout()
        self.back_btn = QPushButton("Back to Accounts")
        self.back_btn.setProperty("class", "SecondaryButton")
        self.back_btn.setIcon(get_icon("arrow_left", color="#172033", size=14))
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(self.back_requested.emit)
        top_bar.addWidget(self.back_btn)
        top_bar.addStretch()

        self.status_badge = QLabel("● Active")
        self.status_badge.setProperty("class", "StatusIndicatorPill")
        self.status_badge.setProperty("status", "success")
        top_bar.addWidget(self.status_badge)
        main_layout.addLayout(top_bar)

        # Title Card
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.holder_title = QLabel("Customer Profile")
        self.holder_title.setStyleSheet("font-size: 22px; font-weight: 700; color: #172033;")

        self.account_num_subtitle = QLabel("Account: ----")
        self.account_num_subtitle.setStyleSheet(
            "font-size: 13px; color: #64748B; font-family: Consolas, monospace;"
        )
        title_box.addWidget(self.holder_title)
        title_box.addWidget(self.account_num_subtitle)
        main_layout.addLayout(title_box)

        # Scroll Area for main content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 16, 0)
        content_layout.setSpacing(18)

        # 2. KPI Summary Cards
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(14)

        self.balance_card = self._create_kpi_card("Current Balance", "$0.00 USD", "#15803D")
        self.currency_card = self._create_kpi_card("Currency", "USD", "#2563EB")
        self.opened_card = self._create_kpi_card("Opened Date", "----", "#172033")
        self.version_card = self._create_kpi_card("Ledger Version", "v1", "#64748B")

        kpi_layout.addWidget(self.balance_card)
        kpi_layout.addWidget(self.currency_card)
        kpi_layout.addWidget(self.opened_card)
        kpi_layout.addWidget(self.version_card)
        content_layout.addLayout(kpi_layout)

        # 3. Read-only Identity Section
        identity_group = self._create_card_container("Core Identity Information (Immutable)")
        identity_form = QFormLayout(identity_group)
        identity_form.setSpacing(12)
        identity_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.display_acc_edit = QLineEdit()
        self.display_acc_edit.setReadOnly(True)
        self.display_acc_edit.setStyleSheet("font-family: Consolas, monospace; background-color: #F8FAFC;")

        self.display_name_edit = QLineEdit()
        self.display_name_edit.setReadOnly(True)
        self.display_name_edit.setStyleSheet("background-color: #F8FAFC;")

        self.display_dob_edit = QLineEdit()
        self.display_dob_edit.setReadOnly(True)
        self.display_dob_edit.setStyleSheet("background-color: #F8FAFC;")

        identity_form.addRow("Account Number:", self.display_acc_edit)
        identity_form.addRow("Legal Holder Name:", self.display_name_edit)
        identity_form.addRow("Date of Birth:", self.display_dob_edit)
        content_layout.addWidget(identity_group)

        # 4. Editable Contact Section
        contact_group = self._create_card_container("Contact & Address Information (Editable)")
        contact_form = QFormLayout(contact_group)
        contact_form.setSpacing(12)
        contact_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.phone_edit = QLineEdit()
        self.phone_error = self._create_error_label()

        self.address_edit = QLineEdit()
        self.address_error = self._create_error_label()

        self.city_edit = QLineEdit()
        self.city_error = self._create_error_label()

        self.state_edit = QLineEdit()
        self.state_error = self._create_error_label()

        self.country_edit = QLineEdit()
        self.country_error = self._create_error_label()

        contact_form.addRow("Phone Number *:", self._wrap_field(self.phone_edit, self.phone_error))
        contact_form.addRow(
            "Street Address *:", self._wrap_field(self.address_edit, self.address_error)
        )
        contact_form.addRow("City *:", self._wrap_field(self.city_edit, self.city_error))
        contact_form.addRow("State *:", self._wrap_field(self.state_edit, self.state_error))
        contact_form.addRow("Country *:", self._wrap_field(self.country_edit, self.country_error))
        content_layout.addWidget(contact_group)

        # 5. Action Buttons Footer
        action_layout = QHBoxLayout()
        action_layout.setSpacing(12)

        self.op_status_label = QLabel("")
        self.op_status_label.setStyleSheet("color: #2563EB; font-weight: 500;")
        action_layout.addWidget(self.op_status_label)
        action_layout.addStretch()

        self.freeze_btn = QPushButton("Freeze Account")
        self.freeze_btn.setProperty("class", "SecondaryButton")
        self.freeze_btn.setStyleSheet("color: #B45309; border-color: #FDE68A;")
        self.freeze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.freeze_btn.clicked.connect(self._on_freeze_clicked)
        action_layout.addWidget(self.freeze_btn)

        self.close_btn = QPushButton("Close Account")
        self.close_btn.setProperty("class", "DangerButton")
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self._on_close_clicked)
        action_layout.addWidget(self.close_btn)

        self.discard_btn = QPushButton("Discard Changes")
        self.discard_btn.setProperty("class", "SecondaryButton")
        self.discard_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.discard_btn.clicked.connect(self.vm.reset_edits)
        action_layout.addWidget(self.discard_btn)

        self.save_btn = QPushButton("Save Changes")
        self.save_btn.setProperty("class", "PrimaryButton")
        self.save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.save_btn.clicked.connect(self._on_save_clicked)
        action_layout.addWidget(self.save_btn)

        content_layout.addLayout(action_layout)
        content_layout.addStretch()

        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

    def _create_kpi_card(self, title: str, default_val: str, color_hex: str) -> QFrame:
        card = QFrame()
        card.setProperty("class", "CardFrame")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        title_lbl = QLabel(title)
        title_lbl.setProperty("class", "CardTitle")
        val_lbl = QLabel(default_val)
        val_lbl.setObjectName(f"kpi_{title.replace(' ', '_').lower()}")
        val_lbl.setStyleSheet(f"color: {color_hex}; font-size: 18px; font-weight: 700;")

        layout.addWidget(title_lbl)
        layout.addWidget(val_lbl)
        return card

    def _create_card_container(self, title: str) -> QFrame:
        frame = QFrame()
        frame.setProperty("class", "CardFrame")
        return frame

    def _create_error_label(self) -> QLabel:
        lbl = QLabel("")
        lbl.setStyleSheet("color: #DC2626; font-size: 11px; font-weight: 600;")
        lbl.setVisible(False)
        return lbl

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
        # Form field changes
        self.phone_edit.textChanged.connect(self.vm.set_phone_number)
        self.address_edit.textChanged.connect(self.vm.set_address_line)
        self.city_edit.textChanged.connect(self.vm.set_city)
        self.state_edit.textChanged.connect(self.vm.set_state)
        self.country_edit.textChanged.connect(self.vm.set_country)

        # ViewModel -> View updates
        self.vm.account_loaded.connect(self._render_account)
        self.vm.profile_updated.connect(self._on_profile_updated)
        self.vm.account_closed.connect(self._on_account_closed)
        self.vm.account_frozen.connect(self._on_account_frozen)
        self.vm.account_unfrozen.connect(self._on_account_unfrozen)
        self.vm.validation_changed.connect(self._on_validation_changed)
        self.vm.loading_changed.connect(self._on_loading_changed)
        self.vm.operation_error.connect(self._on_operation_error)

    def set_account(self, account: AccountDTO) -> None:
        """Load account DTO into view."""
        self.vm.set_account(account)

    def load_account_number(self, account_number: str) -> None:
        """Fetch and display account by number."""
        self.vm.load_account(account_number)

    def _render_account(self, acc: AccountDTO) -> None:
        formatted_num = (
            f"{acc.account_number[:4]}-{acc.account_number[4:8]}-{acc.account_number[8:]}"
        )
        self.holder_title.setText(acc.holder_name)
        self.account_num_subtitle.setText(f"Account: {formatted_num}")

        # Update KPI labels
        self.balance_card.findChild(QLabel, "kpi_current_balance").setText(f"${acc.balance:,.2f}")
        self.currency_card.findChild(QLabel, "kpi_currency").setText(acc.currency)
        open_date_str = acc.created_at.strftime("%Y-%m-%d") if acc.created_at else "----"
        self.opened_card.findChild(QLabel, "kpi_opened_date").setText(open_date_str)
        self.version_card.findChild(QLabel, "kpi_ledger_version").setText(f"v{acc.version}")

        # Status badge
        if not acc.is_active:
            self.status_badge.setText("○ Closed")
            self.status_badge.setProperty("status", "danger")
            self.close_btn.setEnabled(False)
            self.freeze_btn.setEnabled(False)
        elif acc.is_frozen:
            self.status_badge.setText("▲ Frozen (Risk Hold)")
            self.status_badge.setProperty("status", "warning")
            self.freeze_btn.setText("Unfreeze Account")
            self.freeze_btn.setStyleSheet("color: #15803D; border-color: #BBF7D0;")
            self.freeze_btn.setEnabled(True)
            self.close_btn.setEnabled(False)
        else:
            self.status_badge.setText("● Active")
            self.status_badge.setProperty("status", "success")
            self.freeze_btn.setText("Freeze Account")
            self.freeze_btn.setStyleSheet("color: #B45309; border-color: #FDE68A;")
            self.freeze_btn.setEnabled(True)
            self.close_btn.setEnabled(True)

        self.status_badge.style().unpolish(self.status_badge)
        self.status_badge.style().polish(self.status_badge)

        # Identity fields
        self.display_acc_edit.setText(formatted_num)
        self.display_name_edit.setText(acc.holder_name)
        self.display_dob_edit.setText(acc.dob.strftime("%Y-%m-%d") if acc.dob else "")

        # Editable contact fields
        self.phone_edit.setText(acc.phone_number)
        self.address_edit.setText(acc.address_line)
        self.city_edit.setText(acc.city)
        self.state_edit.setText(acc.state)
        self.country_edit.setText(acc.country)

        self.op_status_label.setText("")

    def _on_validation_changed(self, is_valid: bool, errors: dict[str, str]) -> None:
        self.save_btn.setEnabled(is_valid)

        self._update_error_field(self.phone_error, errors.get("phone_number"))
        self._update_error_field(self.address_error, errors.get("address_line"))
        self._update_error_field(self.city_error, errors.get("city"))
        self._update_error_field(self.state_error, errors.get("state"))
        self._update_error_field(self.country_error, errors.get("country"))

    def _update_error_field(self, label: QLabel, msg: Optional[str]) -> None:
        if msg:
            label.setText(msg)
            label.setVisible(True)
        else:
            label.setText("")
            label.setVisible(False)

    def _on_loading_changed(self, is_loading: bool) -> None:
        self.save_btn.setEnabled(not is_loading and self.save_btn.isEnabled())
        self.discard_btn.setEnabled(not is_loading)
        self.close_btn.setEnabled(not is_loading and self.close_btn.isEnabled())

        if is_loading:
            self.op_status_label.setText("Processing update...")
        else:
            self.op_status_label.setText("")

    def _on_save_clicked(self) -> None:
        self.vm.save_profile()

    def _on_profile_updated(self, updated_dto: AccountDTO) -> None:
        self._render_account(updated_dto)
        QMessageBox.information(
            self,
            "Profile Updated",
            f"Customer profile for {updated_dto.holder_name} has been successfully updated and recorded.",
        )

    def _on_close_clicked(self) -> None:
        if not self.vm.account:
            return

        dialog = AccountCloseDialog(self.vm.account, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            reason = dialog.get_closure_reason()
            self.vm.close_account(reason=reason)

    def _on_account_closed(self, closed_dto: AccountDTO) -> None:
        self._render_account(closed_dto)
        QMessageBox.information(
            self,
            "Account Closed",
            f"Account {closed_dto.account_number} ({closed_dto.holder_name}) has been deactivated.",
        )

    def _on_freeze_clicked(self) -> None:
        if not self.vm.account:
            return

        if self.vm.account.is_frozen:
            confirm = QMessageBox.question(
                self,
                "Release Administrative Hold",
                f"Are you sure you want to release the freeze on account {self.vm.account.account_number}?\n\n"
                "This will immediately restore normal withdrawal and transfer capabilities.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if confirm == QMessageBox.StandardButton.Yes:
                self.vm.unfreeze_account(reason="Hold released by operator")
        else:
            from PySide6.QtWidgets import QInputDialog
            reason, ok = QInputDialog.getText(
                self,
                "Administrative Account Freeze",
                f"Enter reason for placing risk hold on account {self.vm.account.account_number}:",
                QLineEdit.EchoMode.Normal,
                "Suspected credential compromise / AML review",
            )
            if ok and reason.strip():
                self.vm.freeze_account(reason=reason.strip())

    def _on_account_frozen(self, frozen_dto: AccountDTO) -> None:
        self._render_account(frozen_dto)
        self.op_status_label.setText("Account administratively frozen.")
        self.op_status_label.setStyleSheet("color: #B45309; font-weight: 600;")
        QMessageBox.warning(
            self,
            "Account Frozen",
            f"Account {frozen_dto.account_number} has been placed under administrative hold.\n\n"
            "Debits and withdrawals are now restricted.",
        )

    def _on_account_unfrozen(self, unfrozen_dto: AccountDTO) -> None:
        self._render_account(unfrozen_dto)
        self.op_status_label.setText("Account hold released.")
        self.op_status_label.setStyleSheet("color: #15803D; font-weight: 600;")
        QMessageBox.information(
            self,
            "Hold Released",
            f"Administrative hold on account {unfrozen_dto.account_number} has been released.\n\n"
            "Normal operations have been restored.",
        )

    def _on_operation_error(self, err_msg: str) -> None:
        QMessageBox.critical(
            self,
            "Operation Error",
            f"An error occurred:\n\n{err_msg}",
        )
