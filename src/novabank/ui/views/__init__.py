"""UI Views for NovaBank presentation layer."""

from novabank.ui.views.account_close_dialog import AccountCloseDialog
from novabank.ui.views.account_detail_view import AccountDetailView
from novabank.ui.views.account_list_view import AccountListView
from novabank.ui.views.deposit_view import DepositView
from novabank.ui.views.open_account_view import OpenAccountView
from novabank.ui.views.withdrawal_view import WithdrawalView

__all__ = [
    "AccountCloseDialog",
    "AccountDetailView",
    "AccountListView",
    "DepositView",
    "OpenAccountView",
    "WithdrawalView",
]
