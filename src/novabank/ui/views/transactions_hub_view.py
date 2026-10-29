"""Transactions Hub view coordinating Deposit, Withdrawal, and Fund Transfer desks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtWidgets import (
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

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
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet(
            "QTabWidget::pane { border: 1px solid #334155; background-color: #0f172a; border-radius: 8px; }"
            "QTabBar::tab { background-color: #1e293b; color: #94a3b8; font-weight: bold; font-size: 13px; "
            "padding: 10px 24px; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 4px; border: 1px solid #334155; border-bottom: none; }"
            "QTabBar::tab:selected { background-color: #0f172a; color: #38bdf8; border-bottom: 2px solid #0284c7; }"
            "QTabBar::tab:hover:!selected { background-color: #334155; color: #f8fafc; }"
        )

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

        self.tab_widget.addTab(self.deposit_view, "Cash Deposit")
        self.tab_widget.addTab(self.withdrawal_view, "Cash Withdrawal")
        self.tab_widget.addTab(self.transfer_view, "Fund Transfer")

        layout.addWidget(self.tab_widget)

