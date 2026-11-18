"""ViewModel coordinating Commercial Loan Origination, Amortization Simulation, and Portfolio Management."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.loan_dto import (
    LoanContractDTO,
    LoanOriginationRequestDTO,
    LoanQuoteResponseDTO,
    LoanRepaymentResultDTO,
)

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class LoanDeskViewModel(QObject):
    """Coordinates commercial credit facilities, amortization calculations, portfolio tracking, and loan servicing."""

    account_found = Signal(object)  # AccountDTO
    account_lookup_failed = Signal(str)

    quote_calculated = Signal(object)  # LoanQuoteResponseDTO
    quote_failed = Signal(str)

    submitting_changed = Signal(bool)
    loan_originated = Signal(object)  # LoanContractDTO
    loan_origination_failed = Signal(str)

    loans_loaded = Signal(list, int)  # (list[LoanContractDTO], total_count: int)
    loans_load_failed = Signal(str)

    repayment_completed = Signal(object)  # LoanRepaymentResultDTO
    repayment_failed = Signal(str)

    schedule_loaded = Signal(object)  # LoanContractDTO
    csv_exported = Signal(str)
    csv_export_failed = Signal(str)

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner

        # Local state
        self.target_account: Optional[AccountDTO] = None
        self.current_quote: Optional[LoanQuoteResponseDTO] = None
        self.current_loans: list[LoanContractDTO] = []
        self.selected_loan: Optional[LoanContractDTO] = None
        self._is_submitting: bool = False

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        self.banking_service = banking_service
        self.task_runner = task_runner

    def _safe_emit(self, sig: Signal, *args) -> None:
        try:
            sig.emit(*args)
        except RuntimeError:
            pass

    def lookup_account(self, account_number_raw: str) -> None:
        """Lookup borrower account asynchronously."""
        clean_num = account_number_raw.strip().replace("-", "").replace(" ", "")
        if len(clean_num) != 12:
            self.target_account = None
            return

        if not self.banking_service or not self.task_runner:
            return

        def _fetch():
            return self.banking_service.get_account(clean_num)

        def _on_success(account: Optional[AccountDTO]):
            if account:
                if not account.is_active:
                    self.target_account = None
                    self._safe_emit(self.account_lookup_failed, f"Account {clean_num} is deactivated/closed.")
                elif account.is_frozen:
                    self.target_account = None
                    self._safe_emit(self.account_lookup_failed, f"Account {clean_num} is under administrative freeze.")
                else:
                    self.target_account = account
                    self._safe_emit(self.account_found, account)
            else:
                self.target_account = None
                self._safe_emit(self.account_lookup_failed, f"Account {clean_num} not found.")

        def _on_error(exc: Exception, tb: str):
            self.target_account = None
            self._safe_emit(self.account_lookup_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def calculate_quote(self, principal_str: str, apr_str: str, term_months: int) -> None:
        """Calculate quote EMI and totals."""
        if not self.banking_service:
            return

        try:
            clean_principal = principal_str.strip().replace("$", "").replace(",", "")
            clean_apr = apr_str.strip().replace("%", "")
            principal = Decimal(clean_principal)
            apr = Decimal(clean_apr)
            if principal <= Decimal("0.00") or apr <= Decimal("0.00") or term_months <= 0:
                self.current_quote = None
                self._safe_emit(self.quote_failed, "All loan parameters must be strictly positive.")
                return
        except (InvalidOperation, ValueError, TypeError) as exc:
            self.current_quote = None
            self._safe_emit(self.quote_failed, f"Invalid numeric input: {exc}")
            return

        try:
            quote = self.banking_service.calculate_loan_quote(
                principal=principal,
                apr_percentage=apr,
                term_months=term_months,
            )
            self.current_quote = quote
            self._safe_emit(self.quote_calculated, quote)
        except Exception as exc:
            self.current_quote = None
            self._safe_emit(self.quote_failed, str(exc))

    def originate_loan(
        self,
        account_number: str,
        loan_type: str,
        principal: Decimal,
        apr: Decimal,
        term_months: int,
        purpose: str,
        actor: str = "lending_officer",
    ) -> None:
        """Originate and disburse commercial credit facility asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        if self._is_submitting:
            return

        self._is_submitting = True
        self._safe_emit(self.submitting_changed, True)

        request = LoanOriginationRequestDTO(
            account_number=account_number,
            loan_type=loan_type,
            principal=principal,
            apr_percentage=apr,
            term_months=term_months,
            purpose=purpose,
        )

        def _execute():
            return self.banking_service.originate_loan(request, actor=actor)

        def _on_success(loan_dto: LoanContractDTO):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.loan_originated, loan_dto)

        def _on_error(exc: Exception, tb: str):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.loan_origination_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)

    def load_loans(
        self,
        account_number: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> None:
        """Load portfolio loans asynchronously with optional filters."""
        if not self.banking_service or not self.task_runner:
            return

        clean_acc = account_number.strip().replace("-", "").replace(" ", "") if account_number else None
        filter_status = status.strip().upper() if status and status.strip().upper() != "ALL" else None

        def _fetch():
            return self.banking_service.list_loans(
                account_number=clean_acc,
                status=filter_status,
                page=page,
                page_size=page_size,
            )

        def _on_success(result: tuple[list[LoanContractDTO], int]):
            loans, total = result
            self.current_loans = loans
            self._safe_emit(self.loans_loaded, loans, total)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.loans_load_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def repay_installment(
        self,
        loan_id: str,
        amount: Optional[Decimal] = None,
        actor: str = "teller",
    ) -> None:
        """Process scheduled installment repayment asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        if self._is_submitting:
            return

        self._is_submitting = True
        self._safe_emit(self.submitting_changed, True)

        def _execute():
            return self.banking_service.repay_loan_installment(loan_id, amount=amount, actor=actor)

        def _on_success(result: LoanRepaymentResultDTO):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.repayment_completed, result)

        def _on_error(exc: Exception, tb: str):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.repayment_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)

    def load_loan_schedule(self, loan_id: str) -> None:
        """Fetch full loan schedule for explorer tab."""
        if not self.banking_service or not self.task_runner:
            return

        def _fetch():
            return self.banking_service.get_loan(loan_id)

        def _on_success(loan: Optional[LoanContractDTO]):
            if loan:
                self.selected_loan = loan
                self._safe_emit(self.schedule_loaded, loan)
            else:
                self._safe_emit(self.loans_load_failed, f"Loan '{loan_id}' not found.")

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.loans_load_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def export_schedule_csv(self, loan_id: str, destination_path: Optional[str] = None) -> None:
        """Export loan schedule to CSV file."""
        if not self.banking_service or not self.task_runner:
            return

        def _execute():
            return self.banking_service.export_loan_schedule_csv(loan_id, destination=destination_path)

        def _on_success(csv_content: str):
            self._safe_emit(self.csv_exported, csv_content)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.csv_export_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)
