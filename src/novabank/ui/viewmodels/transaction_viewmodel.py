"""ViewModel managing cash desk transactions (Deposit, Withdrawal, and Transfer) and live previews."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.transaction_dto import TransactionDTO, TransferResultDTO

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class TransactionViewModel(QObject):
    """ViewModel coordinating account verification, real-time balance previews, and atomic execution."""

    account_found = Signal(object)  # AccountDTO
    account_lookup_failed = Signal(str)
    destination_account_found = Signal(object)  # AccountDTO
    destination_account_failed = Signal(str)

    validation_changed = Signal(bool, dict)
    submitting_changed = Signal(bool)
    transaction_completed = Signal(object)  # TransactionDTO or TransferResultDTO
    transaction_failed = Signal(str)

    # Counter Limits
    MIN_TRANSACTION_AMOUNT = Decimal("1.00")
    MAX_DEPOSIT_LIMIT = Decimal("1000000.00")
    MAX_WITHDRAWAL_LIMIT = Decimal("50000.00")

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner

        # State
        self.source_account: Optional[AccountDTO] = None
        self.destination_account: Optional[AccountDTO] = None
        self.amount_str: str = ""
        self.description: str = ""
        self._is_submitting: bool = False

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        self.banking_service = banking_service
        self.task_runner = task_runner

    def lookup_source_account(self, account_number_raw: str) -> None:
        """Lookup source customer account asynchronously."""
        clean_num = account_number_raw.strip().replace("-", "").replace(" ", "")
        if len(clean_num) != 12:
            self.source_account = None
            return

        if not self.banking_service or not self.task_runner:
            return

        def _fetch():
            return self.banking_service.get_account(clean_num)

        def _on_success(dto: Optional[AccountDTO]):
            if dto:
                self.source_account = dto
                self.account_found.emit(dto)
            else:
                self.source_account = None
                self.account_lookup_failed.emit(f"Account {clean_num} does not exist.")
            self.validate_deposit()

        def _on_error(exc: Exception, tb: str):
            self.source_account = None
            self.account_lookup_failed.emit(str(exc))
            self.validate_deposit()

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def lookup_destination_account(self, account_number_raw: str) -> None:
        """Lookup destination customer account for transfers asynchronously."""
        clean_num = account_number_raw.strip().replace("-", "").replace(" ", "")
        if len(clean_num) != 12:
            self.destination_account = None
            return

        if not self.banking_service or not self.task_runner:
            return

        def _fetch():
            return self.banking_service.get_account(clean_num)

        def _on_success(dto: Optional[AccountDTO]):
            if dto:
                self.destination_account = dto
                self.destination_account_found.emit(dto)
            else:
                self.destination_account = None
                self.destination_account_failed.emit(
                    f"Destination account {clean_num} does not exist."
                )
            self.validate_transfer()

        def _on_error(exc: Exception, tb: str):
            self.destination_account = None
            self.destination_account_failed.emit(str(exc))
            self.validate_transfer()

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def set_amount(self, amount_str: str) -> None:
        self.amount_str = amount_str

    def set_description(self, desc: str) -> None:
        self.description = desc

    def parse_amount(self) -> Optional[Decimal]:
        """Attempt parsing amount_str to Decimal."""
        clean = self.amount_str.strip().replace("$", "").replace(",", "")
        if not clean:
            return None
        try:
            amt = Decimal(clean)
            return amt
        except InvalidOperation:
            return None

    def calculate_deposit_preview(self) -> tuple[Decimal, Decimal, Decimal]:
        """Return (current_balance, deposit_amount, projected_balance)."""
        current = self.source_account.balance if self.source_account else Decimal("0.00")
        deposit_amt = self.parse_amount() or Decimal("0.00")
        projected = current + deposit_amt if deposit_amt > 0 else current
        return current, deposit_amt, projected

    def calculate_withdrawal_preview(self) -> tuple[Decimal, Decimal, Decimal]:
        """Return (current_balance, withdrawal_amount, projected_balance)."""
        current = self.source_account.balance if self.source_account else Decimal("0.00")
        withdraw_amt = self.parse_amount() or Decimal("0.00")
        projected = current - withdraw_amt if withdraw_amt > 0 else current
        return current, withdraw_amt, projected

    def validate_deposit(self) -> tuple[bool, dict[str, str]]:
        """Validate inputs for cash deposit."""
        errors: dict[str, str] = {}

        if not self.source_account:
            errors["account"] = "Please enter and verify a valid 12-digit account number."
        elif not self.source_account.is_active:
            errors["account"] = "Account is inactive/closed. Deposits are prohibited."

        amt = self.parse_amount()
        if amt is None:
            if self.amount_str.strip():
                errors["amount"] = "Invalid numeric monetary amount."
            else:
                errors["amount"] = "Deposit amount is required."
        else:
            # Check 2 decimal places max
            if amt.as_tuple().exponent < -2:
                errors["amount"] = "Amount cannot exceed 2 decimal places."
            elif amt < self.MIN_TRANSACTION_AMOUNT:
                errors["amount"] = f"Minimum deposit amount is ${self.MIN_TRANSACTION_AMOUNT:,.2f}."
            elif amt > self.MAX_DEPOSIT_LIMIT:
                errors["amount"] = (
                    f"Counter deposit exceeds maximum limit of ${self.MAX_DEPOSIT_LIMIT:,.2f}."
                )

        is_valid = len(errors) == 0
        self.validation_changed.emit(is_valid, errors)
        return is_valid, errors

    def validate_withdrawal(self) -> tuple[bool, dict[str, str]]:
        """Validate inputs for cash withdrawal."""
        errors: dict[str, str] = {}

        if not self.source_account:
            errors["account"] = "Please enter and verify a valid 12-digit account number."
        elif not self.source_account.is_active:
            errors["account"] = "Account is inactive/closed. Withdrawals are prohibited."

        amt = self.parse_amount()
        if amt is None:
            if self.amount_str.strip():
                errors["amount"] = "Invalid numeric monetary amount."
            else:
                errors["amount"] = "Withdrawal amount is required."
        else:
            if amt.as_tuple().exponent < -2:
                errors["amount"] = "Amount cannot exceed 2 decimal places."
            elif amt < self.MIN_TRANSACTION_AMOUNT:
                errors["amount"] = (
                    f"Minimum withdrawal amount is ${self.MIN_TRANSACTION_AMOUNT:,.2f}."
                )
            elif amt > self.MAX_WITHDRAWAL_LIMIT:
                errors["amount"] = (
                    f"Counter withdrawal exceeds maximum limit of ${self.MAX_WITHDRAWAL_LIMIT:,.2f}."
                )
            elif self.source_account and amt > self.source_account.balance:
                errors["amount"] = (
                    f"Insufficient funds: Requested ${amt:,.2f} exceeds "
                    f"available balance of ${self.source_account.balance:,.2f}."
                )

        is_valid = len(errors) == 0
        self.validation_changed.emit(is_valid, errors)
        return is_valid, errors

    def validate_transfer(self) -> tuple[bool, dict[str, str]]:
        """Validate inputs for fund transfer between two accounts."""
        errors: dict[str, str] = {}

        if not self.source_account:
            errors["source_account"] = "Source account is required and must exist."
        elif not self.source_account.is_active:
            errors["source_account"] = "Source account is closed."

        if not self.destination_account:
            errors["destination_account"] = "Destination account is required and must exist."
        elif not self.destination_account.is_active:
            errors["destination_account"] = "Destination account is closed."

        if (
            self.source_account
            and self.destination_account
            and self.source_account.account_number == self.destination_account.account_number
        ):
            errors["destination_account"] = "Cannot transfer funds to the same account."

        amt = self.parse_amount()
        if amt is None:
            if self.amount_str.strip():
                errors["amount"] = "Invalid numeric monetary amount."
            else:
                errors["amount"] = "Transfer amount is required."
        else:
            if amt.as_tuple().exponent < -2:
                errors["amount"] = "Amount cannot exceed 2 decimal places."
            elif amt < self.MIN_TRANSACTION_AMOUNT:
                errors["amount"] = (
                    f"Minimum transfer amount is ${self.MIN_TRANSACTION_AMOUNT:,.2f}."
                )
            elif self.source_account and amt > self.source_account.balance:
                errors["amount"] = (
                    f"Insufficient funds: Requested ${amt:,.2f} exceeds "
                    f"available balance of ${self.source_account.balance:,.2f}."
                )

        is_valid = len(errors) == 0
        self.validation_changed.emit(is_valid, errors)
        return is_valid, errors

    def execute_deposit(self, actor: str = "teller") -> None:
        """Submit cash deposit transaction asynchronously."""
        is_valid, _ = self.validate_deposit()
        if (
            not is_valid
            or not self.source_account
            or not self.banking_service
            or not self.task_runner
        ):
            return

        self._is_submitting = True
        self.submitting_changed.emit(True)

        acc_num = self.source_account.account_number
        amt = self.parse_amount()
        desc = self.description.strip() or "Counter Cash Deposit"

        def _do_deposit():
            return self.banking_service.deposit(
                account_number=acc_num,
                amount=amt,
                description=desc,
                actor=actor,
            )

        def _on_success(dto: TransactionDTO):
            # Refresh source account
            self.lookup_source_account(acc_num)
            self.transaction_completed.emit(dto)

        def _on_error(exc: Exception, tb: str):
            self.transaction_failed.emit(str(exc))

        def _on_finished():
            self._is_submitting = False
            self.submitting_changed.emit(False)

        self.task_runner.run_async(
            _do_deposit,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def execute_withdrawal(self, actor: str = "teller") -> None:
        """Submit cash withdrawal transaction asynchronously."""
        is_valid, _ = self.validate_withdrawal()
        if (
            not is_valid
            or not self.source_account
            or not self.banking_service
            or not self.task_runner
        ):
            return

        self._is_submitting = True
        self.submitting_changed.emit(True)

        acc_num = self.source_account.account_number
        amt = self.parse_amount()
        desc = self.description.strip() or "Counter Cash Withdrawal"

        def _do_withdraw():
            return self.banking_service.withdraw(
                account_number=acc_num,
                amount=amt,
                description=desc,
                actor=actor,
            )

        def _on_success(dto: TransactionDTO):
            self.lookup_source_account(acc_num)
            self.transaction_completed.emit(dto)

        def _on_error(exc: Exception, tb: str):
            self.transaction_failed.emit(str(exc))

        def _on_finished():
            self._is_submitting = False
            self.submitting_changed.emit(False)

        self.task_runner.run_async(
            _do_withdraw,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )

    def execute_transfer(self, actor: str = "teller") -> None:
        """Submit account-to-account fund transfer asynchronously."""
        is_valid, _ = self.validate_transfer()
        if (
            not is_valid
            or not self.source_account
            or not self.destination_account
            or not self.banking_service
            or not self.task_runner
        ):
            return

        self._is_submitting = True
        self.submitting_changed.emit(True)

        src_num = self.source_account.account_number
        dst_num = self.destination_account.account_number
        amt = self.parse_amount()
        desc = self.description.strip() or f"Transfer from {src_num} to {dst_num}"

        def _do_transfer():
            return self.banking_service.transfer(
                source_account_number=src_num,
                destination_account_number=dst_num,
                amount=amt,
                description=desc,
                actor=actor,
            )

        def _on_success(dto: TransferResultDTO):
            self.lookup_source_account(src_num)
            self.lookup_destination_account(dst_num)
            self.transaction_completed.emit(dto)

        def _on_error(exc: Exception, tb: str):
            self.transaction_failed.emit(str(exc))

        def _on_finished():
            self._is_submitting = False
            self.submitting_changed.emit(False)

        self.task_runner.run_async(
            _do_transfer,
            on_result=_on_success,
            on_error=_on_error,
            on_finished=_on_finished,
        )
