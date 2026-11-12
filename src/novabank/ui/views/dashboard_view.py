"""Dashboard View for NovaBank Desktop Platform.

High-density institutional banking operations terminal delivering real-time telemetry,
direct ledger transactions, customer portfolios, and liquidity analytics without dead whitespace.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
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
    """Institutional banking operations overview with immediate real-time ledger access."""

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

        # Scrollable container ensuring no horizontal overflow
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("background: transparent;")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        # ---------------------------------------------------------------------
        # 1. Action Toolbar & Live Status Row
        # ---------------------------------------------------------------------
        action_strip = QHBoxLayout()
        action_strip.setSpacing(8)

        # Quick desk buttons
        btn_open = QPushButton("+ Open Account")
        btn_open.setIcon(get_icon("open_account", color="#FFFFFF", size=13))
        btn_open.setStyleSheet(
            "QPushButton { background-color: #2563EB; border: none; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 600; color: #FFFFFF; }"
            "QPushButton:hover { background-color: #1D4ED8; }"
        )
        btn_open.clicked.connect(lambda: self._route_to("open_account"))

        btn_dep = QPushButton("+ Deposit")
        btn_dep.setIcon(get_icon("deposits", color="#15803D", size=13))
        btn_dep.setStyleSheet(
            "QPushButton { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 600; color: #15803D; }"
            "QPushButton:hover { background-color: #F0FDF4; border-color: #86EFAC; }"
        )
        btn_dep.clicked.connect(lambda: self._route_to("deposits"))

        btn_wdr = QPushButton("– Withdraw")
        btn_wdr.setIcon(get_icon("withdrawals", color="#DC2626", size=13))
        btn_wdr.setStyleSheet(
            "QPushButton { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 600; color: #DC2626; }"
            "QPushButton:hover { background-color: #FEF2F2; border-color: #FECACA; }"
        )
        btn_wdr.clicked.connect(lambda: self._route_to("withdrawals"))

        btn_trf = QPushButton("⇄ Transfer")
        btn_trf.setIcon(get_icon("transfers", color="#334155", size=13))
        btn_trf.setStyleSheet(
            "QPushButton { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 600; color: #334155; }"
            "QPushButton:hover { background-color: #F8FAFC; border-color: #94A3B8; }"
        )
        btn_trf.clicked.connect(lambda: self._route_to("transfers"))

        btn_stmt = QPushButton("Statements")
        btn_stmt.setIcon(get_icon("statements", color="#334155", size=13))
        btn_stmt.setStyleSheet(
            "QPushButton { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 12px; font-size: 12px; font-weight: 600; color: #334155; }"
            "QPushButton:hover { background-color: #F8FAFC; border-color: #94A3B8; }"
        )
        btn_stmt.clicked.connect(lambda: self._route_to("statements"))

        action_strip.addWidget(btn_open)
        action_strip.addWidget(btn_dep)
        action_strip.addWidget(btn_wdr)
        action_strip.addWidget(btn_trf)
        action_strip.addWidget(btn_stmt)
        action_strip.addStretch()

        self.pill_system = QLabel("Live Core Ledger")
        self.pill_system.setProperty("class", "StatusIndicatorPill")
        self.pill_system.setProperty("status", "success")

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setIcon(get_icon("refresh", color="#475569", size=12))
        self.refresh_btn.setStyleSheet(
            "QPushButton { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 500; color: #475569; }"
            "QPushButton:hover { background-color: #F8FAFC; border-color: #94A3B8; }"
        )
        self.refresh_btn.clicked.connect(self.load_data)

        action_strip.addWidget(self.pill_system)
        action_strip.addWidget(self.refresh_btn)
        layout.addLayout(action_strip)

        # ---------------------------------------------------------------------
        # 2. Compact Financial Overview KPIs (4 Core Institutional Metrics)
        # ---------------------------------------------------------------------
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(10)

        self.card_aum, self.val_aum, self.sub_aum = self._create_kpi_card(
            title="TOTAL ASSETS (AUM)",
            initial_value="$0.00",
            initial_sub="Aggregated balances",
            icon_name="dollar_sign",
        )
        kpi_row.addWidget(self.card_aum)

        self.card_acc, self.val_acc, self.sub_acc = self._create_kpi_card(
            title="ACTIVE ACCOUNTS",
            initial_value="0 Active",
            initial_sub="Registered accounts",
            icon_name="accounts",
        )
        kpi_row.addWidget(self.card_acc)

        self.card_vol, self.val_vol, self.sub_vol = self._create_kpi_card(
            title="TOTAL TRANSACTIONS",
            initial_value="0 Settled",
            initial_sub="Settled ledger entries",
            icon_name="transactions",
        )
        kpi_row.addWidget(self.card_vol)

        self.card_sec, self.val_sec, self.sub_sec = self._create_kpi_card(
            title="SETTLEMENT STATUS",
            initial_value="0 Pending",
            initial_sub="100% real-time settlement",
            icon_name="clock",
        )
        kpi_row.addWidget(self.card_sec)

        layout.addLayout(kpi_row)

        # ---------------------------------------------------------------------
        # 3. Core Operational Workspace Split (Immediate Real Data Visibility)
        # Left 60%: Recent Transactions Ledger Table
        # Right 40%: Primary Customer Portfolios + Liquidity Telemetry
        # ---------------------------------------------------------------------
        workspace_layout = QHBoxLayout()
        workspace_layout.setSpacing(12)

        # LEFT COLUMN: Real-Time Transaction Ledger
        tx_card = QFrame()
        tx_card.setProperty("class", "CardFrame")
        tx_card.setStyleSheet("QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        tx_layout = QVBoxLayout(tx_card)
        tx_layout.setContentsMargins(14, 12, 14, 12)
        tx_layout.setSpacing(10)

        tx_header = QHBoxLayout()
        tx_title = QLabel("Recent Settled Transactions")
        tx_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #172033;")
        tx_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #172033; border: none; background: transparent;")
        tx_header.addWidget(tx_title)
        tx_header.addStretch()

        view_tx_btn = QPushButton("View All →")
        view_tx_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 11px; color: #2563EB; font-weight: 600; padding: 2px 4px; }"
            "QPushButton:hover { text-decoration: underline; color: #1D4ED8; }"
        )
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
        self.transactions_table.setStyleSheet(
            "QTableWidget { background-color: #FFFFFF; alternate-background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; font-size: 12px; }"
            "QHeaderView::section { background-color: #F8FAFC; color: #475569; font-weight: 600; border: none; padding: 7px 6px; border-bottom: 2px solid #E2E8F0; font-size: 11px; }"
            "QTableWidget::item { padding: 6px 8px; border-bottom: 1px solid #F1F5F9; }"
            "QTableWidget::item:selected { background-color: #EFF6FF; color: #1E3A8A; }"
        )

        self.transactions_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tx_h = self.transactions_table.horizontalHeader()
        tx_h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tx_h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tx_h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        tx_h.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        tx_h.resizeSection(0, 95)
        tx_h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        tx_h.resizeSection(1, 95)
        tx_h.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        tx_h.resizeSection(2, 90)
        tx_h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        tx_h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        tx_h.setSectionResizeMode(4, QHeaderView.ResizeMode.Interactive)
        tx_h.resizeSection(4, 70)

        tx_layout.addWidget(self.transactions_table, stretch=1)
        workspace_layout.addWidget(tx_card, stretch=60)
        workspace_layout.addWidget(tx_card, stretch=62)

        # RIGHT COLUMN: Portfolios + Analytics Breakdown
        right_column = QVBoxLayout()
        right_column.setSpacing(12)

        # Right Top: Customer Accounts Portfolio
        acc_card = QFrame()
        acc_card.setProperty("class", "CardFrame")
        acc_card.setStyleSheet("QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        acc_layout = QVBoxLayout(acc_card)
        acc_layout.setContentsMargins(14, 12, 14, 12)
        acc_layout.setSpacing(10)

        acc_header = QHBoxLayout()
        acc_title = QLabel("Primary Customer Portfolios")
        acc_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #172033;")
        acc_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #172033; border: none; background: transparent;")
        acc_header.addWidget(acc_title)
        acc_header.addStretch()

        view_all_btn = QPushButton("Directory →")
        view_all_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none; font-size: 11px; color: #2563EB; font-weight: 600; padding: 2px 4px; }"
            "QPushButton:hover { text-decoration: underline; color: #1D4ED8; }"
        )
        view_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        view_all_btn.clicked.connect(lambda: self._route_to("accounts"))
        acc_header.addWidget(view_all_btn)
        acc_layout.addLayout(acc_header)

        self.accounts_table = QTableWidget()
        self.accounts_table.setColumnCount(4)
        self.accounts_table.setHorizontalHeaderLabels([
            "Account No.",
            "Customer Name",
            "Status",
            "Balance",
        ])
        self.accounts_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.accounts_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.accounts_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.accounts_table.setAlternatingRowColors(True)
        self.accounts_table.setShowGrid(False)
        self.accounts_table.verticalHeader().setVisible(False)
        self.accounts_table.setStyleSheet(
            "QTableWidget { background-color: #FFFFFF; alternate-background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 6px; font-size: 12px; }"
            "QHeaderView::section { background-color: #F8FAFC; color: #475569; font-weight: 600; border: none; padding: 7px 6px; border-bottom: 2px solid #E2E8F0; font-size: 11px; }"
            "QTableWidget::item { padding: 6px 8px; border-bottom: 1px solid #F1F5F9; }"
            "QTableWidget::item:selected { background-color: #EFF6FF; color: #1E3A8A; }"
        )

        self.accounts_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        h_header = self.accounts_table.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        h_header.resizeSection(0, 95)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Interactive)
        h_header.resizeSection(2, 60)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h_header.resizeSection(3, 80)

        self.accounts_table.doubleClicked.connect(self._on_table_double_clicked)
        acc_layout.addWidget(self.accounts_table, stretch=1)
        right_column.addWidget(acc_card, stretch=60)

        # Right Bottom: Operational Analytics Card
        analytics_card = QFrame()
        analytics_card.setProperty("class", "CardFrame")
        analytics_card.setStyleSheet("QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }")
        an_layout = QVBoxLayout(analytics_card)
        an_layout.setContentsMargins(14, 12, 14, 12)
        an_layout.setSpacing(8)

        an_header = QHBoxLayout()
        an_title = QLabel("Operational Flow Breakdown")
        an_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #172033;")
        an_header.addWidget(an_title)
        an_header.addStretch()
        an_layout.addLayout(an_header)

        # Compact Flow Rows
        flows_grid = QVBoxLayout()
        flows_grid.setSpacing(6)

        self.dep_bar_row, self.dep_lbl, self.dep_bar = self._create_analytics_row("Deposits Inflow")
        self.wdr_bar_row, self.wdr_lbl, self.wdr_bar = self._create_analytics_row("Withdrawals Outflow")
        self.trf_bar_row, self.trf_lbl, self.trf_bar = self._create_analytics_row("Transfers Settled")

        flows_grid.addLayout(self.dep_bar_row)
        flows_grid.addLayout(self.wdr_bar_row)
        flows_grid.addLayout(self.trf_bar_row)

        an_layout.addLayout(flows_grid)

        # Hidden but retained dummy progress bars for balance distribution compatibility
        self.tier1_row, self.tier1_lbl, self.tier1_bar = self._create_analytics_row("< $1,000")
        self.tier2_row, self.tier2_lbl, self.tier2_bar = self._create_analytics_row("$1k-$10k")
        self.tier3_row, self.tier3_lbl, self.tier3_bar = self._create_analytics_row("$10k-$50k")
        self.tier4_row, self.tier4_lbl, self.tier4_bar = self._create_analytics_row("> $50k")

        tier_container = QWidget()
        tier_layout = QHBoxLayout(tier_container)
        tier_layout.setContentsMargins(0, 0, 0, 0)
        tier_layout.setSpacing(8)
        tier_layout.addWidget(self.tier1_lbl)
        tier_layout.addWidget(self.tier2_lbl)
        tier_layout.addWidget(self.tier3_lbl)
        tier_layout.addWidget(self.tier4_lbl)
        tier_layout = QGridLayout(tier_container)
        tier_layout.setContentsMargins(0, 4, 0, 0)
        tier_layout.setHorizontalSpacing(10)
        tier_layout.setVerticalSpacing(4)
        tier_layout.addWidget(self.tier1_lbl, 0, 0)
        tier_layout.addWidget(self.tier2_lbl, 0, 1)
        tier_layout.addWidget(self.tier3_lbl, 1, 0)
        tier_layout.addWidget(self.tier4_lbl, 1, 1)
        tier_container.setStyleSheet("color: #64748B; font-size: 11px;")
        an_layout.addWidget(tier_container)

        right_column.addWidget(analytics_card, stretch=40)
        workspace_layout.addLayout(right_column, stretch=40)
        workspace_layout.addLayout(right_column, stretch=38)

        layout.addLayout(workspace_layout, stretch=1)

        scroll_area.setWidget(container)
        root_layout.addWidget(scroll_area)

    def _create_kpi_card(
        self,
        title: str,
        initial_value: str,
        initial_sub: str,
        icon_name: str,
    ) -> tuple[QFrame, QLabel, QLabel]:
        """Create a compact, high-density institutional KPI card."""
        card = QFrame()
        card.setProperty("class", "CardFrame")
        card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(2)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #64748B; letter-spacing: 0.5px; text-transform: uppercase;"
            "font-size: 10px; font-weight: 700; color: #64748B; letter-spacing: 0.5px; text-transform: uppercase; border: none; background: transparent;"
        )
        header_row.addWidget(title_lbl)
        header_row.addStretch()

        icon_lbl = QLabel()
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        icon_lbl.setPixmap(get_icon(icon_name, color="#2563EB", size=13).pixmap(13, 13))
        header_row.addWidget(icon_lbl)
        card_layout.addLayout(header_row)

        val_lbl = QLabel(initial_value)
        val_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033; letter-spacing: -0.3px;")
        val_lbl.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033; letter-spacing: -0.3px; border: none; background: transparent;")
        card_layout.addWidget(val_lbl)

        sub_lbl = QLabel(initial_sub)
        sub_lbl.setStyleSheet("font-size: 11px; color: #94A3B8;")
        sub_lbl.setStyleSheet("font-size: 11px; color: #94A3B8; border: none; background: transparent;")
        card_layout.addWidget(sub_lbl)

        return card, val_lbl, sub_lbl

    def _create_analytics_row(self, label_text: str) -> tuple[QHBoxLayout, QLabel, QProgressBar]:
        """Create a visual analytics meter row."""
        row = QHBoxLayout()
        row.setSpacing(8)

        lbl = QLabel(f"{label_text}: $0.00 (0)")
        lbl.setStyleSheet("font-size: 11px; font-weight: 500; color: #334155; min-width: 130px;")
        lbl.setStyleSheet("font-size: 11px; font-weight: 500; color: #334155;")
        row.addWidget(lbl)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(4)
        bar.setStyleSheet(
            "QProgressBar { background-color: #F1F5F9; border-radius: 2px; border: none; }"
            "QProgressBar::chunk { background-color: #2563EB; border-radius: 2px; }"
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
                    .limit(15)
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
        self.sub_aum.setText(f"{total_count} customer accounts")

        self.val_acc.setText(f"{active_count} Active")
        self.sub_acc.setText(f"{total_count} registered accounts")

        self.val_vol.setText(f"{total_tx_count} Settled")
        self.sub_vol.setText("Atomic ledger entries")

        self.val_sec.setText("0 Pending")
        self.sub_sec.setText("Real-time settlement")

        # Update Analytics: Activity Volume Breakdown
        dep_amt = type_breakdown.get("DEPOSIT", Decimal("0.00"))
        dep_cnt = type_counts.get("DEPOSIT", 0)
        wdr_amt = type_breakdown.get("WITHDRAWAL", Decimal("0.00"))
        wdr_cnt = type_counts.get("WITHDRAWAL", 0)
        trf_amt = type_breakdown.get("TRANSFER", Decimal("0.00"))
        trf_cnt = type_counts.get("TRANSFER", 0)
        total_flow = dep_amt + wdr_amt + trf_amt

        self.dep_lbl.setText(f"Deposits Inflow: ${dep_amt:,.2f} ({dep_cnt})")
        self.dep_bar.setValue(int((dep_amt / total_flow * 100)) if total_flow > 0 else 0)

        self.wdr_lbl.setText(f"Withdrawals Outflow: ${wdr_amt:,.2f} ({wdr_cnt})")
        self.wdr_bar.setValue(int((wdr_amt / total_flow * 100)) if total_flow > 0 else 0)

        self.trf_lbl.setText(f"Transfers Settled: ${trf_amt:,.2f} ({trf_cnt})")
        self.trf_bar.setValue(int((trf_amt / total_flow * 100)) if total_flow > 0 else 0)

        # Update Analytics: Account Balance Distribution
        t1 = balance_tiers.get("< $1,000", 0)
        t2 = balance_tiers.get("$1,000 to $10,000", 0)
        t3 = balance_tiers.get("$10,000 to $50,000", 0)
        t4 = balance_tiers.get("Over $50,000", 0)
        n_accs = max(total_count, 1)

        self.tier1_lbl.setText(f"< $1k: {t1}")
        self.tier1_bar.setValue(int((t1 / n_accs) * 100))

        self.tier2_lbl.setText(f"$1k-$10k: {t2}")
        self.tier2_bar.setValue(int((t2 / n_accs) * 100))

        self.tier3_lbl.setText(f"$10k-$50k: {t3}")
        self.tier3_bar.setValue(int((t3 / n_accs) * 100))

        self.tier4_lbl.setText(f"> $50k: {t4}")
        self.tier4_bar.setValue(int((t4 / n_accs) * 100))

        # Populate Recent Transactions Table
        self.transactions_table.setRowCount(len(recent_transactions))
        for row, tx in enumerate(recent_transactions):
            item_ref = QTableWidgetItem(tx["ref"][:13] + "..." if len(tx["ref"]) > 16 else tx["ref"])
            item_ref.setFont(QFont("Consolas", 9))
            item_ref.setForeground(QColor("#334155"))

            item_acc = QTableWidgetItem(tx["account"])
            item_acc.setFont(QFont("Consolas", 9))
            item_acc.setForeground(QColor("#64748B"))

            item_type = QTableWidgetItem(tx["type"])
            item_type.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            if tx["type"] == "DEPOSIT":
                item_type.setForeground(QColor("#15803D"))
            elif tx["type"] == "WITHDRAWAL":
                item_type.setForeground(QColor("#DC2626"))
            else:
                item_type.setForeground(QColor("#2563EB"))

            direction = tx.get("direction", "CREDIT")
            amount_val = tx["amount"]
            if direction == "CREDIT" or tx["type"] == "DEPOSIT":
                formatted_amt = f"+${amount_val:,.2f}"
                amt_color = QColor("#15803D")
            else:
                formatted_amt = f"-${amount_val:,.2f}"
                amt_color = QColor("#DC2626")

            item_amt = QTableWidgetItem(formatted_amt)
            item_amt.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_amt.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
            item_amt.setForeground(amt_color)

            item_status = QTableWidgetItem(tx["status"])
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_status.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            item_status.setForeground(QColor("#15803D"))

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
            item_num.setFont(QFont("Consolas", 9))
            item_num.setForeground(QColor("#334155"))

            item_name = QTableWidgetItem(acc.holder_name)
            item_name.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))

            status_str = "ACTIVE" if acc.is_active else "CLOSED"
            item_status = QTableWidgetItem(status_str)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            item_status.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            item_status.setForeground(QColor("#15803D") if acc.is_active else QColor("#DC2626"))

            item_bal = QTableWidgetItem(f"${acc.balance:,.2f}")
            item_bal.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item_bal.setFont(QFont("Consolas", 9, QFont.Weight.Bold))

            self.accounts_table.setItem(row, 0, item_num)
            self.accounts_table.setItem(row, 1, item_name)
            self.accounts_table.setItem(row, 2, item_status)
            self.accounts_table.setItem(row, 3, item_bal)

    def _on_data_error(self, exc: Exception, tb: str) -> None:
        """Handle metric fetch failure gracefully."""
        self.val_aum.setText("Unavailable")
        self.sub_aum.setText(str(exc))
