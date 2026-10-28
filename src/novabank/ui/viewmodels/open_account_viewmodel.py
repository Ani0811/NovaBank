"""ViewModel for customer account opening workflow and real-time form validation."""

from __future__ import annotations

import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.account_dto import OpenAccountResultDTO

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class OpenAccountViewModel(QObject):
    """Encapsulates state and validation for the Open Account form."""

    validation_changed = Signal(bool, dict)
    submitting_changed = Signal(bool)
    account_created = Signal(object)
    submission_error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.holder_name: str = ""
        # Default DOB to 25 years ago
        self.dob: date = date.today() - timedelta(days=25 * 365 + 6)
        self.address_line: str = ""
        self.city: str = ""
        self.state: str = ""
        self.country: str = "United States"
        self.phone_number: str = ""
        self.initial_deposit_str: str = ""
        self._is_submitting: bool = False

    def set_holder_name(self, value: str) -> None:
        self.holder_name = value
        self.validate()

    def set_dob(self, value: date) -> None:
        self.dob = value
        self.validate()

    def set_address_line(self, value: str) -> None:
        self.address_line = value
        self.validate()

    def set_city(self, value: str) -> None:
        self.city = value
        self.validate()

    def set_state(self, value: str) -> None:
        self.state = value
        self.validate()

    def set_country(self, value: str) -> None:
        self.country = value
        self.validate()

    def set_phone_number(self, value: str) -> None:
        self.phone_number = value
        self.validate()

    def set_initial_deposit(self, value: str) -> None:
        self.initial_deposit_str = value
        self.validate()

    def reset(self) -> None:
        """Reset form fields to initial state."""
        self.holder_name = ""
        self.dob = date.today() - timedelta(days=25 * 365 + 6)
        self.address_line = ""
        self.city = ""
        self.state = ""
        self.country = "United States"
        self.phone_number = ""
        self.initial_deposit_str = ""
        self.validate()

    def validate(self) -> tuple[bool, dict[str, str]]:
        """Validate all form inputs against business and domain invariants.

        Returns:
            Tuple of (is_all_valid, dict_of_field_errors)
        """
        errors: dict[str, str] = {}

        # 1. Holder name validation
        name = self.holder_name.strip()
        if not name:
            errors["holder_name"] = "Full name is required."
        elif len(name) < 2:
            errors["holder_name"] = "Full name must be at least 2 characters."
        elif len(name) > 100:
            errors["holder_name"] = "Full name cannot exceed 100 characters."

        # 2. DOB validation
        today = date.today()
        if self.dob > today:
            errors["dob"] = "Date of birth cannot be in the future."
        else:
            age = (
                today.year
                - self.dob.year
                - ((today.month, today.day) < (self.dob.month, self.dob.day))
            )
            if age < 18:
                errors["dob"] = f"Customer must be at least 18 years old (current age: {age})."
            elif age > 120:
                errors["dob"] = f"Age cannot exceed 120 years (current age: {age})."

        # 3. Phone number validation (10 digits)
        clean_phone = (
            self.phone_number.strip()
            .replace("-", "")
            .replace(" ", "")
            .replace("(", "")
            .replace(")", "")
        )
        if not clean_phone:
            errors["phone_number"] = "Phone number is required."
        elif not re.fullmatch(r"\d{10}", clean_phone):
            errors["phone_number"] = "Phone number must consist of exactly 10 digits."

        # 4. Address validation
        if not self.address_line.strip():
            errors["address_line"] = "Address line is required."
        elif len(self.address_line.strip()) > 255:
            errors["address_line"] = "Address line cannot exceed 255 characters."

        if not self.city.strip():
            errors["city"] = "City is required."
        elif len(self.city.strip()) > 100:
            errors["city"] = "City cannot exceed 100 characters."

        if not self.state.strip():
            errors["state"] = "State is required."
        elif len(self.state.strip()) > 100:
            errors["state"] = "State cannot exceed 100 characters."

        if not self.country.strip():
            errors["country"] = "Country is required."
        elif len(self.country.strip()) > 100:
            errors["country"] = "Country cannot exceed 100 characters."

        # 5. Initial deposit validation (optional, but if present must be >= 0)
        dep_str = self.initial_deposit_str.strip()
        if dep_str:
            try:
                dep_amount = Decimal(dep_str)
                if dep_amount < Decimal("0.00"):
                    errors["initial_deposit"] = "Initial deposit cannot be negative."
            except InvalidOperation:
                errors["initial_deposit"] = "Invalid numeric monetary amount."

        is_valid = len(errors) == 0
        self.validation_changed.emit(is_valid, errors)
        return is_valid, errors

    def submit(
        self,
        banking_service: BankingService,
        task_runner: TaskRunner,
        actor: str = "teller",
    ) -> None:
        """Submit the form asynchronously on the thread pool."""
        is_valid, _ = self.validate()
        if not is_valid or self._is_submitting:
            return

        self._is_submitting = True
        self.submitting_changed.emit(True)

        dep_str = self.initial_deposit_str.strip()
        initial_deposit = Decimal(dep_str) if dep_str else None
        clean_phone = (
            self.phone_number.strip()
            .replace("-", "")
            .replace(" ", "")
            .replace("(", "")
            .replace(")", "")
        )

        def _do_open():
            return banking_service.open_account(
                holder_name=self.holder_name.strip(),
                dob=self.dob,
                address_line=self.address_line.strip(),
                city=self.city.strip(),
                state=self.state.strip(),
                country=self.country.strip(),
                phone_number=clean_phone,
                initial_deposit=initial_deposit,
                currency="USD",
                actor=actor,
            )

        def _on_success(result: OpenAccountResultDTO):
            self.account_created.emit(result)

        def _on_error(exc: Exception, tb: str):
            self.submission_error.emit(str(exc))

        def _on_finished():
            self._is_submitting = False
            self.submitting_changed.emit(False)

        task_runner.run_async(
            _do_open,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )
