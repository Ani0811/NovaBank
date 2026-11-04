"""Transactions Hub view coordinating Deposit, Withdrawal, and Fund Transfer desks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtWidgets import (
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from novabank.ui.resources.icons import get_icon
from novabank.ui.views.deposit_view import DepositView
from novabank.ui.views.transfer_view import TransferView
from novabank.ui.views.withdrawal_view import WithdrawalView

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class TransactionsHubView(QWidget):
    """Central cash desk terminal hosting Deposit, Withdrawal, and Transfer views."""

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(14)

        self.tab_widget = QTabWidget(self)

        self.deposit_view = DepositView(
            banking_service=self.banking_service,
            task_runner=self.task_runner,
            parent=self.tab_widget,
        )
        self.withdrawal_view = WithdrawalView(
            banking_service=self.banking_service,
            task_runner=self.task_runner,
            parent=self.tab_widget,
        )
        self.transfer_view = TransferView(
            banking_service=self.banking_service,
            task_runner=self.task_runner,
            parent=self.tab_widget,
        )

        self.tab_widget.addTab(self.deposit_view, get_icon("deposits", color="#2563EB", size=16), "Cash Deposit")
        self.tab_widget.addTab(self.withdrawal_view, get_icon("withdrawals", color="#2563EB", size=16), "Cash Withdrawal")
        self.tab_widget.addTab(self.transfer_view, get_icon("transfers", color="#2563EB", size=16), "Fund Transfer")

        layout.addWidget(self.tab_widget)
