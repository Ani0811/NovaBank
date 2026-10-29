"""ViewModel for customer profile inspection, contact details editing, and account lifecycle."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.account_dto import AccountDTO

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class AccountDetailViewModel(QObject):
    """ViewModel coordinating account detail loading, field editing, validation, and updates."""

    account_loaded = Signal(object)  # AccountDTO
    profile_updated = Signal(object)  # AccountDTO
    account_closed = Signal(object)  # AccountDTO
    loading_changed = Signal(bool)
    validation_changed = Signal(bool, dict)
    operation_error = Signal(str)

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner

        self.account: Optional[AccountDTO] = None
        self.account_number: str = ""
        self.holder_name: str = ""
        self.address_line: str = ""
        self.city: str = ""
        self.state: str = ""
        self.country: str = "United States"
        self.phone_number: str = ""
        self.is_loading: bool = False
        self._is_editing: bool = False

    def set_account(self, account: AccountDTO) -> None:
        """Populate ViewModel fields directly from an existing AccountDTO."""
        self.account = account
        self.account_number = account.account_number
        self.holder_name = account.holder_name
        self.address_line = account.address_line
        self.city = account.city
        self.state = account.state
        self.country = account.country
        self.phone_number = account.phone_number
        self.account_loaded.emit(account)
        self.validate()

    def set_address_line(self, val: str) -> None:
        self.address_line = val
        self.validate()

    def set_city(self, val: str) -> None:
        self.city = val
        self.validate()

    def set_state(self, val: str) -> None:
        self.state = val
        self.validate()

    def set_country(self, val: str) -> None:
        self.country = val
        self.validate()

    def set_phone_number(self, val: str) -> None:
        self.phone_number = val
        self.validate()

    def reset_edits(self) -> None:
        """Discard in-progress modifications and restore saved account values."""
        if self.account:
            self.set_account(self.account)

    def validate(self) -> tuple[bool, dict[str, str]]:
        """Validate mutable contact fields against domain constraints."""
        errors: dict[str, str] = {}

        # Phone validation (10 digits)
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

        # Address validation
        if not self.address_line.strip():
            errors["address_line"] = "Address line cannot be empty."
        elif len(self.address_line.strip()) > 255:
            errors["address_line"] = "Address line cannot exceed 255 characters."

        if not self.city.strip():
            errors["city"] = "City cannot be empty."
        elif len(self.city.strip()) > 100:
            errors["city"] = "City cannot exceed 100 characters."

        if not self.state.strip():
            errors["state"] = "State cannot be empty."
        elif len(self.state.strip()) > 100:
            errors["state"] = "State cannot exceed 100 characters."

        if not self.country.strip():
            errors["country"] = "Country cannot be empty."
        elif len(self.country.strip()) > 100:
            errors["country"] = "Country cannot exceed 100 characters."

        is_valid = len(errors) == 0
        self.validation_changed.emit(is_valid, errors)
        return is_valid, errors

    def load_account(self, account_number: str) -> None:
        """Fetch account from database asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        self.is_loading = True
        self.loading_changed.emit(True)

        def _fetch():
            return self.banking_service.get_account(account_number)

        def _on_success(dto: Optional[AccountDTO]):
            if dto:
                self.set_account(dto)
            else:
                self.operation_error.emit(f"Account {account_number} not found.")

        def _on_error(exc: Exception, tb: str):
            self.operation_error.emit(str(exc))

        def _on_finished():
            self.is_loading = False
            self.loading_changed.emit(False)

        self.task_runner.run_async(
            _fetch,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def save_profile(self, actor: str = "teller") -> None:
        """Save updated contact details asynchronously."""
        is_valid, _ = self.validate()
        if not is_valid or not self.account or not self.banking_service or not self.task_runner:
            return

        self.is_loading = True
        self.loading_changed.emit(True)

        clean_phone = (
            self.phone_number.strip()
            .replace("-", "")
            .replace(" ", "")
            .replace("(", "")
            .replace(")", "")
        )
        addr = self.address_line.strip()
        city = self.city.strip()
        state = self.state.strip()
        country = self.country.strip()
        acc_num = self.account.account_number

        def _update():
            return self.banking_service.update_account_profile(
                account_number=acc_num,
                address_line=addr,
                city=city,
                state=state,
                country=country,
                phone_number=clean_phone,
                actor=actor,
            )

        def _on_success(updated_dto: AccountDTO):
            self.account = updated_dto
            self.profile_updated.emit(updated_dto)

        def _on_error(exc: Exception, tb: str):
            self.operation_error.emit(str(exc))

        def _on_finished():
            self.is_loading = False
            self.loading_changed.emit(False)

        self.task_runner.run_async(
            _update,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def close_account(self, reason: str = "Customer request", actor: str = "teller") -> None:
        """Deactivate account if balance is exactly zero."""
        if not self.account or not self.banking_service or not self.task_runner:
            return

        self.is_loading = True
        self.loading_changed.emit(True)
        acc_num = self.account.account_number

        def _close():
            return self.banking_service.close_account(
                account_number=acc_num,
                reason=reason,
                actor=actor,
            )

        def _on_success(closed_dto: AccountDTO):
            self.account = closed_dto
            self.account_closed.emit(closed_dto)

        def _on_error(exc: Exception, tb: str):
            self.operation_error.emit(str(exc))

        def _on_finished():
            self.is_loading = False
            self.loading_changed.emit(False)

        self.task_runner.run_async(
            _close,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )
