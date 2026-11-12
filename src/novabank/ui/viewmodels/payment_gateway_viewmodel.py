"""ViewModel coordinating Payment Gateway Virtual Terminal, fee calculation, settlements, and refund operations."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional, Sequence

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.payment_dto import (
    PaymentRefundResultDTO,
    PaymentRequestDTO,
    PaymentTransactionDTO,
)
from novabank.domain.entities.payment import PaymentChannel
from novabank.domain.value_objects.money import Money
from novabank.infrastructure.gateways.payment_rails_simulator import PaymentRailsSimulator

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class PaymentGatewayViewModel(QObject):
    """Coordinates gateway clearance, live interchange fee calculations, ledger settlements, and refunds."""

    account_found = Signal(object)  # AccountDTO
    account_lookup_failed = Signal(str)

    fee_calculated = Signal(object, object, object)  # (gross: Decimal, fee: Decimal, net: Decimal)
    card_brand_detected = Signal(str)  # "VISA", "MASTERCARD", "AMEX", "DISCOVER", or ""

    submitting_changed = Signal(bool)
    payment_completed = Signal(object)  # PaymentTransactionDTO
    payment_failed = Signal(str)

    refund_completed = Signal(object)  # PaymentRefundResultDTO
    refund_failed = Signal(str)

    payments_loaded = Signal(list, int)  # (list[PaymentTransactionDTO], total_count: int)
    payments_load_failed = Signal(str)

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

        # State
        self.target_account: Optional[AccountDTO] = None
        self.channel: str = "CARD"
        self.amount_str: str = ""
        self.merchant_name: str = "NovaBank Merchant Operations"
        self.customer_name: str = ""
        self.card_number: str = ""
        self.card_exp: str = ""
        self.card_cvv: str = ""
        self.card_zip: str = ""
        self.routing_number: str = ""
        self.description: str = ""
        self._is_submitting: bool = False
        self.current_payments: list[PaymentTransactionDTO] = []

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        self.banking_service = banking_service
        self.task_runner = task_runner

    def _safe_emit(self, sig: Signal, *args) -> None:
        try:
            sig.emit(*args)
        except RuntimeError:
            pass

    def lookup_account(self, account_number_raw: str) -> None:
        """Lookup destination merchant account asynchronously."""
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
                    self._safe_emit(self.account_lookup_failed, f"Account {clean_num} is under risk freeze.")
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

    def set_channel(self, channel: str) -> None:
        self.channel = channel.strip().upper()
        self.update_fee_preview()

    def set_amount(self, amount_str: str) -> None:
        self.amount_str = amount_str.strip().replace("$", "").replace(",", "")
        self.update_fee_preview()

    def set_card_number(self, card_number_raw: str) -> None:
        self.card_number = card_number_raw
        digits = re.sub(r"\D", "", card_number_raw)
        brand = PaymentRailsSimulator.detect_card_brand(digits)
        self._safe_emit(self.card_brand_detected, brand)

    def update_fee_preview(self) -> None:
        """Calculate real-time gross, interchange fee, and net settlement."""
        try:
            amt = Decimal(self.amount_str)
            if amt <= Decimal("0.00"):
                self._safe_emit(self.fee_calculated, Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))
                return
        except (InvalidOperation, ValueError, TypeError):
            self._safe_emit(self.fee_calculated, Decimal("0.00"), Decimal("0.00"), Decimal("0.00"))
            return

        try:
            channel_enum = PaymentChannel(self.channel)
        except ValueError:
            channel_enum = PaymentChannel.CARD

        gross_money = Money(amt)
        fee_money = PaymentRailsSimulator.calculate_interchange_fee(channel_enum, gross_money)
        net_money = gross_money - fee_money

        self._safe_emit(self.fee_calculated, gross_money.amount, fee_money.amount, net_money.amount)

    def submit_payment(
        self,
        account_number: str,
        channel: str,
        amount: Decimal,
        merchant_name: str,
        customer_name: str,
        description: str = "",
        card_number: Optional[str] = None,
        card_exp: Optional[str] = None,
        card_cvv: Optional[str] = None,
        card_zip: Optional[str] = None,
        routing_number: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> None:
        """Submit a payment request asynchronously through the gateway."""
        if not self.banking_service or not self.task_runner:
            return

        if self._is_submitting:
            return

        self._is_submitting = True
        self._safe_emit(self.submitting_changed, True)

        req = PaymentRequestDTO(
            account_number=account_number,
            channel=channel,
            amount=amount,
            merchant_name=merchant_name or "NovaBank Merchant Operations",
            customer_name=customer_name or "Valued Customer",
            description=description,
            card_number=card_number,
            card_exp=card_exp,
            card_cvv=card_cvv,
            card_zip=card_zip,
            routing_number=routing_number,
            idempotency_key=idempotency_key,
        )

        def _execute():
            return self.banking_service.process_gateway_payment(req, actor="teller_pos")

        def _on_success(dto: PaymentTransactionDTO):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.payment_completed, dto)

        def _on_error(exc: Exception, tb: str):
            self._is_submitting = False
            self._safe_emit(self.submitting_changed, False)
            self._safe_emit(self.payment_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)

    def issue_refund(self, payment_id: str, reason: str) -> None:
        """Issue full payment reversal & refund asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        def _execute():
            return self.banking_service.refund_gateway_payment(
                payment_id=payment_id,
                reason=reason,
                actor="teller_supervisor",
            )

        def _on_success(dto: PaymentRefundResultDTO):
            self._safe_emit(self.refund_completed, dto)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.refund_failed, str(exc))

        self.task_runner.run_async(_execute, on_result=_on_success, on_error=_on_error)

    def load_payments(
        self,
        account_number: Optional[str] = None,
        channel: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> None:
        """Load paginated gateway payments asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        def _fetch():
            return self.banking_service.list_gateway_payments(
                account_number=account_number if account_number else None,
                channel=channel if channel and channel != "ALL" else None,
                status=status if status and status != "ALL" else None,
                page=page,
                page_size=page_size,
            )

        def _on_success(result: tuple[list[PaymentTransactionDTO], int]):
            payments, total = result
            self.current_payments = payments
            self._safe_emit(self.payments_loaded, payments, total)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.payments_load_failed, str(exc))

        self.task_runner.run_async(_fetch, on_result=_on_success, on_error=_on_error)

    def export_csv(
        self,
        file_path: str,
        payments: Optional[Sequence[PaymentTransactionDTO]] = None,
    ) -> None:
        """Export gateway payment records directly to CSV file asynchronously."""
        if not self.banking_service or not self.task_runner:
            return

        data_to_export = payments if payments is not None else self.current_payments

        def _export():
            self.banking_service.export_payments_csv(
                payments=data_to_export,
                destination=file_path,
            )
            return file_path

        def _on_success(saved_path: str):
            self._safe_emit(self.csv_exported, saved_path)

        def _on_error(exc: Exception, tb: str):
            self._safe_emit(self.csv_export_failed, str(exc))

        self.task_runner.run_async(_export, on_result=_on_success, on_error=_on_error)
