"""Open Account view presenting form inputs, real-time validation, and creation dialog."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
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

from novabank.application.dto.account_dto import OpenAccountResultDTO
from novabank.ui.viewmodels.open_account_viewmodel import OpenAccountViewModel

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class OpenAccountView(QWidget):
    """View widget for creating and registering new bank customer accounts."""

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        viewmodel: Optional[OpenAccountViewModel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm = viewmodel or OpenAccountViewModel(self)

        self._setup_ui()
        self._bind_viewmodel()
        self.vm.validate()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(28, 28, 28, 28)
        main_layout.setSpacing(20)

        # Header Section
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        title_label = QLabel("Open New Customer Account")
        title_label.setObjectName("viewTitle")
        title_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #f8fafc;")

        subtitle_label = QLabel(
            "Enter customer identification and initial account details to register an account."
        )
        subtitle_label.setStyleSheet("font-size: 13px; color: #94a3b8;")

        header_layout.addWidget(title_label)
        header_layout.addWidget(subtitle_label)
        main_layout.addLayout(header_layout)

        # Scroll area for form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)
        form_layout.setSpacing(16)
        form_layout.setContentsMargins(0, 0, 16, 0)

        # --- Section 1: Customer Personal Details ---
        personal_group = self._create_card("Personal Information")
        personal_form = QFormLayout(personal_group)
        personal_form.setSpacing(12)
        personal_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Full Legal Name (e.g. Jane Doe)")
        self.name_error = self._create_error_label()

        self.dob_edit = QDateEdit()
        self.dob_edit.setCalendarPopup(True)
        self.dob_edit.setDisplayFormat("yyyy-MM-dd")
        default_dob = self.vm.dob
        self.dob_edit.setDate(QDate(default_dob.year, default_dob.month, default_dob.day))
        self.dob_edit.setMaximumDate(QDate.currentDate().addYears(-18))
        self.dob_error = self._create_error_label()

        self.phone_edit = QLineEdit()
        self.phone_edit.setPlaceholderText("10-digit Phone Number (e.g. 5551234567)")
        self.phone_error = self._create_error_label()

        personal_form.addRow("Full Name *:", self._wrap_field(self.name_edit, self.name_error))
        personal_form.addRow("Date of Birth *:", self._wrap_field(self.dob_edit, self.dob_error))
        personal_form.addRow("Phone Number *:", self._wrap_field(self.phone_edit, self.phone_error))
        form_layout.addWidget(personal_group)

        # --- Section 2: Address Information ---
        address_group = self._create_card("Address Details")
        address_form = QFormLayout(address_group)
        address_form.setSpacing(12)
        address_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.address_edit = QLineEdit()
        self.address_edit.setPlaceholderText("Street Address / Apt / Suite")
        self.address_error = self._create_error_label()

        self.city_edit = QLineEdit()
        self.city_edit.setPlaceholderText("City")
        self.city_error = self._create_error_label()

        self.state_edit = QLineEdit()
        self.state_edit.setPlaceholderText("State / Province")
        self.state_error = self._create_error_label()

        self.country_edit = QLineEdit()
        self.country_edit.setText("United States")
        self.country_error = self._create_error_label()

        address_form.addRow(
            "Street Address *:", self._wrap_field(self.address_edit, self.address_error)
        )
        address_form.addRow("City *:", self._wrap_field(self.city_edit, self.city_error))
        address_form.addRow("State *:", self._wrap_field(self.state_edit, self.state_error))
        address_form.addRow("Country *:", self._wrap_field(self.country_edit, self.country_error))
        form_layout.addWidget(address_group)

        # --- Section 3: Financial Details ---
        finance_group = self._create_card("Initial Deposit (Optional)")
        finance_form = QFormLayout(finance_group)
        finance_form.setSpacing(12)
        finance_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.deposit_edit = QLineEdit()
        self.deposit_edit.setPlaceholderText("0.00")
        self.deposit_error = self._create_error_label()

        finance_form.addRow(
            "Opening Balance ($):", self._wrap_field(self.deposit_edit, self.deposit_error)
        )
        form_layout.addWidget(finance_group)

        # Action Buttons Card
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 8, 0, 0)
        action_layout.setSpacing(12)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #38bdf8; font-weight: bold;")
        action_layout.addWidget(self.status_label)
        action_layout.addStretch()

        self.clear_btn = QPushButton("Clear Form")
        self.clear_btn.setStyleSheet(
            "padding: 8px 16px; border-radius: 6px; background-color: #334155; color: #f8fafc;"
        )
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        action_layout.addWidget(self.clear_btn)

        self.submit_btn = QPushButton("Create Account")
        self.submit_btn.setEnabled(False)
        self.submit_btn.setStyleSheet(
            "padding: 8px 20px; border-radius: 6px; background-color: #2563eb; color: #ffffff; font-weight: bold;"
        )
        self.submit_btn.clicked.connect(self._on_submit_clicked)
        action_layout.addWidget(self.submit_btn)

        form_layout.addLayout(action_layout)
        form_layout.addStretch()

        scroll.setWidget(form_container)
        main_layout.addWidget(scroll)

    def _create_card(self, title: str) -> QFrame:
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
        # Widget -> ViewModel connections
        self.name_edit.textChanged.connect(self.vm.set_holder_name)
        self.phone_edit.textChanged.connect(self.vm.set_phone_number)
        self.address_edit.textChanged.connect(self.vm.set_address_line)
        self.city_edit.textChanged.connect(self.vm.set_city)
        self.state_edit.textChanged.connect(self.vm.set_state)
        self.country_edit.textChanged.connect(self.vm.set_country)
        self.deposit_edit.textChanged.connect(self.vm.set_initial_deposit)

        def _on_dob_changed(qdate: QDate) -> None:
            self.vm.set_dob(date(qdate.year(), qdate.month(), qdate.day()))

        self.dob_edit.dateChanged.connect(_on_dob_changed)

        # ViewModel -> Widget connections
        self.vm.validation_changed.connect(self._on_validation_changed)
        self.vm.submitting_changed.connect(self._on_submitting_changed)
        self.vm.account_created.connect(self._on_account_created)
        self.vm.submission_error.connect(self._on_submission_error)

    def _on_validation_changed(self, is_valid: bool, errors: dict[str, str]) -> None:
        self.submit_btn.setEnabled(is_valid)

        # Update error labels
        self._update_error_field(self.name_error, errors.get("holder_name"))
        self._update_error_field(self.dob_error, errors.get("dob"))
        self._update_error_field(self.phone_error, errors.get("phone_number"))
        self._update_error_field(self.address_error, errors.get("address_line"))
        self._update_error_field(self.city_error, errors.get("city"))
        self._update_error_field(self.state_error, errors.get("state"))
        self._update_error_field(self.country_error, errors.get("country"))
        self._update_error_field(self.deposit_error, errors.get("initial_deposit"))

    def _update_error_field(self, label: QLabel, msg: Optional[str]) -> None:
        if msg:
            label.setText(msg)
            label.setVisible(True)
        else:
            label.setText("")
            label.setVisible(False)

    def _on_submitting_changed(self, is_submitting: bool) -> None:
        self.submit_btn.setEnabled(not is_submitting and self.submit_btn.isEnabled())
        self.clear_btn.setEnabled(not is_submitting)
        self.name_edit.setEnabled(not is_submitting)
        self.phone_edit.setEnabled(not is_submitting)
        self.address_edit.setEnabled(not is_submitting)
        self.city_edit.setEnabled(not is_submitting)
        self.state_edit.setEnabled(not is_submitting)
        self.country_edit.setEnabled(not is_submitting)
        self.deposit_edit.setEnabled(not is_submitting)

        if is_submitting:
            self.status_label.setText("Creating customer account in database...")
        else:
            self.status_label.setText("")

    def _on_submit_clicked(self) -> None:
        if not self.banking_service or not self.task_runner:
            # Running standalone or in view-only mode
            return
        self.vm.submit(self.banking_service, self.task_runner)

    def _on_clear_clicked(self) -> None:
        self.name_edit.clear()
        self.phone_edit.clear()
        self.address_edit.clear()
        self.city_edit.clear()
        self.state_edit.clear()
        self.country_edit.setText("United States")
        self.deposit_edit.clear()
        default_dob = date.today().replace(year=date.today().year - 25)
        self.dob_edit.setDate(QDate(default_dob.year, default_dob.month, default_dob.day))
        self.vm.reset()

    def _on_account_created(self, result: OpenAccountResultDTO) -> None:
        acc = result.account
        formatted_num = (
            f"{acc.account_number[:4]}-{acc.account_number[4:8]}-{acc.account_number[8:]}"
        )
        msg = (
            f"Account created successfully!\n\n"
            f"Account Number: {formatted_num}\n"
            f"Holder Name: {acc.holder_name}\n"
            f"Initial Balance: ${acc.balance:,.2f} {acc.currency}\n"
            f"Phone: {acc.phone_number}\n\n"
            f"Would you like to print or save the account confirmation slip?"
        )
        QMessageBox.information(
            self,
            "Account Registration Complete",
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        self._on_clear_clicked()

    def _on_submission_error(self, error_message: str) -> None:
        QMessageBox.critical(
            self,
            "Account Registration Failed",
            f"An error occurred while creating the account:\n\n{error_message}",
        )
