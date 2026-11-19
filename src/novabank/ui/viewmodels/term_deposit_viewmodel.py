"""ViewModel coordinating Term Deposit & CD Vault issuance, yield calculations, portfolio tracking, and redemptions."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.term_deposit_dto import (
    CDSimulationResponseDTO,
    CertificateOfDepositDTO,
    EarlyRedemptionPreviewDTO,
    OpenCDRequestDTO,
    RedemptionResultDTO,
)

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class TermDepositViewModel(QObject):
    """Coordinates Certificate of Deposit issuance, compounding simulations, and portfolio redemptions."""

    account_found = Signal(object)  # AccountDTO
    account_lookup_failed = Signal(str)

    quote_calculated = Signal(object)  # CDSimulationResponseDTO
    quote_failed = Signal(str)

    submitting_changed = Signal(bool)
    cd_opened = Signal(object)  # CertificateOfDepositDTO
    cd_open_failed = Signal(str)

    cds_loaded = Signal(list, int)  # (list[CertificateOfDepositDTO], total_count: int)
    cds_load_failed = Signal(str)

    redemption_preview_ready = Signal(object)  # EarlyRedemptionPreviewDTO
    redemption_completed = Signal(object)  # RedemptionResultDTO
    redemption_failed = Signal(str)

    certificate_loaded = Signal(object)  # CertificateOfDepositDTO
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
        self.current_quote: Optional[CDSimulationResponseDTO] = None
        self.current_cds: list[CertificateOfDepositDTO] = []
        self.selected_cd: Optional[CertificateOfDepositDTO] = None
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
        """Lookup funding account asynchronously."""
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

    def calculate_quote(
        self,
        principal_str: str,
        apy_str: str,
        tenor_months: int,
        payout_frequency: str = "AT_MATURITY",
    ) -> None:
        """Calculate guaranteed maturity return and projected interest."""
        if not self.banking_service:
            return

        try:
            clean_p = principal_str.strip().replace("$", "").replace(",", "")
            clean_apy = apy_str.strip().replace("%", "")
            principal = Decimal(clean_p)
            apy = Decimal(clean_apy)
            if principal < Decimal("500.00") or apy <= Decimal("0.00") or tenor_months <= 0:
                self.current_quote = None
                self._safe_emit(self.quote_failed, "Minimum principal is $500.00 with positive APY and tenor.")
                return
        except (InvalidOperation, ValueError, TypeError) as exc:
            self.current_quote = None
            self._safe_emit(self.quote_failed, f"Invalid numeric parameter: {exc}")
            return

        try:
            quote = self.banking_service.simulate_term_deposit(
                principal=principal,
                tenor_months=tenor_months,
                apy_percentage=apy,
                payout_frequency=payout_frequency,
            )
            self.current_quote = quote
            self._safe_emit(self.quote_calculated, quote)
        except Exception as exc:
            self.current_quote = None
            self._safe_emit(self.quote_failed, str(exc))

    def open_cd(
        self,
        account_number: str,
        principal: Decimal,
        apy: Decimal,
        tenor_months: int,
        payout_frequency: str = "AT_MATURITY",
        rollover_option: str = "PAYOUT_AND_CLOSE",
        actor: str = "teller",
    ) -> None:
        """Lock funds and issue Certificate of Deposit asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        if self._is_submitting:
            return

        self._is_submitting = True
        self._safe_emit(self.submitting_changed, True)

        request = OpenCDRequestDTO(
            account_number=account_number,
            principal=principal,
            apy_percentage=apy,
            tenor_months=tenor_months,
            payout_frequency=payout_frequency,
            rollover_option=rollover_option,
        )

        def _execute():
            return self.banking_service.open_term_deposit(request, actor=actor)

        def _on_success(cd_dto: CertificateOfDepositDTO):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.cd_opened, cd_dto)

        def _on_error(exc: Exception, tb: str):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.cd_open_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)

    def load_cds(
        self,
        account_number: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> None:
        """Load portfolio Certificates of Deposit asynchronously with optional filters."""
        if not self.banking_service or not self.task_runner:
            return

        clean_acc = account_number.strip().replace("-", "").replace(" ", "") if account_number else None
        filter_status = (
            status.strip().upper()
            if status and status.strip().upper() not in ("ALL", "ALL STATUSES")
            else None
        )

        def _fetch():
            return self.banking_service.list_term_deposits(
                account_number=clean_acc,
                status=filter_status,
                page=page,
                page_size=page_size,
            )

        def _on_success(result: tuple[list[CertificateOfDepositDTO], int]):
            cds, total = result
            self.current_cds = cds
            self._safe_emit(self.cds_loaded, cds, total)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.cds_load_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def preview_early_redemption(self, cd_id: str) -> None:
        """Preview early liquidation penalty asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        def _execute():
            return self.banking_service.preview_early_redemption(cd_id)

        def _on_success(preview: EarlyRedemptionPreviewDTO):
            self._safe_emit(self.redemption_preview_ready, preview)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.redemption_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)

    def redeem_cd(
        self,
        cd_id: str,
        is_premature: bool = False,
        actor: str = "teller",
    ) -> None:
        """Process CD maturity or early liquidation redemption asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        if self._is_submitting:
            return

        self._is_submitting = True
        self._safe_emit(self.submitting_changed, True)

        def _execute():
            return self.banking_service.redeem_term_deposit(cd_id, is_premature=is_premature, actor=actor)

        def _on_success(result: RedemptionResultDTO):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.redemption_completed, result)

        def _on_error(exc: Exception, tb: str):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.redemption_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)

    def load_certificate(self, cd_id: str) -> None:
        """Fetch full Certificate details and accruals for inspection tab."""
        if not self.banking_service or not self.task_runner:
            return

        def _fetch():
            return self.banking_service.get_term_deposit(cd_id)

        def _on_success(cd: Optional[CertificateOfDepositDTO]):
            if cd:
                self.selected_cd = cd
                self._safe_emit(self.certificate_loaded, cd)
            else:
                self._safe_emit(self.cds_load_failed, f"Certificate '{cd_id}' not found.")

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.cds_load_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def export_cds_csv(self, destination_path: Optional[str] = None) -> None:
        """Export current list of Certificates of Deposit to CSV."""
        if not self.banking_service or not self.task_runner:
            return

        cds_to_export = self.current_cds

        def _execute():
            return self.banking_service.export_term_deposits_csv(
                cds=cds_to_export, destination=destination_path
            )

        def _on_success(csv_content: str):
            self._safe_emit(self.csv_exported, csv_content)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.csv_export_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)
