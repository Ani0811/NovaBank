"""Multi-Currency Treasury & FX Exchange Desk UI View."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.fx_dto import (
    FXQuoteResponseDTO,
    FXRateTableEntryDTO,
    FXTradeDTO,
    TreasuryPositionDTO,
)
from novabank.domain.services.fx_calculator import SUPPORTED_CURRENCIES
from novabank.ui.resources.icons import get_icon
from novabank.ui.viewmodels.fx_treasury_viewmodel import FXTreasuryViewModel


class FXTradeReceiptDialog(QDialog):
    """Institutional modal receipt confirming Spot FX trade execution and settlement."""

    def __init__(self, trade: FXTradeDTO, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.trade = trade
        self.setWindowTitle(f"Foreign Exchange Settlement Receipt - {trade.trade_id}")
        self.setFixedWidth(560)
        self.setModal(True)
        self.setStyleSheet(
            """
            QDialog {
                background-color: #FFFFFF;
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }
            QLabel {
                font-size: 13px;
                color: #172033;
            }
            """
        )
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(18)

        # Header Badge
        header_text = QVBoxLayout()
        header_text.setSpacing(4)

        badge = QLabel("SPOT CONVERSION SETTLED")
        badge.setStyleSheet(
            """
            background-color: #DCFCE7;
            color: #15803D;
            border: 1px solid #BBF7D0;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            """
        )
        badge.setFixedWidth(200)

        title = QLabel("Foreign Exchange Settlement")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033;")
        subtitle = QLabel("Atomic conversion settled against sovereign vault liquidity.")
        subtitle.setStyleSheet("font-size: 12px; color: #64748B;")

        header_text.addWidget(badge)
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        layout.addLayout(header_text)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #E2E8F0; background-color: #E2E8F0; height: 1px;")
        layout.addWidget(div)

        # Data Box
        box = QFrame()
        box.setStyleSheet(
            """
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 14px;
            """
        )
        box_layout = QGridLayout(box)
        box_layout.setVerticalSpacing(10)
        box_layout.setHorizontalSpacing(16)

        def _add_row(row_idx: int, label_text: str, val_text: str, is_highlight: bool = False, is_mono: bool = False, is_green: bool = False):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
            val = QLabel(val_text)
            mono_style = "font-family: 'Consolas', monospace;" if is_mono else ""
            if is_green:
                val.setStyleSheet(f"font-size: 14px; font-weight: 700; color: #15803D; {mono_style}")
            elif is_highlight:
                val.setStyleSheet(f"font-size: 14px; font-weight: 700; color: #17365D; {mono_style}")
            else:
                val.setStyleSheet(f"font-size: 13px; font-weight: 600; color: #172033; {mono_style}")
            box_layout.addWidget(lbl, row_idx, 0)
            box_layout.addWidget(val, row_idx, 1)

        _add_row(0, "Trade Reference ID:", self.trade.trade_id, is_mono=True)
        _add_row(1, "Settlement Reference:", self.trade.settlement_reference, is_mono=True)
        _add_row(2, "Customer Account:", self.trade.account_number, is_mono=True)
        _add_row(3, "Currency Pair Sold:", f"{self.trade.formatted_source_amount} ({self.trade.source_currency})", is_highlight=True)
        _add_row(4, "Currency Pair Bought:", f"{self.trade.formatted_target_amount} ({self.trade.target_currency})", is_green=True)
        _add_row(5, "Spot Benchmark Rate:", f"{self.trade.spot_rate:.5f}", is_mono=True)
        _add_row(6, "Effective Client Rate:", f"{self.trade.effective_rate:.5f}", is_mono=True)
        _add_row(7, "Spread Markup:", f"{self.trade.spread_bps} bps")
        _add_row(8, "Brokerage / Fee:", f"${self.trade.fee_amount:.2f} USD")
        _add_row(9, "Settlement Channel:", "Continuous Linked Settlement (CLS) Netting")
        _add_row(10, "Executed At (UTC):", self.trade.executed_at)
        _add_row(11, "Executing Desk:", self.trade.actor)

        layout.addWidget(box)

        # Institutional Guarantee Footer
        notice = QLabel("Executed in compliance with NovaBank Global Markets Treasury Policies & Master FX Agreement.")
        notice.setStyleSheet("font-size: 11px; color: #94A3B8; font-style: italic;")
        layout.addWidget(notice)

        # Buttons
        btn_row = QHBoxLayout()
        btn_close = QPushButton("Close Receipt")
        btn_close.setFixedHeight(36)
        btn_close.setStyleSheet(
            """
            QPushButton {
                background-color: #17365D;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-weight: 600;
                font-size: 13px;
                padding: 0 20px;
            }
            QPushButton:hover {
                background-color: #1E4273;
            }
            """
        )
        btn_close.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class FXTreasuryView(QWidget):
    """Multi-Currency Treasury & FX Exchange Desk UI View."""

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        viewmodel: Optional[FXTreasuryViewModel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.viewmodel = viewmodel or FXTreasuryViewModel(banking_service, task_runner, parent=self)
        self._target_account: Optional[AccountDTO] = None
        self._current_quote: Optional[FXQuoteResponseDTO] = None
        self._current_trades: list[FXTradeDTO] = []
        self._init_ui()
        self._connect_signals()

    def _init_ui(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-family: 'Segoe UI', -apple-system, sans-serif;
                color: #172033;
            }
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: #FFFFFF;
                border-radius: 6px;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #F8FAFC;
                color: #64748B;
                padding: 10px 20px;
                font-size: 13px;
                font-weight: 600;
                border: 1px solid #E2E8F0;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #17365D;
                border-bottom: 2px solid #2563EB;
            }
            QTabBar::tab:hover:!selected {
                background-color: #F1F5F9;
                color: #0F172A;
            }
            """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 16, 24, 24)
        main_layout.setSpacing(16)

        # Tab Widget
        self.tabs = QTabWidget()
        self.tab_terminal = self._build_terminal_tab()
        self.tab_treasury = self._build_treasury_tab()
        self.tab_blotter = self._build_blotter_tab()

        self.tabs.addTab(self.tab_terminal, get_icon("currency_exchange"), "FX Spot Exchange & Trade Terminal")
        self.tabs.addTab(self.tab_treasury, get_icon("bank"), "Treasury Reserves & Vault Liquidity")
        self.tabs.addTab(self.tab_blotter, get_icon("clock"), "FX Blotter & Settlement Ledger")

        main_layout.addWidget(self.tabs)

    def _build_terminal_tab(self) -> QWidget:
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Top 2-Column Split: Left Ticket, Right Hero Pricing
        top_split = QHBoxLayout()
        top_split.setSpacing(20)

        # Left Column: Spot Order Ticket
        ticket_card = QFrame()
        ticket_card.setStyleSheet(self._card_style())
        ticket_layout = QVBoxLayout(ticket_card)
        ticket_layout.setContentsMargins(20, 20, 20, 20)
        ticket_layout.setSpacing(14)

        ticket_title = QLabel("Spot Conversion Order")
        ticket_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #17365D;")
        ticket_sub = QLabel("Select funding account, currencies, and trading volume.")
        ticket_sub.setStyleSheet("font-size: 12px; color: #64748B;")
        ticket_layout.addWidget(ticket_title)
        ticket_layout.addWidget(ticket_sub)

        # Funding Account Section
        acc_lbl = QLabel("Funding Account")
        acc_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        ticket_layout.addWidget(acc_lbl)

        acc_row = QHBoxLayout()
        self.input_account = QLineEdit()
        self.input_account.setPlaceholderText("12-digit Account Number (e.g. 100000000001)")
        self.input_account.setStyleSheet(self._input_style())
        self.input_account.setFixedHeight(38)
        self.input_account.setFont(QFont("Consolas", 11))
        self.input_account.textChanged.connect(self._on_account_changed)

        self.btn_lookup = QPushButton("Verify")
        self.btn_lookup.setFixedHeight(38)
        self.btn_lookup.setStyleSheet(self._secondary_button_style())
        self.btn_lookup.clicked.connect(self._on_lookup_clicked)
        acc_row.addWidget(self.input_account)
        acc_row.addWidget(self.btn_lookup)
        ticket_layout.addLayout(acc_row)

        self.lbl_account_status = QLabel("")
        self.lbl_account_status.setStyleSheet("font-size: 12px; color: #64748B;")
        ticket_layout.addWidget(self.lbl_account_status)

        # Currencies Row
        ccy_lbl = QLabel("Currency Pair & Direction")
        ccy_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        ticket_layout.addWidget(ccy_lbl)

        ccy_row = QHBoxLayout()
        ccy_row.setSpacing(8)

        self.combo_source = QComboBox()
        self.combo_source.setStyleSheet(self._combo_style())
        self.combo_source.setFixedHeight(38)
        self.combo_source.addItems(SUPPORTED_CURRENCIES)
        self.combo_source.setCurrentText("USD")
        self.combo_source.currentTextChanged.connect(self._on_currency_changed)

        self.btn_swap = QPushButton()
        self.btn_swap.setIcon(get_icon("arrow_left_right"))
        self.btn_swap.setFixedSize(38, 38)
        self.btn_swap.setStyleSheet(self._secondary_button_style())
        self.btn_swap.setToolTip("Invert Currency Direction")
        self.btn_swap.clicked.connect(self._on_swap_currencies)

        self.combo_target = QComboBox()
        self.combo_target.setStyleSheet(self._combo_style())
        self.combo_target.setFixedHeight(38)
        self.combo_target.addItems(SUPPORTED_CURRENCIES)
        self.combo_target.setCurrentText("EUR")
        self.combo_target.currentTextChanged.connect(self._on_currency_changed)

        ccy_row.addWidget(self.combo_source, 2)
        ccy_row.addWidget(self.btn_swap, 1)
        ccy_row.addWidget(self.combo_target, 2)
        ticket_layout.addLayout(ccy_row)

        # Amount Section
        amt_lbl = QLabel("Source Amount to Convert")
        amt_lbl.setStyleSheet("font-size: 12px; font-weight: 600; color: #334155;")
        ticket_layout.addWidget(amt_lbl)

        self.input_amount = QLineEdit()
        self.input_amount.setPlaceholderText("e.g. 10000.00")
        self.input_amount.setStyleSheet(self._input_style())
        self.input_amount.setFixedHeight(38)
        self.input_amount.setFont(QFont("Consolas", 12))
        self.input_amount.textChanged.connect(self._on_amount_changed)
        ticket_layout.addWidget(self.input_amount)

        # Quick Amount Pills
        pills_row = QHBoxLayout()
        pills_row.setSpacing(6)
        for amt_val in ["1,000", "5,000", "10,000", "50,000", "100,000"]:
            pill = QPushButton(f"${amt_val}")
            pill.setFixedHeight(28)
            pill.setStyleSheet(self._pill_style())
            pill.clicked.connect(lambda checked=False, v=amt_val: self._on_quick_amount_clicked(v))
            pills_row.addWidget(pill)
        ticket_layout.addLayout(pills_row)

        # Submit Action
        self.btn_execute = QPushButton("Execute Spot Conversion & Settle Funds")
        self.btn_execute.setFixedHeight(44)
        self.btn_execute.setStyleSheet(self._primary_button_style())
        self.btn_execute.clicked.connect(self._on_execute_clicked)
        self.btn_execute.setEnabled(False)
        ticket_layout.addWidget(self.btn_execute)

        top_split.addWidget(ticket_card, 5)

        # Right Column: Hero Live Pricing Card
        pricing_card = QFrame()
        pricing_card.setStyleSheet(self._card_style())
        pricing_layout = QVBoxLayout(pricing_card)
        pricing_layout.setContentsMargins(20, 20, 20, 20)
        pricing_layout.setSpacing(14)

        pricing_title = QLabel("Institutional FX Pricing")
        pricing_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #17365D;")
        pricing_sub = QLabel("Continuous mid-market quote triangulated against USD benchmark.")
        pricing_sub.setStyleSheet("font-size: 12px; color: #64748B;")
        pricing_layout.addWidget(pricing_title)
        pricing_layout.addWidget(pricing_sub)

        # Large Rate Display Hero
        hero_box = QFrame()
        hero_box.setStyleSheet(
            """
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 16px;
            """
        )
        hero_layout = QVBoxLayout(hero_box)
        hero_layout.setSpacing(6)

        self.lbl_hero_pair = QLabel("USD / EUR")
        self.lbl_hero_pair.setStyleSheet("font-size: 12px; font-weight: 700; color: #64748B; letter-spacing: 0.5px;")

        self.lbl_hero_rate = QLabel("0.92166")
        self.lbl_hero_rate.setFont(QFont("Consolas", 24, QFont.Weight.Bold))
        self.lbl_hero_rate.setStyleSheet("color: #17365D;")

        self.lbl_spread_badge = QLabel("INSTITUTIONAL 20 BPS SPREAD")
        self.lbl_spread_badge.setStyleSheet(
            """
            background-color: #EFF6FF;
            color: #2563EB;
            border: 1px solid #DBEAFE;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 700;
            """
        )
        self.lbl_spread_badge.setFixedWidth(190)

        hero_layout.addWidget(self.lbl_hero_pair)
        hero_layout.addWidget(self.lbl_hero_rate)
        hero_layout.addWidget(self.lbl_spread_badge)
        pricing_layout.addWidget(hero_box)

        # Financial Breakdown Box
        breakdown_box = QFrame()
        breakdown_box.setStyleSheet(
            """
            background-color: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 6px;
            padding: 12px;
            """
        )
        breakdown_layout = QGridLayout(breakdown_box)
        breakdown_layout.setVerticalSpacing(8)
        breakdown_layout.setHorizontalSpacing(14)

        def _make_stat_row(row_idx: int, label_text: str, default_val: str, is_hero: bool = False, is_mono: bool = True):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
            val = QLabel(default_val)
            mono_style = "font-family: 'Consolas', monospace;" if is_mono else ""
            if is_hero:
                val.setStyleSheet(f"font-size: 15px; font-weight: 700; color: #15803D; {mono_style}")
            else:
                val.setStyleSheet(f"font-size: 13px; font-weight: 600; color: #172033; {mono_style}")
            breakdown_layout.addWidget(lbl, row_idx, 0)
            breakdown_layout.addWidget(val, row_idx, 1)
            return val

        self.val_payout = _make_stat_row(0, "Target Amount to Receive:", "0.00 EUR", is_hero=True)
        self.val_benchmark = _make_stat_row(1, "Spot Mid-Market Benchmark:", "0.92166")
        self.val_effective = _make_stat_row(2, "Effective Client Rate:", "0.92166")
        self.val_fee = _make_stat_row(3, "Institutional Fee ($5 min / 0.1%):", "$0.00 USD")
        self.val_debit = _make_stat_row(4, "Total Account Debit:", "$0.00 USD")
        self.val_channel = _make_stat_row(5, "Settlement Protocol:", "Continuous Linked Settlement (CLS)", is_mono=False)

        pricing_layout.addWidget(breakdown_box)
        pricing_layout.addStretch()

        top_split.addWidget(pricing_card, 5)
        layout.addLayout(top_split)

        # Bottom Section: Live Benchmark Rates Ticker Table
        rates_card = QFrame()
        rates_card.setStyleSheet(self._card_style())
        rates_layout = QVBoxLayout(rates_card)
        rates_layout.setContentsMargins(20, 20, 20, 20)
        rates_layout.setSpacing(12)

        rates_header_row = QHBoxLayout()
        rates_title = QLabel("Benchmark FX Spot Rates (USD Major Crosses)")
        rates_title.setStyleSheet("font-size: 15px; font-weight: 700; color: #17365D;")
        rates_sub = QLabel("Live wholesale rates and bid/ask trading quotes")
        rates_sub.setStyleSheet("font-size: 12px; color: #64748B;")

        rates_titles = QVBoxLayout()
        rates_titles.setSpacing(2)
        rates_titles.addWidget(rates_title)
        rates_titles.addWidget(rates_sub)
        rates_header_row.addLayout(rates_titles)
        rates_header_row.addStretch()

        self.btn_refresh_rates = QPushButton("Refresh Rates")
        self.btn_refresh_rates.setIcon(get_icon("refresh"))
        self.btn_refresh_rates.setStyleSheet(self._secondary_button_style())
        self.btn_refresh_rates.setFixedHeight(34)
        self.btn_refresh_rates.clicked.connect(self._on_refresh_rates_clicked)
        rates_header_row.addWidget(self.btn_refresh_rates)
        rates_layout.addLayout(rates_header_row)

        self.rates_table = QTableWidget()
        self.rates_table.setColumnCount(6)
        self.rates_table.setHorizontalHeaderLabels([
            "Currency Pair", "Spot Benchmark", "Bank Bid (Buy)", "Bank Ask (Sell)", "Spread (bps)", "Last Updated"
        ])
        self.rates_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rates_table.verticalHeader().setVisible(False)
        self.rates_table.setStyleSheet(self._table_style())
        self.rates_table.setMinimumHeight(220)
        self.rates_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        rates_layout.addWidget(self.rates_table)

        layout.addWidget(rates_card)

        scroll.setWidget(container)
        wrap_layout = QVBoxLayout(widget)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        wrap_layout.addWidget(scroll)
        return widget

    def _build_treasury_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(18)

        # Top 4 KPI Metrics Cards
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(16)

        def _create_kpi_card(title_text: str, default_val: str, sub_text: str, color_hex: str = "#17365D") -> tuple[QFrame, QLabel]:
            card = QFrame()
            card.setStyleSheet(self._card_style())
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(18, 16, 18, 16)
            c_layout.setSpacing(4)

            lbl_t = QLabel(title_text)
            lbl_t.setStyleSheet("font-size: 12px; font-weight: 600; color: #64748B; letter-spacing: 0.3px;")
            lbl_v = QLabel(default_val)
            lbl_v.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
            lbl_v.setStyleSheet(f"color: {color_hex};")
            lbl_s = QLabel(sub_text)
            lbl_s.setStyleSheet("font-size: 11px; color: #94A3B8;")

            c_layout.addWidget(lbl_t)
            c_layout.addWidget(lbl_v)
            c_layout.addWidget(lbl_s)
            return card, lbl_v

        card1, self.kpi_total_usd = _create_kpi_card("TOTAL TREASURY VALUATION", "$0.00", "Mark-to-market aggregate across 8 currencies")
        card2, self.kpi_active_ccy = _create_kpi_card("ACTIVE VAULT RESERVES", "8 Currencies", "Sovereign liquidity holding desks")
        card3, self.kpi_volume_24h = _create_kpi_card("24H TRADING VOLUME", "$0.00", "Institutional customer spot conversions")
        card4, self.kpi_spread_rev = _create_kpi_card("REALIZED SPREAD REVENUE", "$0.00", "Cumulative 20 bps FX margin profit", color_hex="#15803D")

        kpi_row.addWidget(card1)
        kpi_row.addWidget(card2)
        kpi_row.addWidget(card3)
        kpi_row.addWidget(card4)
        layout.addLayout(kpi_row)

        # Treasury Liquidity Table Card
        table_card = QFrame()
        table_card.setStyleSheet(self._card_style())
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(20, 20, 20, 20)
        table_layout.setSpacing(14)

        t_header_row = QHBoxLayout()
        t_title = QLabel("Sovereign Currency Vault Balances & Asset Allocation")
        t_title.setStyleSheet("font-size: 16px; font-weight: 700; color: #17365D;")
        t_sub = QLabel("Real-time physical liquidity positions backed by central bank reserves.")
        t_sub.setStyleSheet("font-size: 12px; color: #64748B;")

        t_titles = QVBoxLayout()
        t_titles.setSpacing(2)
        t_titles.addWidget(t_title)
        t_titles.addWidget(t_sub)
        t_header_row.addLayout(t_titles)
        t_header_row.addStretch()

        self.btn_revalue_treasury = QPushButton("Revalue Positions")
        self.btn_revalue_treasury.setIcon(get_icon("refresh"))
        self.btn_revalue_treasury.setStyleSheet(self._secondary_button_style())
        self.btn_revalue_treasury.setFixedHeight(34)
        self.btn_revalue_treasury.clicked.connect(self._on_revalue_clicked)
        t_header_row.addWidget(self.btn_revalue_treasury)
        table_layout.addLayout(t_header_row)

        self.treasury_table = QTableWidget()
        self.treasury_table.setColumnCount(7)
        self.treasury_table.setHorizontalHeaderLabels([
            "Currency", "Reserve Balance", "Spot to USD", "Valuation (USD)", "Current Allocation", "Target %", "Status"
        ])
        self.treasury_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.treasury_table.verticalHeader().setVisible(False)
        self.treasury_table.setStyleSheet(self._table_style())
        self.treasury_table.setMinimumHeight(320)
        self.treasury_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table_layout.addWidget(self.treasury_table)

        layout.addWidget(table_card)
        return widget

    def _build_blotter_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Filters Card
        filter_card = QFrame()
        filter_card.setStyleSheet(self._card_style())
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(16, 12, 16, 12)
        filter_layout.setSpacing(12)

        self.filter_acc = QLineEdit()
        self.filter_acc.setPlaceholderText("Filter Account Number...")
        self.filter_acc.setStyleSheet(self._input_style())
        self.filter_acc.setFixedHeight(34)
        self.filter_acc.setFont(QFont("Consolas", 10))

        self.filter_pair = QComboBox()
        self.filter_pair.setStyleSheet(self._combo_style())
        self.filter_pair.setFixedHeight(34)
        self.filter_pair.addItem("All Currency Pairs", "ALL")
        for pair in ["EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "USD/CAD", "AUD/USD", "USD/SGD"]:
            self.filter_pair.addItem(pair, pair)

        self.filter_status = QComboBox()
        self.filter_status.setStyleSheet(self._combo_style())
        self.filter_status.setFixedHeight(34)
        self.filter_status.addItem("All Statuses", "ALL")
        self.filter_status.addItem("EXECUTED", "EXECUTED")
        self.filter_status.addItem("SETTLED", "SETTLED")
        self.filter_status.addItem("CANCELLED", "CANCELLED")

        self.btn_apply_filter = QPushButton("Filter")
        self.btn_apply_filter.setStyleSheet(self._secondary_button_style())
        self.btn_apply_filter.setFixedHeight(34)
        self.btn_apply_filter.clicked.connect(self._on_filter_blotter)

        self.btn_reset_filter = QPushButton("Reset")
        self.btn_reset_filter.setStyleSheet(self._secondary_button_style())
        self.btn_reset_filter.setFixedHeight(34)
        self.btn_reset_filter.clicked.connect(self._on_reset_blotter)

        self.btn_export_csv = QPushButton("Export Blotter (CSV)")
        self.btn_export_csv.setIcon(get_icon("download"))
        self.btn_export_csv.setStyleSheet(self._secondary_button_style())
        self.btn_export_csv.setFixedHeight(34)
        self.btn_export_csv.clicked.connect(self._on_export_csv)

        filter_layout.addWidget(self.filter_acc, 2)
        filter_layout.addWidget(self.filter_pair, 2)
        filter_layout.addWidget(self.filter_status, 2)
        filter_layout.addWidget(self.btn_apply_filter)
        filter_layout.addWidget(self.btn_reset_filter)
        filter_layout.addStretch()
        filter_layout.addWidget(self.btn_export_csv)
        layout.addWidget(filter_card)

        # Blotter Table Card
        blotter_card = QFrame()
        blotter_card.setStyleSheet(self._card_style())
        blotter_layout = QVBoxLayout(blotter_card)
        blotter_layout.setContentsMargins(20, 20, 20, 20)
        blotter_layout.setSpacing(12)

        self.blotter_table = QTableWidget()
        self.blotter_table.setColumnCount(11)
        self.blotter_table.setHorizontalHeaderLabels([
            "Trade ID", "Executed (UTC)", "Account #", "Sold", "Bought", "Spot Rate", "Effective Rate", "Spread ($)", "Fee ($)", "Status", "Receipt"
        ])
        self.blotter_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.blotter_table.horizontalHeader().setSectionResizeMode(10, QHeaderView.ResizeMode.ResizeToContents)
        self.blotter_table.verticalHeader().setVisible(False)
        self.blotter_table.setStyleSheet(self._table_style())
        self.blotter_table.setMinimumHeight(360)
        self.blotter_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        blotter_layout.addWidget(self.blotter_table)

        self.lbl_blotter_count = QLabel("Showing 0 trades | Cryptographically ledgered")
        self.lbl_blotter_count.setStyleSheet("font-size: 12px; color: #64748B;")
        blotter_layout.addWidget(self.lbl_blotter_count)

        layout.addWidget(blotter_card)
        return widget

    def _connect_signals(self) -> None:
        self.viewmodel.account_found.connect(self._on_account_found)
        self.viewmodel.account_lookup_failed.connect(self._on_account_failed)
        self.viewmodel.quote_calculated.connect(self._on_quote_calculated)
        self.viewmodel.quote_failed.connect(self._on_quote_failed)
        self.viewmodel.submitting_changed.connect(self._on_submitting_changed)
        self.viewmodel.trade_executed.connect(self._on_trade_executed)
        self.viewmodel.trade_failed.connect(self._on_trade_failed)
        self.viewmodel.rates_loaded.connect(self._on_rates_loaded)
        self.viewmodel.treasury_updated.connect(self._on_treasury_updated)
        self.viewmodel.trades_loaded.connect(self._on_trades_loaded)
        self.viewmodel.csv_exported.connect(self._on_csv_exported)
        self.viewmodel.csv_export_failed.connect(self._on_csv_failed)

    # ---------------- UI Event Handlers ----------------

    def _on_account_changed(self, text: str) -> None:
        clean = text.strip().replace("-", "").replace(" ", "")
        if len(clean) == 12:
            self.viewmodel.lookup_account(clean)
        else:
            self._target_account = None
            self.lbl_account_status.setText("")
            self._update_execute_affordance()

    def _on_lookup_clicked(self) -> None:
        num = self.input_account.text().strip()
        if num:
            self.viewmodel.lookup_account(num)

    def _on_account_found(self, account: AccountDTO) -> None:
        self._target_account = account
        self.lbl_account_status.setText(f"✓ {account.holder_name} (Balance: ${account.balance:,.2f} {account.currency})")
        self.lbl_account_status.setStyleSheet("font-size: 12px; color: #15803D; font-weight: 600;")
        self._update_execute_affordance()

    def _on_account_failed(self, msg: str) -> None:
        self._target_account = None
        self.lbl_account_status.setText(f"✗ {msg}")
        self.lbl_account_status.setStyleSheet("font-size: 12px; color: #DC2626; font-weight: 500;")
        self._update_execute_affordance()

    def _on_currency_changed(self) -> None:
        self._request_quote_if_ready()

    def _on_amount_changed(self, text: str) -> None:
        self._request_quote_if_ready()

    def _on_quick_amount_clicked(self, val_str: str) -> None:
        clean = val_str.replace(",", "")
        self.input_amount.setText(clean)

    def _on_swap_currencies(self) -> None:
        src = self.combo_source.currentText()
        tgt = self.combo_target.currentText()
        self.combo_source.blockSignals(True)
        self.combo_target.blockSignals(True)
        self.combo_source.setCurrentText(tgt)
        self.combo_target.setCurrentText(src)
        self.combo_source.blockSignals(False)
        self.combo_target.blockSignals(False)
        self._request_quote_if_ready()

    def _request_quote_if_ready(self) -> None:
        src = self.combo_source.currentText()
        tgt = self.combo_target.currentText()
        amt_text = self.input_amount.text().strip()

        if src == tgt:
            self.lbl_hero_pair.setText(f"{src} / {tgt}")
            self.lbl_hero_rate.setText("---")
            self._current_quote = None
            self._update_execute_affordance()
            return

        self.lbl_hero_pair.setText(f"{src} / {tgt}")

        if not amt_text:
            return

        try:
            amt = Decimal(amt_text.replace(",", ""))
            if amt <= Decimal("0.00"):
                return
        except InvalidOperation:
            return

        self.viewmodel.calculate_quote(src, tgt, amt_text)

    def _on_quote_calculated(self, quote: FXQuoteResponseDTO) -> None:
        self._current_quote = quote
        self.lbl_hero_rate.setText(f"{quote.spot_rate:.5f}")
        self.lbl_spread_badge.setText(f"INSTITUTIONAL {quote.spread_bps} BPS SPREAD")

        self.val_payout.setText(f"{quote.formatted_target_amount} {quote.target_currency}")
        self.val_benchmark.setText(f"{quote.spot_rate:.5f}")
        self.val_effective.setText(f"{quote.effective_rate:.5f}")
        self.val_fee.setText(f"${quote.fee_amount:.2f} USD")
        self.val_debit.setText(f"{quote.formatted_source_amount} {quote.source_currency}")

        self._update_execute_affordance()

    def _on_quote_failed(self, msg: str) -> None:
        self._current_quote = None
        self._update_execute_affordance()

    def _update_execute_affordance(self) -> None:
        can_execute = (
            self._target_account is not None
            and self._current_quote is not None
            and not self.viewmodel._is_submitting
        )
        self.btn_execute.setEnabled(can_execute)

    def _on_execute_clicked(self) -> None:
        if not self._target_account or not self._current_quote:
            return

        reply = QMessageBox.question(
            self,
            "Confirm Foreign Exchange Conversion",
            f"Are you sure you want to convert {self._current_quote.formatted_source_amount} {self._current_quote.source_currency} "
            f"to {self._current_quote.formatted_target_amount} {self._current_quote.target_currency} "
            f"@ {self._current_quote.effective_rate:.5f}?\n\n"
            f"Funding Account: {self._target_account.account_number}\n"
            f"Fee: ${self._current_quote.fee_amount:.2f} USD",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            self.viewmodel.execute_trade(
                account_number=self._target_account.account_number,
                source_currency=self._current_quote.source_currency,
                target_currency=self._current_quote.target_currency,
                source_amount=self._current_quote.source_amount,
                actor="senior_fx_trader",
            )

    def _on_submitting_changed(self, is_submitting: bool) -> None:
        self.btn_execute.setEnabled(not is_submitting and self._target_account is not None and self._current_quote is not None)
        self.btn_execute.setText("Settling Spot Trade..." if is_submitting else "Execute Spot Conversion & Settle Funds")

    def _on_trade_executed(self, trade: FXTradeDTO) -> None:
        # Refresh account balance
        if self._target_account:
            self.viewmodel.lookup_account(self._target_account.account_number)

        # Show trade receipt modal
        dialog = FXTradeReceiptDialog(trade, self)
        dialog.exec()

    def _on_trade_failed(self, msg: str) -> None:
        QMessageBox.critical(self, "Trade Execution Rejected", f"Foreign Exchange settlement failed:\n\n{msg}")

    def _on_refresh_rates_clicked(self) -> None:
        self.viewmodel.load_live_rates()

    def _on_revalue_clicked(self) -> None:
        self.viewmodel.load_treasury_overview()

    def _on_rates_loaded(self, rates: list[FXRateTableEntryDTO]) -> None:
        self.rates_table.setRowCount(len(rates))
        for row_idx, r in enumerate(rates):
            pair_item = QTableWidgetItem(r.currency_pair)
            pair_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            pair_item.setForeground(QColor("#17365D"))

            spot_item = QTableWidgetItem(f"{r.spot_rate:.5f}")
            spot_item.setFont(QFont("Consolas", 10))

            bid_item = QTableWidgetItem(f"{r.bid_rate:.5f}")
            bid_item.setFont(QFont("Consolas", 10))

            ask_item = QTableWidgetItem(f"{r.ask_rate:.5f}")
            ask_item.setFont(QFont("Consolas", 10))

            spread_item = QTableWidgetItem(f"{r.spread_bps} bps")
            spread_item.setFont(QFont("Segoe UI", 10))

            time_item = QTableWidgetItem(r.last_updated)
            time_item.setFont(QFont("Consolas", 9))
            time_item.setForeground(QColor("#64748B"))

            self.rates_table.setItem(row_idx, 0, pair_item)
            self.rates_table.setItem(row_idx, 1, spot_item)
            self.rates_table.setItem(row_idx, 2, bid_item)
            self.rates_table.setItem(row_idx, 3, ask_item)
            self.rates_table.setItem(row_idx, 4, spread_item)
            self.rates_table.setItem(row_idx, 5, time_item)

    def _on_treasury_updated(self, summary: dict) -> None:
        total_usd = summary.get("total_usd", Decimal("0.00"))
        vol_24h = summary.get("volume_24h", Decimal("0.00"))
        spread_rev = summary.get("spread_revenue_24h", Decimal("0.00"))
        positions: list[TreasuryPositionDTO] = summary.get("positions", [])

        self.kpi_total_usd.setText(f"${total_usd:,.2f}")
        self.kpi_volume_24h.setText(f"${vol_24h:,.2f}")
        self.kpi_spread_rev.setText(f"${spread_rev:,.2f}")
        self.kpi_active_ccy.setText(f"{len(positions)} Currencies")

        self.treasury_table.setRowCount(len(positions))
        for row_idx, p in enumerate(positions):
            ccy_item = QTableWidgetItem(p.currency)
            ccy_item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
            ccy_item.setForeground(QColor("#17365D"))

            bal_item = QTableWidgetItem(p.formatted_reserve_balance)
            bal_item.setFont(QFont("Consolas", 10))

            rate_item = QTableWidgetItem(f"{p.spot_to_usd:.5f}")
            rate_item.setFont(QFont("Consolas", 10))

            usd_item = QTableWidgetItem(f"${p.usd_equivalent:,.2f}")
            usd_item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))

            # Progress Bar in allocation column
            alloc_bar = QProgressBar()
            alloc_bar.setRange(0, 100)
            alloc_bar.setValue(int(p.current_allocation_pct))
            alloc_bar.setTextVisible(True)
            alloc_bar.setFormat(f"{p.current_allocation_pct:.1f}%")
            alloc_bar.setStyleSheet(
                """
                QProgressBar {
                    border: 1px solid #E2E8F0;
                    border-radius: 4px;
                    text-align: center;
                    background-color: #F8FAFC;
                    font-size: 11px;
                    font-weight: 600;
                    color: #172033;
                }
                QProgressBar::chunk {
                    background-color: #2563EB;
                    border-radius: 3px;
                }
                """
            )

            target_item = QTableWidgetItem(f"{p.target_allocation_pct:.1f}%")
            target_item.setFont(QFont("Segoe UI", 10))

            status_item = QTableWidgetItem("LIQUID" if p.reserve_balance > Decimal("0") else "DEPLETED")
            status_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
            status_item.setForeground(QColor("#15803D" if p.reserve_balance > Decimal("0") else "#DC2626"))

            self.treasury_table.setItem(row_idx, 0, ccy_item)
            self.treasury_table.setItem(row_idx, 1, bal_item)
            self.treasury_table.setItem(row_idx, 2, rate_item)
            self.treasury_table.setItem(row_idx, 3, usd_item)
            self.treasury_table.setCellWidget(row_idx, 4, alloc_bar)
            self.treasury_table.setItem(row_idx, 5, target_item)
            self.treasury_table.setItem(row_idx, 6, status_item)

    def _on_filter_blotter(self) -> None:
        acc = self.filter_acc.text().strip() or None
        pair = self.filter_pair.currentData()
        status = self.filter_status.currentData()
        self.viewmodel.load_trades(account_number=acc, pair=pair, status=status)

    def _on_reset_blotter(self) -> None:
        self.filter_acc.clear()
        self.filter_pair.setCurrentIndex(0)
        self.filter_status.setCurrentIndex(0)
        self.viewmodel.load_trades()

    def _on_trades_loaded(self, trades: list[FXTradeDTO], total: int) -> None:
        self._current_trades = trades
        self.blotter_table.setRowCount(len(trades))
        for row_idx, t in enumerate(trades):
            id_item = QTableWidgetItem(t.trade_id)
            id_item.setFont(QFont("Consolas", 9))

            time_item = QTableWidgetItem(t.executed_at)
            time_item.setFont(QFont("Consolas", 9))
            time_item.setForeground(QColor("#64748B"))

            acc_item = QTableWidgetItem(t.account_number)
            acc_item.setFont(QFont("Consolas", 9))

            sold_item = QTableWidgetItem(f"{t.formatted_source_amount} {t.source_currency}")
            sold_item.setFont(QFont("Consolas", 10))

            bought_item = QTableWidgetItem(f"{t.formatted_target_amount} {t.target_currency}")
            bought_item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            bought_item.setForeground(QColor("#15803D"))

            spot_item = QTableWidgetItem(f"{t.spot_rate:.5f}")
            spot_item.setFont(QFont("Consolas", 9))

            eff_item = QTableWidgetItem(f"{t.effective_rate:.5f}")
            eff_item.setFont(QFont("Consolas", 9))

            spread_item = QTableWidgetItem(f"${t.spread_revenue_usd:.2f}")
            spread_item.setFont(QFont("Consolas", 9))

            fee_item = QTableWidgetItem(f"${t.fee_amount:.2f}")
            fee_item.setFont(QFont("Consolas", 9))

            status_item = QTableWidgetItem(t.status)
            status_item.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            status_item.setForeground(QColor("#15803D" if t.status == "EXECUTED" else "#B45309"))

            # Receipt action button
            btn_receipt = QPushButton("Receipt")
            btn_receipt.setFixedHeight(24)
            btn_receipt.setStyleSheet(self._mini_button_style())
            btn_receipt.clicked.connect(lambda checked=False, tr=t: self._show_receipt(tr))

            self.blotter_table.setItem(row_idx, 0, id_item)
            self.blotter_table.setItem(row_idx, 1, time_item)
            self.blotter_table.setItem(row_idx, 2, acc_item)
            self.blotter_table.setItem(row_idx, 3, sold_item)
            self.blotter_table.setItem(row_idx, 4, bought_item)
            self.blotter_table.setItem(row_idx, 5, spot_item)
            self.blotter_table.setItem(row_idx, 6, eff_item)
            self.blotter_table.setItem(row_idx, 7, spread_item)
            self.blotter_table.setItem(row_idx, 8, fee_item)
            self.blotter_table.setItem(row_idx, 9, status_item)
            self.blotter_table.setCellWidget(row_idx, 10, btn_receipt)

        self.lbl_blotter_count.setText(f"Showing {len(trades)} of {total} settled trades | Cryptographically signed ledger")

    def _show_receipt(self, trade: FXTradeDTO) -> None:
        dialog = FXTradeReceiptDialog(trade, self)
        dialog.exec()

    def _on_export_csv(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export FX Blotter CSV",
            "fx_trade_blotter.csv",
            "CSV Documents (*.csv);;All Files (*)",
        )
        if file_path:
            self.viewmodel.export_blotter_csv(destination=file_path)

    def _on_csv_exported(self, path: str) -> None:
        QMessageBox.information(self, "Export Complete", f"FX blotter exported successfully to:\n\n{path}")

    def _on_csv_failed(self, msg: str) -> None:
        QMessageBox.critical(self, "Export Failed", f"Could not export FX blotter:\n\n{msg}")

    def refresh_data(self) -> None:
        """Triggered upon tab display or navigation."""
        self.viewmodel.load_live_rates()
        self.viewmodel.load_treasury_overview()
        self.viewmodel.load_trades()

    # ---------------- Style Helpers ----------------

    def _card_style(self) -> str:
        return """
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
            }
        """

    def _input_style(self) -> str:
        return """
            QLineEdit {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                color: #172033;
            }
            QLineEdit:focus {
                border: 1px solid #2563EB;
            }
        """

    def _combo_style(self) -> str:
        return """
            QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 6px 10px;
                font-size: 13px;
                color: #172033;
            }
            QComboBox:focus {
                border: 1px solid #2563EB;
            }
        """

    def _primary_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #17365D;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #1E4273;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
                color: #F1F5F9;
            }
        """

    def _secondary_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #FFFFFF;
                color: #334155;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #F8FAFC;
                border-color: #94A3B8;
            }
        """

    def _pill_style(self) -> str:
        return """
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #E2E8F0;
                border-radius: 14px;
                font-size: 11px;
                font-weight: 600;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                color: #0F172A;
            }
        """

    def _mini_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #EFF6FF;
                color: #2563EB;
                border: 1px solid #DBEAFE;
                border-radius: 3px;
                font-size: 11px;
                font-weight: 600;
                padding: 2px 8px;
            }
            QPushButton:hover {
                background-color: #DBEAFE;
            }
        """

    def _table_style(self) -> str:
        return """
            QTableWidget {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 4px;
                gridline-color: #F1F5F9;
                font-size: 13px;
                color: #172033;
            }
            QHeaderView::section {
                background-color: #F8FAFC;
                color: #64748B;
                padding: 8px 6px;
                font-weight: 600;
                font-size: 12px;
                border: none;
                border-bottom: 1px solid #E2E8F0;
            }
            QTableWidget::item:selected {
                background-color: #EFF6FF;
                color: #17365D;
            }
        """
