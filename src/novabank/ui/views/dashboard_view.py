"""Institutional Financial Dashboard View for NovaBank operations."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.account_dto import AccountDTO
from novabank.ui.resources.icons import get_icon

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class DashboardView(QWidget):
    """Central enterprise banking dashboard presenting real-time liquidity, KPIs, and operational workflows."""

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        navigate_callback: Optional[Callable[[str], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.navigate_callback = navigate_callback

        self._accounts_cache: list[AccountDTO] = []

        self._setup_ui()
        self.load_data()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # Scrollable canvas
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 24, 28, 28)
        layout.setSpacing(24)

        # ---------------------------------------------------------------------
        # 1. Page Header Strip
        # ---------------------------------------------------------------------
        header_row = QHBoxLayout()
        header_row.setSpacing(16)

        title_block = QVBoxLayout()
        title_block.setSpacing(3)
        self.view_title = QLabel("Operational Overview")
        self.view_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033; letter-spacing: -0.2px;")

        self.view_subtitle = QLabel("Real-time summary of accounts, settlement volume, and liquidity.")
        self.view_subtitle.setStyleSheet("font-size: 13px; color: #64748B;")

        title_block.addWidget(self.view_title)
        title_block.addWidget(self.view_subtitle)
        header_row.addLayout(title_block, stretch=1)

        # Environment status pill & refresh
        status_box = QHBoxLayout()
        status_box.setSpacing(10)

        self.pill_system = QLabel("Live Core Ledger")
        self.pill_system.setProperty("class", "StatusIndicatorPill")
        self.pill_system.setProperty("status", "success")

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setProperty("class", "SecondaryButton")
        self.refresh_btn.setIcon(get_icon("refresh", color="#172033", size=14))
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.load_data)

        status_box.addWidget(self.pill_system)
        status_box.addWidget(self.refresh_btn)
        header_row.addLayout(status_box)

        layout.addLayout(header_row)

        # ---------------------------------------------------------------------
        # 2. Financial Overview KPIs (4 Core Institutional Metrics)
        # ---------------------------------------------------------------------
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(16)

        # Card 1: Total Deposits / Assets
        self.card_aum, self.val_aum, self.sub_aum = self._create_kpi_card(
            title="TOTAL DEPOSITS / ASSETS",
            initial_value="$0.00",
            initial_sub="Aggregated customer balances",
            icon_name="dollar_sign",
        )
        kpi_grid.addWidget(self.card_aum, 0, 0)

        # Card 2: Active Accounts
        self.card_acc, self.val_acc, self.sub_acc = self._create_kpi_card(
            title="ACTIVE ACCOUNTS",
            initial_value="0 Active",
            initial_sub="0 total customer accounts",
            icon_name="accounts",
        )
        kpi_grid.addWidget(self.card_acc, 0, 1)

        # Card 3: Total Transactions
        self.card_vol, self.val_vol, self.sub_vol = self._create_kpi_card(
            title="TOTAL TRANSACTIONS",
            initial_value="0 Settled",
            initial_sub="Atomic ledger operations",
            icon_name="transactions",
        )
        kpi_grid.addWidget(self.card_vol, 0, 2)

        # Card 4: Pending Transactions
        self.card_sec, self.val_sec, self.sub_sec = self._create_kpi_card(
            title="PENDING TRANSACTIONS",
            initial_value="0 Pending",
            initial_sub="100% real-time settlement",
            icon_name="clock",
        )
        kpi_grid.addWidget(self.card_sec, 0, 3)

        layout.addLayout(kpi_grid)

        # ---------------------------------------------------------------------
        # 3. Quick Actions
        # ---------------------------------------------------------------------
        quick_actions_card = QFrame()
        quick_actions_card.setProperty("class", "CardFrame")
        qa_layout = QVBoxLayout(quick_actions_card)
        qa_layout.setContentsMargins(18, 16, 18, 16)
        qa_layout.setSpacing(12)

        qa_header = QHBoxLayout()
        qa_title = QLabel("TELLER QUICK ACTIONS")
        qa_title.setProperty("class", "CardTitle")
        qa_header.addWidget(qa_title)
        qa_header.addStretch()
        qa_layout.addLayout(qa_header)

        actions_grid = QGridLayout()
        actions_grid.setSpacing(10)

        actions = [
            ("open_account", "Open Account", "Register new customer profile", "open_account"),
            ("deposits", "Cash Deposit", "Process customer currency deposit", "deposits"),
            ("withdrawals", "Cash Withdrawal", "Verify funds and dispense cash", "withdrawals"),
            ("transfers", "Fund Transfer", "Execute dual-ledger balance transfer", "transfers"),
            ("statements", "Generate Statement", "Export official account statement", "statements"),
            ("ai_assistant", "AI Assistant", "Query portfolio data and flags", "ai_assistant"),
        ]

        for i, (icon_name, title, desc, route) in enumerate(actions):
            btn = self._create_action_card(icon_name, title, desc, route)
            actions_grid.addWidget(btn, i // 3, i % 3)

        qa_layout.addLayout(actions_grid)
        layout.addWidget(quick_actions_card)

        # ---------------------------------------------------------------------
        # 4. Financial Analytics (Activity Breakdown & Balance Distribution)
        # ---------------------------------------------------------------------
        analytics_layout = QHBoxLayout()
        analytics_layout.setSpacing(16)

        # Left Analytics: Operational Activity Volume
        activity_card = QFrame()
        activity_card.setProperty("class", "CardFrame")
        act_layout = QVBoxLayout(activity_card)
        act_layout.setSpacing(14)

        act_title = QLabel("TRANSACTION ACTIVITY BREAKDOWN")
        act_title.setProperty("class", "CardTitle")
        act_layout.addWidget(act_title)

        # Deposit bar
        self.dep_bar_row, self.dep_lbl, self.dep_bar = self._create_analytics_row("Deposits Volume")
        act_layout.addLayout(self.dep_bar_row)

        # Withdrawal bar
        self.wdr_bar_row, self.wdr_lbl, self.wdr_bar = self._create_analytics_row("Withdrawals Volume")
        act_layout.addLayout(self.wdr_bar_row)

        # Transfer bar
        self.trf_bar_row, self.trf_lbl, self.trf_bar = self._create_analytics_row("Transfers Volume")
        act_layout.addLayout(self.trf_bar_row)

        act_layout.addStretch()
        analytics_layout.addWidget(activity_card, stretch=50)

        # Right Analytics: Account Balance Distribution
        dist_card = QFrame()
        dist_card.setProperty("class", "CardFrame")
        dist_layout = QVBoxLayout(dist_card)
        dist_layout.setSpacing(14)

        dist_title = QLabel("ACCOUNT BALANCE DISTRIBUTION")
        dist_title.setProperty("class", "CardTitle")
        dist_layout.addWidget(dist_title)

        self.tier1_row, self.tier1_lbl, self.tier1_bar = self._create_analytics_row("Under $1,000")
        dist_layout.addLayout(self.tier1_row)

        self.tier2_row, self.tier2_lbl, self.tier2_bar = self._create_analytics_row("$1,000 to $10,000")
        dist_layout.addLayout(self.tier2_row)

        self.tier3_row, self.tier3_lbl, self.tier3_bar = self._create_analytics_row("$10,000 to $50,000")
        dist_layout.addLayout(self.tier3_row)

        self.tier4_row, self.tier4_lbl, self.tier4_bar = self._create_analytics_row("Over $50,000")
        dist_layout.addLayout(self.tier4_row)

        dist_layout.addStretch()
        analytics_layout.addWidget(dist_card, stretch=50)

        layout.addLayout(analytics_layout)

        # ---------------------------------------------------------------------
        # 5. Live Tables Grid: Recent Transactions & Account Overview
        # ---------------------------------------------------------------------
        tables_layout = QHBoxLayout()
        tables_layout.setSpacing(16)

        # Left Column: Recent Transactions Table
        tx_card = QFrame()
        tx_card.setProperty("class", "CardFrame")
        tx_layout = QVBoxLayout(tx_card)
        tx_layout.setSpacing(12)

        tx_header = QHBoxLayout()
        tx_title = QLabel("Recent Transactions")
        tx_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #172033;")
        tx_header.addWidget(tx_title)
        tx_header.addStretch()

        view_tx_btn = QPushButton("View All Transactions →")
        view_tx_btn.setProperty("class", "SecondaryButton")
        view_tx_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_tx_btn.clicked.connect(lambda: self._route_to("transactions"))
        tx_header.addWidget(view_tx_btn)
        tx_layout.addLayout(tx_header)

        self.transactions_table = QTableWidget()
        self.transactions_table.setColumnCount(5)
        self.transactions_table.setHorizontalHeaderLabels([
            "Reference",
            "Account",
            "Type",
            "Amount",
            "Status",
        ])
        self.transactions_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.transactions_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.transactions_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.transactions_table.setAlternatingRowColors(True)
        self.transactions_table.setShowGrid(False)
        self.transactions_table.verticalHeader().setVisible(False)
        self.transactions_table.setMinimumHeight(240)

        tx_h = self.transactions_table.horizontalHeader()
        tx_h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tx_h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tx_h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tx_h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        tx_h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        tx_layout.addWidget(self.transactions_table)
        tables_layout.addWidget(tx_card, stretch=50)

        # Right Column: Primary Customer Portfolios
        left_card = QFrame()
        left_card.setProperty("class", "CardFrame")
        left_layout = QVBoxLayout(left_card)
        left_layout.setSpacing(12)

        left_header = QHBoxLayout()
        left_title = QLabel("Customer Portfolios")
        left_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #172033;")
        left_header.addWidget(left_title)
        left_header.addStretch()

        view_all_btn = QPushButton("View Accounts Directory →")
        view_all_btn.setProperty("class", "SecondaryButton")
        view_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all_btn.clicked.connect(lambda: self._route_to("accounts"))
        left_header.addWidget(view_all_btn)
        left_layout.addLayout(left_header)

        # Accounts Preview Table
        self.accounts_table = QTableWidget()
        self.accounts_table.setColumnCount(5)
        self.accounts_table.setHorizontalHeaderLabels([
            "Account Number",
            "Customer Name",
            "Location",
            "Status",
            "Balance",
        ])
        self.accounts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.accounts_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.accounts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.accounts_table.setAlternatingRowColors(True)
        self.accounts_table.setShowGrid(False)
        self.accounts_table.verticalHeader().setVisible(False)
        self.accounts_table.setMinimumHeight(240)

        h_header = self.accounts_table.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.accounts_table.doubleClicked.connect(self._on_table_double_clicked)
        left_layout.addWidget(self.accounts_table)

        tables_layout.addWidget(left_card, stretch=50)

        layout.addLayout(tables_layout)

        scroll_area.setWidget(container)
        root_layout.addWidget(scroll_area)

    def _create_kpi_card(
        self,
        title: str,
        initial_value: str,
        initial_sub: str,
        icon_name: str,
    ) -> tuple[QFrame, QLabel, QLabel]:
        """Create a professional institutional KPI metric card."""
        card = QFrame()
        card.setProperty("class", "CardFrame")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 16, 18, 16)
        card_layout.setSpacing(6)

        header_row = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setProperty("class", "CardTitle")
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon(icon_name, color="#2563EB", size=18).pixmap(18, 18))
        header_row.addWidget(icon_lbl)
        card_layout.addLayout(header_row)

        val_lbl = QLabel(initial_value)
        val_lbl.setProperty("class", "CardValue")
        card_layout.addWidget(val_lbl)

        sub_lbl = QLabel(initial_sub)
        sub_lbl.setProperty("class", "CardMuted")
        card_layout.addWidget(sub_lbl)

        return card, val_lbl, sub_lbl

    def _create_action_card(
        self,
        icon_name: str,
        title: str,
        description: str,
        target_route: str,
    ) -> QPushButton:
        """Create an interactive desk action launch button."""
        btn = QPushButton()
        btn.setProperty("class", "SecondaryButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 6px; padding: 10px 14px; text-align: left; }"
            "QPushButton:hover { background-color: #F8FAFC; border-color: #2563EB; }"
        )

        inner_layout = QHBoxLayout(btn)
        inner_layout.setContentsMargins(4, 2, 4, 2)
        inner_layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_icon(icon_name, color="#2563EB", size=20).pixmap(20, 20))
        inner_layout.addWidget(icon_lbl)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #172033;")
        desc_lbl = QLabel(description)
        desc_lbl.setStyleSheet("font-size: 11px; color: #64748B;")
        text_layout.addWidget(title_lbl)
        text_layout.addWidget(desc_lbl)

        inner_layout.addLayout(text_layout, stretch=1)

        arrow_lbl = QLabel()
        arrow_lbl.setPixmap(get_icon("chevron_right", color="#94A3B8", size=14).pixmap(14, 14))
        inner_layout.addWidget(arrow_lbl)

        btn.clicked.connect(lambda: self._route_to(target_route))
        return btn

    def _create_analytics_row(self, label_text: str) -> tuple[QHBoxLayout, QLabel, QProgressBar]:
        """Create a visual analytics meter row."""
        row = QHBoxLayout()
        row.setSpacing(10)

        lbl = QLabel(f"{label_text}: $0.00 (0)")
        lbl.setStyleSheet("font-size: 12px; font-weight: 500; color: #172033; min-width: 200px;")
        row.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(8)
        bar.setStyleSheet(
            "QProgressBar { background-color: #F1F5F9; border-radius: 4px; border: none; }"
            "QProgressBar::chunk { background-color: #2563EB; border-radius: 4px; }"
        )
        row.addWidget(bar, stretch=1)

        return row, lbl, bar

    def _route_to(self, route_key: str) -> None:
        """Invoke navigation callback to switch views."""
        if self.navigate_callback:
            self.navigate_callback(route_key)

    def _on_table_double_clicked(self) -> None:
        """Double-clicking account row opens accounts directory."""
        self._route_to("accounts")

    def load_data(self) -> None:
        """Fetch and populate live metrics asynchronously."""
        if not self.banking_service:
            return

        if self.task_runner:
            self.task_runner.run_async(
                self._fetch_dashboard_data,
                on_result=self._on_data_loaded,
                on_error=self._on_data_error,
            )
        else:
            data = self._fetch_dashboard_data()
            self._on_data_loaded(data)

    def _fetch_dashboard_data(self) -> dict:
        """Worker background task gathering executive financial metrics from real backend."""
        accounts, total_count = self.banking_service.list_accounts(page=1, page_size=100)
        total_aum = sum((acc.balance for acc in accounts), Decimal("0.00"))
        active_count = sum(1 for acc in accounts if acc.is_active)

        # Balance tier distribution
        balance_tiers = {
            "< $1,000": 0,
            "$1,000 to $10,000": 0,
            "$10,000 to $50,000": 0,
            "Over $50,000": 0,
        }
        for acc in accounts:
            b = acc.balance
            if b < Decimal("1000.00"):
                balance_tiers["< $1,000"] += 1
            elif b < Decimal("10000.00"):
                balance_tiers["$1,000 to $10,000"] += 1
            elif b < Decimal("50000.00"):
                balance_tiers["$10,000 to $50,000"] += 1
            else:
                balance_tiers["Over $50,000"] += 1

        recent_transactions: list[dict] = []
        total_tx_count = 0
        type_breakdown = {
            "DEPOSIT": Decimal("0.00"),
            "WITHDRAWAL": Decimal("0.00"),
            "TRANSFER": Decimal("0.00"),
        }
        type_counts = {"DEPOSIT": 0, "WITHDRAWAL": 0, "TRANSFER": 0}

        try:
            with self.banking_service._session_factory() as session:
                from novabank.infrastructure.db.models import TransactionModel

                total_tx_count = session.query(TransactionModel).count()
                tx_models = (
                    session.query(TransactionModel)
                    .order_by(TransactionModel.created_at.desc())
                    .limit(10)
                    .all()
                )
                for m in tx_models:
                    recent_transactions.append({
                        "ref": m.transaction_ref,
                        "account": m.account_number,
                        "type": m.transaction_type,
                        "direction": m.direction,
                        "amount": m.amount,
                        "currency": m.currency,
                        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M"),
                        "status": "SETTLED",
                    })

                all_txs = (
                    session.query(TransactionModel.transaction_type, TransactionModel.amount).all()
                )
                for t_type, amt in all_txs:
                    if t_type in type_breakdown:
                        type_breakdown[t_type] += amt
                        type_counts[t_type] += 1
        except Exception:
            pass

        return {
            "accounts": accounts,
            "total_count": total_count,
            "total_aum": total_aum,
            "active_count": active_count,
            "balance_tiers": balance_tiers,
            "recent_transactions": recent_transactions,
            "total_tx_count": total_tx_count,
            "type_breakdown": type_breakdown,
            "type_counts": type_counts,
        }

    def _on_data_loaded(self, data: dict) -> None:
        """Update KPI metrics, analytics meters, and populate account and transaction tables."""
        accounts: list[AccountDTO] = data.get("accounts", [])
        self._accounts_cache = accounts
        total_aum: Decimal = data.get("total_aum", Decimal("0.00"))
        active_count: int = data.get("active_count", 0)
        total_count: int = data.get("total_count", 0)
        total_tx_count: int = data.get("total_tx_count", 0)
        recent_transactions: list[dict] = data.get("recent_transactions", [])
        type_breakdown = data.get("type_breakdown", {})
        type_counts = data.get("type_counts", {})
        balance_tiers = data.get("balance_tiers", {})

        # Update 4 Core KPI Cards
        self.val_aum.setText(f"${total_aum:,.2f}")
        self.sub_aum.setText(f"Aggregated across {total_count} customer account{'s' if total_count != 1 else ''}")

        self.val_acc.setText(f"{active_count} Active")
        self.sub_acc.setText(f"{total_count} total registered accounts")

        self.val_vol.setText(f"{total_tx_count} Settled")
        self.sub_vol.setText("All transactions cryptographically ledgered")

        self.val_sec.setText("0 Pending")
        self.sub_sec.setText("Real-time atomic settlement")

        # Update Analytics: Activity Volume Breakdown
        dep_amt = type_breakdown.get("DEPOSIT", Decimal("0.00"))
        dep_cnt = type_counts.get("DEPOSIT", 0)
        wdr_amt = type_breakdown.get("WITHDRAWAL", Decimal("0.00"))
        wdr_cnt = type_counts.get("WITHDRAWAL", 0)
        trf_amt = type_breakdown.get("TRANSFER", Decimal("0.00"))
        trf_cnt = type_counts.get("TRANSFER", 0)
        total_flow = dep_amt + wdr_amt + trf_amt

        self.dep_lbl.setText(f"Deposits: ${dep_amt:,.2f} ({dep_cnt})")
        self.dep_bar.setValue(int((dep_amt / total_flow * 100)) if total_flow > 0 else 0)

        self.wdr_lbl.setText(f"Withdrawals: ${wdr_amt:,.2f} ({wdr_cnt})")
        self.wdr_bar.setValue(int((wdr_amt / total_flow * 100)) if total_flow > 0 else 0)

        self.trf_lbl.setText(f"Transfers: ${trf_amt:,.2f} ({trf_cnt})")
        self.trf_bar.setValue(int((trf_amt / total_flow * 100)) if total_flow > 0 else 0)

        # Update Analytics: Account Balance Distribution
        t1 = balance_tiers.get("< $1,000", 0)
        t2 = balance_tiers.get("$1,000 to $10,000", 0)
        t3 = balance_tiers.get("$10,000 to $50,000", 0)
        t4 = balance_tiers.get("Over $50,000", 0)
        n_accs = max(total_count, 1)

        self.tier1_lbl.setText(f"Under $1,000: {t1} account{'s' if t1 != 1 else ''}")
        self.tier1_bar.setValue(int((t1 / n_accs) * 100))

        self.tier2_lbl.setText(f"$1,000 to $10,000: {t2} account{'s' if t2 != 1 else ''}")
        self.tier2_bar.setValue(int((t2 / n_accs) * 100))

        self.tier3_lbl.setText(f"$10,000 to $50,000: {t3} account{'s' if t3 != 1 else ''}")
        self.tier3_bar.setValue(int((t3 / n_accs) * 100))

        self.tier4_lbl.setText(f"Over $50,000: {t4} account{'s' if t4 != 1 else ''}")
        self.tier4_bar.setValue(int((t4 / n_accs) * 100))

        # Populate Recent Transactions Table
        self.transactions_table.setRowCount(len(recent_transactions))
        for row, tx in enumerate(recent_transactions):
            item_ref = QTableWidgetItem(tx["ref"][:13] + "..." if len(tx["ref"]) > 16 else tx["ref"])
            item_ref.setFont(QFont("Consolas", 10))

            item_acc = QTableWidgetItem(tx["account"])
            item_acc.setFont(QFont("Consolas", 10))

            item_type = QTableWidgetItem(tx["type"])

            direction = tx.get("direction", "CREDIT")
            amount_val = tx["amount"]
            if direction == "CREDIT" or tx["type"] == "DEPOSIT":
                formatted_amt = f"+${amount_val:,.2f}"
            else:
                formatted_amt = f"-${amount_val:,.2f}"

            item_amt = QTableWidgetItem(formatted_amt)
            item_amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_amt.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

            item_status = QTableWidgetItem(tx["status"])
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            self.transactions_table.setItem(row, 0, item_ref)
            self.transactions_table.setItem(row, 1, item_acc)
            self.transactions_table.setItem(row, 2, item_type)
            self.transactions_table.setItem(row, 3, item_amt)
            self.transactions_table.setItem(row, 4, item_status)

        # Populate Accounts Table
        display_accounts = accounts[:10]
        self.accounts_table.setRowCount(len(display_accounts))
        for row, acc in enumerate(display_accounts):
            item_num = QTableWidgetItem(acc.account_number)
            item_num.setFont(QFont("Consolas", 10))

            item_name = QTableWidgetItem(acc.holder_name)
            item_loc = QTableWidgetItem(f"{acc.city}, {acc.state}")

            status_str = "ACTIVE" if acc.is_active else "CLOSED"
            item_status = QTableWidgetItem(status_str)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            item_bal = QTableWidgetItem(f"${acc.balance:,.2f}")
            item_bal.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_bal.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))

            self.accounts_table.setItem(row, 0, item_num)
            self.accounts_table.setItem(row, 1, item_name)
            self.accounts_table.setItem(row, 2, item_loc)
            self.accounts_table.setItem(row, 3, item_status)
            self.accounts_table.setItem(row, 4, item_bal)

    def _on_data_error(self, exc: Exception, tb: str) -> None:
        """Handle metric fetch failure gracefully."""
        self.val_aum.setText("Unavailable")
        self.sub_aum.setText(str(exc))
