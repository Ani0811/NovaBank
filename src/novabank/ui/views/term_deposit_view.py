"""Certificate of Deposit (CD) Vault & Term Deposits UI View."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.term_deposit_dto import (
    CDAccrualMilestoneDTO,
    CDSimulationResponseDTO,
    CertificateOfDepositDTO,
    EarlyRedemptionPreviewDTO,
    RedemptionResultDTO,
)
from novabank.ui.resources.icons import get_icon
from novabank.ui.viewmodels.term_deposit_viewmodel import TermDepositViewModel

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class CDIssuanceReceiptDialog(QDialog):
    """Institutional modal receipt confirming Certificate of Deposit issuance and fund lockup."""

    def __init__(self, cd: CertificateOfDepositDTO, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.cd = cd
        self.setWindowTitle("Certificate of Deposit Issuance Receipt")
        self.setFixedWidth(540)
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

        badge = QLabel("CERTIFICATE OF DEPOSIT ISSUED")
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
        badge.setFixedWidth(210)

        title = QLabel("Time Deposit Issuance & Lockup")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033;")
        subtitle = QLabel("Principal debited atomically from funding account and held under FDIC terms.")
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

        def _add_row(row_idx: int, label_text: str, val_text: str, is_highlight: bool = False, is_mono: bool = False):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
            val = QLabel(val_text)
            mono_style = "font-family: 'Consolas', monospace;" if is_mono else ""
            if is_highlight:
                val.setStyleSheet(f"font-size: 14px; font-weight: 700; color: #17365D; {mono_style}")
            else:
                val.setStyleSheet(f"font-size: 13px; font-weight: 600; color: #172033; {mono_style}")
            box_layout.addWidget(lbl, row_idx, 0)
            box_layout.addWidget(val, row_idx, 1)

        _add_row(0, "Certificate Number:", self.cd.certificate_number, is_mono=True)
        _add_row(1, "Funding Account:", self.cd.account_number, is_mono=True)
        _add_row(2, "Principal Locked:", self.cd.formatted_principal, is_highlight=True)
        _add_row(3, "Annual Percentage Yield:", self.cd.formatted_apy, is_highlight=True)
        _add_row(4, "Tenor Duration:", f"{self.cd.tenor_months} Months")
        _add_row(5, "Issue Date:", self.cd.issue_date)
        _add_row(6, "Maturity Date:", self.cd.maturity_date)
        _add_row(7, "Projected Maturity Payout:", self.cd.formatted_maturity_amount, is_highlight=True)
        _add_row(8, "Rollover Instruction:", self.cd.rollover_option.replace("_", " ").title())

        layout.addWidget(box)

        # Institutional Guarantee Footer
        notice = QLabel("Insured up to applicable statutory limits by NovaBank Enterprise Reserve Protection.")
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
                padding: 6px 20px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #234E82;
            }
            """
        )
        btn_close.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class CDEarlyRedemptionDialog(QDialog):
    """Institutional modal dialog previewing statutory penalty before premature CD liquidation."""

    def __init__(self, preview: EarlyRedemptionPreviewDTO, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.preview = preview
        self.setWindowTitle("Premature CD Liquidation & Penalty Preview")
        self.setFixedWidth(540)
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
        layout.setSpacing(16)

        # Header Badge
        header_text = QVBoxLayout()
        header_text.setSpacing(4)

        badge = QLabel("REGULATORY PENALTY FORFEITURE")
        badge.setStyleSheet(
            """
            background-color: #FEF2F2;
            color: #DC2626;
            border: 1px solid #FECACA;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 0.5px;
            """
        )
        badge.setFixedWidth(230)

        title = QLabel("Premature Certificate Liquidation")
        title.setStyleSheet("font-size: 18px; font-weight: 700; color: #172033;")
        subtitle = QLabel("Liquidating this CD prior to maturity forfeits statutory interest pursuant to banking regulations.")
        subtitle.setStyleSheet("font-size: 12px; color: #64748B;")
        subtitle.setWordWrap(True)

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

        def _add_row(row_idx: int, label_text: str, val_text: str, is_highlight: bool = False, is_penalty: bool = False, is_mono: bool = False):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 500;")
            val = QLabel(val_text)
            mono_style = "font-family: 'Consolas', monospace;" if is_mono else ""
            if is_penalty:
                val.setStyleSheet(f"font-size: 14px; font-weight: 700; color: #DC2626; {mono_style}")
            elif is_highlight:
                val.setStyleSheet(f"font-size: 14px; font-weight: 700; color: #17365D; {mono_style}")
            else:
                val.setStyleSheet(f"font-size: 13px; font-weight: 600; color: #172033; {mono_style}")
            box_layout.addWidget(lbl, row_idx, 0)
            box_layout.addWidget(val, row_idx, 1)

        _add_row(0, "Certificate Number:", self.preview.certificate_number, is_mono=True)
        _add_row(1, "Original Principal:", self.preview.formatted_principal)
        _add_row(2, "Duration Elapsed:", f"{self.preview.days_held} Days Held")
        _add_row(3, "Gross Accrued Interest:", self.preview.formatted_accrued_interest)
        _add_row(4, "Penalty Period:", f"{self.preview.penalty_months} Months Simple Interest")
        _add_row(5, "Forfeited Statutory Penalty:", f"-{self.preview.formatted_penalty}", is_penalty=True)
        _add_row(6, "Net Liquidation Payout:", self.preview.formatted_net_payout, is_highlight=True)

        layout.addWidget(box)

        # Warning
        warn_box = QFrame()
        warn_box.setStyleSheet("background-color: #FFFBEB; border: 1px solid #FDE68A; border-radius: 4px; padding: 10px;")
        warn_layout = QHBoxLayout(warn_box)
        warn_layout.setContentsMargins(8, 8, 8, 8)
        warn_lbl = QLabel(
            "Liquidation is irreversible. Net funds will be credited immediately to the original account."
        )
        warn_lbl.setStyleSheet("font-size: 11px; color: #B45309; font-weight: 600;")
        warn_lbl.setWordWrap(True)
        warn_layout.addWidget(warn_lbl)
        layout.addWidget(warn_box)

        # Buttons
        btn_row = QHBoxLayout()
        btn_cancel = QPushButton("Cancel & Keep CD Active")
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet(
            """
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 6px 16px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
            """
        )
        btn_cancel.clicked.connect(self.reject)

        btn_confirm = QPushButton("Confirm & Liquidate CD")
        btn_confirm.setFixedHeight(36)
        btn_confirm.setStyleSheet(
            """
            QPushButton {
                background-color: #DC2626;
                color: #FFFFFF;
                border: none;
                border-radius: 4px;
                padding: 6px 18px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #B91C1C;
            }
            """
        )
        btn_confirm.clicked.connect(self.accept)

        btn_row.addStretch()
        btn_row.addWidget(btn_cancel)
        btn_row.addWidget(btn_confirm)
        layout.addLayout(btn_row)


class TermDepositView(QWidget):
    """Institutional Term Deposit & Certificate of Deposit (CD) Vault presentation view."""

    # Pre-defined APY tier schedules
    TENOR_PRESETS = [
        ("3 Months", 3, Decimal("3.25")),
        ("6 Months", 6, Decimal("3.75")),
        ("12 Months", 12, Decimal("4.50")),
        ("18 Months", 18, Decimal("4.65")),
        ("24 Months", 24, Decimal("4.85")),
        ("36 Months", 36, Decimal("5.00")),
        ("60 Months", 60, Decimal("5.25")),
    ]

    def __init__(
        self,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        viewmodel: Optional[TermDepositViewModel] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm = viewmodel or TermDepositViewModel(banking_service, task_runner, parent=self)

        self._selected_tenor_months: int = 12
        self._selected_apy: Decimal = Decimal("4.50")
        self._tenor_buttons: list[QPushButton] = []
        self._pending_break_cd_id: Optional[str] = None

        self._setup_ui()
        self._connect_signals()

        # Trigger initial quote simulation and initial portfolio load
        self._recalculate_quote()
        self.refresh_portfolio()

    def set_services(self, banking_service: BankingService, task_runner: TaskRunner) -> None:
        self.banking_service = banking_service
        self.task_runner = task_runner
        self.vm.set_services(banking_service, task_runner)
        self.refresh_portfolio()

    def _setup_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 20, 28, 24)
        root_layout.setSpacing(14)

        # Tab Widget
        self.tab_widget = QTabWidget(self)
        self.tab_widget.setStyleSheet(
            """
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: #FFFFFF;
                border-radius: 6px;
            }
            QTabBar::tab {
                background-color: #F8FAFC;
                color: #64748B;
                padding: 10px 22px;
                font-weight: 600;
                font-size: 13px;
                border: 1px solid #E2E8F0;
                border-bottom: none;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #FFFFFF;
                color: #17365D;
                border-bottom: 2px solid #2563EB;
            }
            QTabBar::tab:hover:!selected {
                background-color: #F1F5F9;
                color: #172033;
            }
            """
        )

        self.calculator_tab = QWidget()
        self.portfolio_tab = QWidget()
        self.certificate_tab = QWidget()

        self._setup_calculator_tab()
        self._setup_portfolio_tab()
        self._setup_certificate_tab()

        self.tab_widget.addTab(self.calculator_tab, "CD Vault Calculator & Issuance")
        self.tab_widget.addTab(self.portfolio_tab, "Active CD Vault Portfolio")
        self.tab_widget.addTab(self.certificate_tab, "Certificate Details & Accrual Schedule")

        root_layout.addWidget(self.tab_widget)

    # -------------------------------------------------------------------------
    # TAB 1: CD Vault Calculator & Issuance
    # -------------------------------------------------------------------------

    def _setup_calculator_tab(self) -> None:
        scroll = QScrollArea(self.calculator_tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        # Left Column: Configuration Controls
        left_col = QVBoxLayout()
        left_col.setSpacing(16)

        # 1. Funding Account Lookup
        lookup_box = QGroupBox("Funding Account Lookup")
        lookup_box.setStyleSheet(self._group_box_style())
        lookup_layout = QVBoxLayout(lookup_box)
        lookup_layout.setSpacing(10)

        acc_row = QHBoxLayout()
        self.funding_acc_input = QLineEdit()
        self.funding_acc_input.setPlaceholderText("12-Digit Account Number")
        self.funding_acc_input.setMaxLength(12)
        self.funding_acc_input.setFixedHeight(36)
        self.funding_acc_input.setStyleSheet(self._input_mono_style())
        self.funding_acc_input.returnPressed.connect(self._on_lookup_clicked)

        btn_lookup = QPushButton("Verify Account")
        btn_lookup.setFixedHeight(36)
        btn_lookup.setStyleSheet(self._btn_secondary_style())
        btn_lookup.clicked.connect(self._on_lookup_clicked)

        acc_row.addWidget(self.funding_acc_input, stretch=1)
        acc_row.addWidget(btn_lookup)
        lookup_layout.addLayout(acc_row)

        self.account_status_label = QLabel("Enter a 12-digit account number to fund the Certificate of Deposit.")
        self.account_status_label.setStyleSheet("font-size: 12px; color: #64748B;")
        self.account_status_label.setWordWrap(True)
        lookup_layout.addWidget(self.account_status_label)

        left_col.addWidget(lookup_box)

        # 2. Deposit Parameters
        param_box = QGroupBox("Certificate of Deposit Parameters")
        param_box.setStyleSheet(self._group_box_style())
        param_layout = QVBoxLayout(param_box)
        param_layout.setSpacing(14)

        # Principal
        p_label = QLabel("Deposit Principal (USD):")
        p_label.setStyleSheet(self._label_style())
        self.principal_input = QLineEdit("10000.00")
        self.principal_input.setFixedHeight(36)
        self.principal_input.setStyleSheet(self._input_mono_style())
        self.principal_input.textChanged.connect(self._recalculate_quote)
        param_layout.addWidget(p_label)
        param_layout.addWidget(self.principal_input)

        # Quick preset buttons
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        for amt_str in ["1,000", "5,000", "10,000", "25,000", "50,000", "100,000"]:
            p_btn = QPushButton(f"${amt_str}")
            p_btn.setFixedHeight(26)
            p_btn.setStyleSheet(self._pill_style(False))
            p_btn.clicked.connect(lambda _, a=amt_str.replace(",", ""): self._set_principal(a))
            preset_row.addWidget(p_btn)
        param_layout.addLayout(preset_row)

        # Tenor Preset Pills
        t_label = QLabel("Tenor & Guaranteed APY Tier:")
        t_label.setStyleSheet(self._label_style())
        param_layout.addWidget(t_label)

        tenor_pills_row = QHBoxLayout()
        tenor_pills_row.setSpacing(6)
        self._tenor_buttons.clear()

        for label, months, apy in self.TENOR_PRESETS:
            pill = QPushButton(f"{label}\n{apy}%")
            pill.setFixedHeight(44)
            pill.setCheckable(True)
            pill.setChecked(months == self._selected_tenor_months)
            pill.setStyleSheet(self._tenor_pill_style(months == self._selected_tenor_months))
            pill.clicked.connect(lambda _, m=months, r=apy, p=pill: self._select_tenor_preset(m, r, p))
            self._tenor_buttons.append(pill)
            tenor_pills_row.addWidget(pill)
        param_layout.addLayout(tenor_pills_row)

        # Custom Tenor & APY Row
        custom_row = QHBoxLayout()
        custom_row.setSpacing(12)

        tenor_col = QVBoxLayout()
        lbl_months = QLabel("Custom Tenor (Months):")
        lbl_months.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600;")
        self.tenor_spin = QSpinBox()
        self.tenor_spin.setRange(1, 120)
        self.tenor_spin.setValue(12)
        self.tenor_spin.setFixedHeight(34)
        self.tenor_spin.setStyleSheet(self._input_mono_style())
        self.tenor_spin.valueChanged.connect(self._on_custom_tenor_changed)
        tenor_col.addWidget(lbl_months)
        tenor_col.addWidget(self.tenor_spin)

        apy_col = QVBoxLayout()
        lbl_apy = QLabel("Annual Yield (APY %):")
        lbl_apy.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600;")
        self.apy_input = QLineEdit("4.50")
        self.apy_input.setFixedHeight(34)
        self.apy_input.setStyleSheet(self._input_mono_style())
        self.apy_input.textChanged.connect(self._on_custom_apy_changed)
        apy_col.addWidget(lbl_apy)
        apy_col.addWidget(self.apy_input)

        custom_row.addLayout(tenor_col)
        custom_row.addLayout(apy_col)
        param_layout.addLayout(custom_row)

        # Payout Frequency & Rollover Option
        freq_row = QHBoxLayout()
        freq_row.setSpacing(12)

        freq_col = QVBoxLayout()
        lbl_freq = QLabel("Payout Frequency:")
        lbl_freq.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600;")
        self.freq_combo = QComboBox()
        self.freq_combo.addItems(["At Maturity", "Monthly", "Quarterly", "Annually"])
        self.freq_combo.setFixedHeight(34)
        self.freq_combo.setStyleSheet(self._combo_style())
        self.freq_combo.currentTextChanged.connect(self._recalculate_quote)
        freq_col.addWidget(lbl_freq)
        freq_col.addWidget(self.freq_combo)

        roll_col = QVBoxLayout()
        lbl_roll = QLabel("Maturity Rollover:")
        lbl_roll.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600;")
        self.roll_combo = QComboBox()
        self.roll_combo.addItems(["Payout & Close", "Roll Principal & Interest", "Roll Principal Only"])
        self.roll_combo.setFixedHeight(34)
        self.roll_combo.setStyleSheet(self._combo_style())
        roll_col.addWidget(lbl_roll)
        roll_col.addWidget(self.roll_combo)

        freq_row.addLayout(freq_col)
        freq_row.addLayout(roll_col)
        param_layout.addLayout(freq_row)

        left_col.addWidget(param_box)

        # Action Button: Lock Funds & Issue CD
        self.btn_issue_cd = QPushButton("Lock Funds & Issue Certificate of Deposit")
        self.btn_issue_cd.setFixedHeight(44)
        self.btn_issue_cd.setIcon(get_icon("vault", "#FFFFFF"))
        self.btn_issue_cd.setStyleSheet(
            """
            QPushButton {
                background-color: #15803D;
                color: #FFFFFF;
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 700;
                padding: 8px 18px;
            }
            QPushButton:hover {
                background-color: #166534;
            }
            QPushButton:disabled {
                background-color: #94A3B8;
            }
            """
        )
        self.btn_issue_cd.clicked.connect(self._on_issue_cd_clicked)
        left_col.addWidget(self.btn_issue_cd)

        left_col.addStretch()
        layout.addLayout(left_col, stretch=4)

        # Right Column: Hero Yield Card & Accrual Milestone Table
        right_col = QVBoxLayout()
        right_col.setSpacing(16)

        # Projected Yield Hero Card
        self.hero_card = QFrame()
        self.hero_card.setStyleSheet(
            """
            QFrame {
                background-color: #F8FAFC;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 16px;
            }
            """
        )
        hero_layout = QVBoxLayout(self.hero_card)
        hero_layout.setSpacing(12)

        badge_row = QHBoxLayout()
        hero_badge = QLabel("GUARANTEED COMPOUND RETURN")
        hero_badge.setStyleSheet(
            """
            background-color: #DCFCE7;
            color: #15803D;
            border: 1px solid #BBF7D0;
            border-radius: 4px;
            padding: 3px 8px;
            font-size: 11px;
            font-weight: 700;
            """
        )
        badge_row.addWidget(hero_badge)
        badge_row.addStretch()
        hero_layout.addLayout(badge_row)

        payout_hdr = QLabel("Total Payout at Maturity")
        payout_hdr.setStyleSheet("font-size: 12px; color: #64748B; font-weight: 600;")
        self.hero_payout_val = QLabel("$10,450.00")
        self.hero_payout_val.setStyleSheet("font-size: 32px; font-weight: 800; color: #17365D; font-family: 'Consolas', monospace;")
        hero_layout.addWidget(payout_hdr)
        hero_layout.addWidget(self.hero_payout_val)

        # Sub-metrics Grid
        metrics_grid = QGridLayout()
        metrics_grid.setVerticalSpacing(8)
        metrics_grid.setHorizontalSpacing(16)

        def _make_metric(lbl_txt: str, val_txt: str, is_green: bool = False):
            col = QVBoxLayout()
            col.setSpacing(2)
            l = QLabel(lbl_txt)
            l.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600;")
            v = QLabel(val_txt)
            color = "#15803D" if is_green else "#172033"
            v.setStyleSheet(f"font-size: 14px; font-weight: 700; color: {color}; font-family: 'Consolas', monospace;")
            col.addWidget(l)
            col.addWidget(v)
            return col, v

        c0, self.hero_principal_val = _make_metric("Initial Principal", "$10,000.00")
        c1, self.hero_interest_val = _make_metric("Guaranteed Yield", "+$450.00", is_green=True)
        c2, self.hero_apy_val = _make_metric("Effective APY", "4.50%")
        c3, self.hero_maturity_val = _make_metric("Maturity Horizon", "12 Months")

        metrics_grid.addLayout(c0, 0, 0)
        metrics_grid.addLayout(c1, 0, 1)
        metrics_grid.addLayout(c2, 1, 0)
        metrics_grid.addLayout(c3, 1, 1)
        hero_layout.addLayout(metrics_grid)

        # Early Penalty Notice
        penalty_box = QFrame()
        penalty_box.setStyleSheet("background-color: #FEF3C7; border: 1px solid #FDE68A; border-radius: 4px; padding: 8px;")
        penalty_layout = QHBoxLayout(penalty_box)
        penalty_layout.setContentsMargins(6, 6, 6, 6)
        self.hero_penalty_lbl = QLabel(
            "Regulatory Notice: Early withdrawal incurs 3 months simple interest forfeiture under federal rules."
        )
        self.hero_penalty_lbl.setStyleSheet("font-size: 11px; color: #92400E; font-weight: 600;")
        self.hero_penalty_lbl.setWordWrap(True)
        penalty_layout.addWidget(self.hero_penalty_lbl)
        hero_layout.addWidget(penalty_box)

        right_col.addWidget(self.hero_card)

        # Month-by-month Accrual Milestone Table
        table_hdr_row = QHBoxLayout()
        table_lbl = QLabel("Yield Accrual Milestones")
        table_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #17365D;")
        table_hdr_row.addWidget(table_lbl)
        table_hdr_row.addStretch()
        right_col.addLayout(table_hdr_row)

        self.projection_table = QTableWidget()
        self.projection_table.setColumnCount(5)
        self.projection_table.setHorizontalHeaderLabels([
            "Milestone", "Accrual Date", "Periodic Interest", "Cumulative Yield", "Projected Balance"
        ])
        self.projection_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.projection_table.verticalHeader().setVisible(False)
        self.projection_table.setStyleSheet(self._table_style())
        self.projection_table.setMinimumHeight(240)
        right_col.addWidget(self.projection_table)

        layout.addLayout(right_col, stretch=5)
        scroll.setWidget(container)

        tab_layout = QVBoxLayout(self.calculator_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    # -------------------------------------------------------------------------
    # TAB 2: Active CD Vault Portfolio
    # -------------------------------------------------------------------------

    def _setup_portfolio_tab(self) -> None:
        layout = QVBoxLayout(self.portfolio_tab)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 4 Top KPI Cards
        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(14)

        def _create_kpi_card(title: str, val_txt: str, sub_txt: str):
            card = QFrame()
            card.setStyleSheet(
                """
                QFrame {
                    background-color: #F8FAFC;
                    border: 1px solid #E2E8F0;
                    border-radius: 6px;
                    padding: 12px 16px;
                }
                """
            )
            c_layout = QVBoxLayout(card)
            c_layout.setSpacing(4)
            t = QLabel(title)
            t.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600; text-transform: uppercase;")
            v = QLabel(val_txt)
            v.setStyleSheet("font-size: 20px; font-weight: 700; color: #17365D; font-family: 'Consolas', monospace;")
            s = QLabel(sub_txt)
            s.setStyleSheet("font-size: 11px; color: #94A3B8;")
            c_layout.addWidget(t)
            c_layout.addWidget(v)
            c_layout.addWidget(s)
            return card, v, s

        c0, self.kpi_active_count, _ = _create_kpi_card("Active Certificates", "0 Active", "Total time deposits")
        c1, self.kpi_total_principal, _ = _create_kpi_card("Total Locked Principal", "$0.00", "Under active vault custody")
        c2, self.kpi_avg_apy, _ = _create_kpi_card("Average Portfolio APY", "0.00%", "Weighted by principal")
        c3, self.kpi_total_projected, _ = _create_kpi_card("Total Projected Return", "$0.00", "At term maturity")

        kpi_row.addWidget(c0)
        kpi_row.addWidget(c1)
        kpi_row.addWidget(c2)
        kpi_row.addWidget(c3)
        layout.addLayout(kpi_row)

        # Filter Bar
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self.filter_acc_input = QLineEdit()
        self.filter_acc_input.setPlaceholderText("Filter by Funding Account #")
        self.filter_acc_input.setMaxLength(12)
        self.filter_acc_input.setFixedHeight(34)
        self.filter_acc_input.setStyleSheet(self._input_mono_style())
        self.filter_acc_input.returnPressed.connect(self._on_filter_changed)

        self.filter_status_combo = QComboBox()
        self.filter_status_combo.addItems(["All Statuses", "ACTIVE", "MATURED", "PREMATURELY_CLOSED", "ROLLED_OVER"])
        self.filter_status_combo.setFixedHeight(34)
        self.filter_status_combo.setStyleSheet(self._combo_style())
        self.filter_status_combo.currentTextChanged.connect(self._on_filter_changed)

        btn_filter = QPushButton("Apply Filter")
        btn_filter.setFixedHeight(34)
        btn_filter.setStyleSheet(self._btn_secondary_style())
        btn_filter.clicked.connect(self._on_filter_changed)

        btn_refresh = QPushButton("Refresh")
        btn_refresh.setFixedHeight(34)
        btn_refresh.setIcon(get_icon("refresh", "#17365D"))
        btn_refresh.setStyleSheet(self._btn_secondary_style())
        btn_refresh.clicked.connect(self.refresh_portfolio)

        btn_export = QPushButton("Export CSV")
        btn_export.setFixedHeight(34)
        btn_export.setStyleSheet(self._btn_tertiary_style())
        btn_export.clicked.connect(self._on_export_portfolio_csv)

        filter_row.addWidget(self.filter_acc_input, stretch=2)
        filter_row.addWidget(self.filter_status_combo, stretch=1)
        filter_row.addWidget(btn_filter)
        filter_row.addWidget(btn_refresh)
        filter_row.addStretch()
        filter_row.addWidget(btn_export)
        layout.addLayout(filter_row)

        # Portfolio Table
        self.portfolio_table = QTableWidget()
        self.portfolio_table.setColumnCount(10)
        self.portfolio_table.setHorizontalHeaderLabels([
            "Certificate #", "Funding Account", "Principal", "APY", "Tenor",
            "Issue Date", "Maturity Date", "Accrued Yield", "Status", "Actions"
        ])
        self.portfolio_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.portfolio_table.horizontalHeader().setSectionResizeMode(9, QHeaderView.ResizeMode.ResizeToContents)
        self.portfolio_table.verticalHeader().setVisible(False)
        self.portfolio_table.setStyleSheet(self._table_style())
        self.portfolio_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.portfolio_table.cellDoubleClicked.connect(self._on_portfolio_cell_double_clicked)
        layout.addWidget(self.portfolio_table)

    # -------------------------------------------------------------------------
    # TAB 3: Certificate Details & Accrual Schedule
    # -------------------------------------------------------------------------

    def _setup_certificate_tab(self) -> None:
        scroll = QScrollArea(self.certificate_tab)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # Lookup Bar
        lookup_row = QHBoxLayout()
        lookup_row.setSpacing(10)

        lookup_lbl = QLabel("Inspect Certificate:")
        lookup_lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #172033;")
        self.cert_search_input = QLineEdit()
        self.cert_search_input.setPlaceholderText("Enter Certificate Number (e.g. CD-202611-...)")
        self.cert_search_input.setFixedHeight(34)
        self.cert_search_input.setStyleSheet(self._input_mono_style())
        self.cert_search_input.returnPressed.connect(self._on_search_certificate_clicked)

        btn_search_cert = QPushButton("Load Certificate")
        btn_search_cert.setFixedHeight(34)
        btn_search_cert.setStyleSheet(self._btn_secondary_style())
        btn_search_cert.clicked.connect(self._on_search_certificate_clicked)

        lookup_row.addWidget(lookup_lbl)
        lookup_row.addWidget(self.cert_search_input, stretch=1)
        lookup_row.addWidget(btn_search_cert)
        layout.addLayout(lookup_row)

        # Official Security Certificate Document Frame
        self.cert_frame = QFrame()
        self.cert_frame.setStyleSheet(
            """
            QFrame {
                background-color: #F8FAFC;
                border: 2px solid #17365D;
                border-radius: 8px;
                padding: 24px;
            }
            """
        )
        cert_doc_layout = QVBoxLayout(self.cert_frame)
        cert_doc_layout.setSpacing(16)

        # Bank Header & Title
        doc_header = QVBoxLayout()
        doc_header.setSpacing(4)
        doc_bank_title = QLabel("NOVABANK NATIONAL ASSOCIATION")
        doc_bank_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        doc_bank_title.setStyleSheet("font-size: 13px; font-weight: 700; color: #64748B; letter-spacing: 2px;")

        doc_cert_title = QLabel("CERTIFICATE OF DEPOSIT")
        doc_cert_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        doc_cert_title.setStyleSheet("font-size: 22px; font-weight: 800; color: #17365D; letter-spacing: 1px;")

        doc_seal_note = QLabel("GUARANTEED TIME DEPOSIT OBLIGATION • FULL FAITH & INSTITUTIONAL BACKING")
        doc_seal_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        doc_seal_note.setStyleSheet("font-size: 10px; font-weight: 600; color: #94A3B8; letter-spacing: 1px;")

        doc_header.addWidget(doc_bank_title)
        doc_header.addWidget(doc_cert_title)
        doc_header.addWidget(doc_seal_note)
        cert_doc_layout.addLayout(doc_header)

        # Certificate Divider
        c_div = QFrame()
        c_div.setFrameShape(QFrame.Shape.HLine)
        c_div.setStyleSheet("color: #CBD5E1; background-color: #CBD5E1; height: 1px;")
        cert_doc_layout.addWidget(c_div)

        # Document Fields Grid
        self.doc_grid = QGridLayout()
        self.doc_grid.setVerticalSpacing(12)
        self.doc_grid.setHorizontalSpacing(24)

        def _doc_field(row: int, col: int, lbl_text: str, val_text: str, is_large: bool = False, is_mono: bool = False):
            box = QVBoxLayout()
            box.setSpacing(2)
            lbl = QLabel(lbl_text)
            lbl.setStyleSheet("font-size: 11px; color: #64748B; font-weight: 600; text-transform: uppercase;")
            val = QLabel(val_text)
            mono = "font-family: 'Consolas', monospace;" if is_mono else ""
            if is_large:
                val.setStyleSheet(f"font-size: 18px; font-weight: 800; color: #17365D; {mono}")
            else:
                val.setStyleSheet(f"font-size: 13px; font-weight: 700; color: #172033; {mono}")
            box.addWidget(lbl)
            box.addWidget(val)
            self.doc_grid.addLayout(box, row, col)
            return val

        self.doc_val_cert_num = _doc_field(0, 0, "Certificate Number", "—", is_mono=True)
        self.doc_val_status = _doc_field(0, 1, "Status", "—")
        self.doc_val_account = _doc_field(0, 2, "Funding Account", "—", is_mono=True)

        self.doc_val_principal = _doc_field(1, 0, "Principal Locked Sum", "—", is_large=True, is_mono=True)
        self.doc_val_apy = _doc_field(1, 1, "Guaranteed Annual APY", "—", is_large=True, is_mono=True)
        self.doc_val_maturity_amount = _doc_field(1, 2, "Projected Maturity Payout", "—", is_large=True, is_mono=True)

        self.doc_val_tenor = _doc_field(2, 0, "Tenor Period", "—")
        self.doc_val_issue_date = _doc_field(2, 1, "Issue Date", "—")
        self.doc_val_maturity_date = _doc_field(2, 2, "Maturity Date", "—")

        self.doc_val_accrued = _doc_field(3, 0, "Accrued Interest to Date", "—", is_mono=True)
        self.doc_val_payout_freq = _doc_field(3, 1, "Payout Frequency", "—")
        self.doc_val_rollover = _doc_field(3, 2, "Rollover Instruction", "—")

        cert_doc_layout.addLayout(self.doc_grid)

        # Legal Guarantee Bar
        guarantee_box = QFrame()
        guarantee_box.setStyleSheet("background-color: #EFF6FF; border: 1px solid #BFDBFE; border-radius: 4px; padding: 10px;")
        g_layout = QHBoxLayout(guarantee_box)
        g_layout.setContentsMargins(8, 8, 8, 8)
        self.doc_legal_text = QLabel(
            "This certifies that the indicated funds are held in fixed-term custody by NovaBank National Association. "
            "Guaranteed return is computed under statutory compound schedules. Premature redemption is subject to regulatory forfeiture."
        )
        self.doc_legal_text.setStyleSheet("font-size: 11px; color: #1E40AF; line-height: 1.4;")
        self.doc_legal_text.setWordWrap(True)
        g_layout.addWidget(self.doc_legal_text)
        cert_doc_layout.addWidget(guarantee_box)

        layout.addWidget(self.cert_frame)

        # Accrual Schedule Table Header
        schedule_hdr = QHBoxLayout()
        schedule_title = QLabel("Amortized Yield Accrual Schedule")
        schedule_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #17365D;")
        self.btn_export_schedule = QPushButton("Export Schedule CSV")
        self.btn_export_schedule.setFixedHeight(30)
        self.btn_export_schedule.setStyleSheet(self._btn_tertiary_style())
        self.btn_export_schedule.clicked.connect(self._on_export_schedule_csv)

        schedule_hdr.addWidget(schedule_title)
        schedule_hdr.addStretch()
        schedule_hdr.addWidget(self.btn_export_schedule)
        layout.addLayout(schedule_hdr)

        self.schedule_table = QTableWidget()
        self.schedule_table.setColumnCount(5)
        self.schedule_table.setHorizontalHeaderLabels([
            "Milestone Month", "Accrual Date", "Periodic Interest", "Cumulative Yield", "Projected Balance"
        ])
        self.schedule_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.schedule_table.verticalHeader().setVisible(False)
        self.schedule_table.setStyleSheet(self._table_style())
        self.schedule_table.setMinimumHeight(260)
        layout.addWidget(self.schedule_table)

        scroll.setWidget(container)
        tab_layout = QVBoxLayout(self.certificate_tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)

    # -------------------------------------------------------------------------
    # Signals & ViewModel Connections
    # -------------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self.vm.account_found.connect(self._on_account_found)
        self.vm.account_lookup_failed.connect(self._on_account_lookup_failed)

        self.vm.quote_calculated.connect(self._on_quote_calculated)
        self.vm.quote_failed.connect(self._on_quote_failed)

        self.vm.cd_opened.connect(self._on_cd_opened)
        self.vm.cd_open_failed.connect(self._on_cd_open_failed)
        self.vm.submitting_changed.connect(self._on_submitting_changed)

        self.vm.cds_loaded.connect(self._on_cds_loaded)
        self.vm.cds_load_failed.connect(self._on_cds_load_failed)

        self.vm.redemption_preview_ready.connect(self._on_redemption_preview_ready)
        self.vm.redemption_completed.connect(self._on_redemption_completed)
        self.vm.redemption_failed.connect(self._on_redemption_failed)

        self.vm.certificate_loaded.connect(self._on_certificate_loaded)
        self.vm.csv_exported.connect(self._on_csv_exported)
        self.vm.csv_export_failed.connect(self._on_csv_export_failed)

    # -------------------------------------------------------------------------
    # Event Handlers & Business Logic
    # -------------------------------------------------------------------------

    def _set_principal(self, amount_str: str) -> None:
        self.principal_input.setText(amount_str)

    def _select_tenor_preset(self, months: int, apy: Decimal, button: QPushButton) -> None:
        self._selected_tenor_months = months
        self._selected_apy = apy

        for btn in self._tenor_buttons:
            is_active = (btn is button)
            btn.setChecked(is_active)
            btn.setStyleSheet(self._tenor_pill_style(is_active))

        self.tenor_spin.blockSignals(True)
        self.tenor_spin.setValue(months)
        self.tenor_spin.blockSignals(False)

        self.apy_input.blockSignals(True)
        self.apy_input.setText(str(apy))
        self.apy_input.blockSignals(False)

        self._recalculate_quote()

    def _on_custom_tenor_changed(self, val: int) -> None:
        self._selected_tenor_months = val
        for btn in self._tenor_buttons:
            btn.setChecked(False)
            btn.setStyleSheet(self._tenor_pill_style(False))
        self._recalculate_quote()

    def _on_custom_apy_changed(self, text: str) -> None:
        try:
            self._selected_apy = Decimal(text.strip().replace("%", ""))
        except (InvalidOperation, ValueError):
            return
        for btn in self._tenor_buttons:
            btn.setChecked(False)
            btn.setStyleSheet(self._tenor_pill_style(False))
        self._recalculate_quote()

    def _on_lookup_clicked(self) -> None:
        acc_num = self.funding_acc_input.text().strip()
        if not acc_num:
            self.account_status_label.setText("Please enter an account number.")
            self.account_status_label.setStyleSheet("font-size: 12px; color: #DC2626;")
            return
        self.account_status_label.setText("Verifying account status and balance...")
        self.account_status_label.setStyleSheet("font-size: 12px; color: #2563EB;")
        self.vm.lookup_account(acc_num)

    def _on_account_found(self, account: AccountDTO) -> None:
        self.account_status_label.setText(
            f"Verified: {account.holder_name} — Available Balance: {account.formatted_balance}"
        )
        self.account_status_label.setStyleSheet("font-size: 12px; color: #15803D; font-weight: 600;")

    def _on_account_lookup_failed(self, msg: str) -> None:
        self.account_status_label.setText(f"Lookup Failed: {msg}")
        self.account_status_label.setStyleSheet("font-size: 12px; color: #DC2626; font-weight: 600;")

    def _recalculate_quote(self) -> None:
        p_str = self.principal_input.text().strip()
        apy_str = self.apy_input.text().strip()
        tenor = self.tenor_spin.value()
        freq = self.freq_combo.currentText().upper().replace(" ", "_")

        self.vm.calculate_quote(
            principal_str=p_str,
            apy_str=apy_str,
            tenor_months=tenor,
            payout_frequency=freq,
        )

    def _on_quote_calculated(self, quote: CDSimulationResponseDTO) -> None:
        self.hero_payout_val.setText(quote.formatted_projected_maturity_amount)
        self.hero_principal_val.setText(quote.formatted_principal)
        self.hero_interest_val.setText(f"+{quote.formatted_total_interest}")
        self.hero_apy_val.setText(f"{quote.apy_percentage:.2f}% APY")
        self.hero_maturity_val.setText(f"{quote.tenor_months} Months ({quote.maturity_date})")

        penalty_mos = 3 if quote.tenor_months <= 12 else 6
        self.hero_penalty_lbl.setText(
            f"Regulatory Notice: Early withdrawal incurs {penalty_mos} months simple interest forfeiture under federal rules."
        )

        # Update projection table
        self.projection_table.setRowCount(len(quote.accrual_milestones))
        for row, ms in enumerate(quote.accrual_milestones):
            m_item = QTableWidgetItem(f"Month {ms.milestone_month}")
            d_item = QTableWidgetItem(ms.accrual_date)
            i_item = QTableWidgetItem(ms.formatted_periodic_interest)
            c_item = QTableWidgetItem(ms.formatted_cumulative_interest)
            b_item = QTableWidgetItem(ms.formatted_balance_after)

            for it in (m_item, d_item, i_item, c_item, b_item):
                it.setFont(QFont("Consolas", 10))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            i_item.setForeground(QColor("#15803D"))
            c_item.setForeground(QColor("#15803D"))
            b_item.setForeground(QColor("#17365D"))

            self.projection_table.setItem(row, 0, m_item)
            self.projection_table.setItem(row, 1, d_item)
            self.projection_table.setItem(row, 2, i_item)
            self.projection_table.setItem(row, 3, c_item)
            self.projection_table.setItem(row, 4, b_item)

    def _on_quote_failed(self, msg: str) -> None:
        self.hero_payout_val.setText("—")
        self.hero_interest_val.setText("—")

    def _on_issue_cd_clicked(self) -> None:
        acc_num = self.funding_acc_input.text().strip().replace("-", "").replace(" ", "")
        if len(acc_num) != 12:
            QMessageBox.warning(self, "Invalid Account", "Please enter a valid 12-digit funding account number.")
            return

        try:
            principal = Decimal(self.principal_input.text().strip().replace("$", "").replace(",", ""))
            apy = Decimal(self.apy_input.text().strip().replace("%", ""))
            tenor = self.tenor_spin.value()
        except (InvalidOperation, ValueError):
            QMessageBox.warning(self, "Invalid Parameters", "Please enter valid numeric principal and APY rates.")
            return

        if principal < Decimal("500.00"):
            QMessageBox.warning(self, "Minimum Principal Required", "Minimum principal for a Certificate of Deposit is $500.00.")
            return

        freq = self.freq_combo.currentText().upper().replace(" ", "_")
        rollover_txt = self.roll_combo.currentText()
        if "Roll Principal & Interest" in rollover_txt:
            roll = "PRINCIPAL_AND_INTEREST"
        elif "Roll Principal Only" in rollover_txt:
            roll = "PRINCIPAL_ONLY"
        else:
            roll = "PAYOUT_AND_CLOSE"

        self.vm.open_cd(
            account_number=acc_num,
            principal=principal,
            apy=apy,
            tenor_months=tenor,
            payout_frequency=freq,
            rollover_option=roll,
        )

    def _on_submitting_changed(self, submitting: bool) -> None:
        self.btn_issue_cd.setEnabled(not submitting)
        if submitting:
            self.btn_issue_cd.setText("Processing CD Lockup...")
        else:
            self.btn_issue_cd.setText("Lock Funds & Issue Certificate of Deposit")

    def _on_cd_opened(self, cd: CertificateOfDepositDTO) -> None:
        receipt = CDIssuanceReceiptDialog(cd, self)
        receipt.exec()

        # Refresh portfolio and switch to portfolio tab
        self.refresh_portfolio()
        self.tab_widget.setCurrentIndex(1)

    def _on_cd_open_failed(self, msg: str) -> None:
        QMessageBox.critical(self, "Issuance Failed", f"Could not issue Certificate of Deposit:\n\n{msg}")

    def refresh_portfolio(self) -> None:
        acc_num = self.filter_acc_input.text().strip() if hasattr(self, "filter_acc_input") else None
        status = self.filter_status_combo.currentText() if hasattr(self, "filter_status_combo") else None
        self.vm.load_cds(account_number=acc_num, status=status)

    def _on_filter_changed(self) -> None:
        self.refresh_portfolio()

    def _on_cds_loaded(self, cds: list[CertificateOfDepositDTO], total_count: int) -> None:
        # Update KPI Summary Cards
        active_cds = [c for c in cds if c.status == "ACTIVE"]
        self.kpi_active_count.setText(f"{len(active_cds)} Active")

        total_principal = sum((c.principal for c in active_cds), Decimal("0.00"))
        self.kpi_total_principal.setText(f"${total_principal:,.2f}")

        if active_cds and total_principal > Decimal("0.00"):
            weighted_apy = sum(c.principal * c.apy_percentage for c in active_cds) / total_principal
            self.kpi_avg_apy.setText(f"{weighted_apy:.2f}%")
        else:
            self.kpi_avg_apy.setText("0.00%")

        total_projected = sum((c.projected_maturity_amount - c.principal for c in active_cds), Decimal("0.00"))
        self.kpi_total_projected.setText(f"+${total_projected:,.2f}")

        # Update Portfolio Table
        self.portfolio_table.setRowCount(len(cds))
        for row, cd in enumerate(cds):
            c_num = QTableWidgetItem(cd.certificate_number)
            c_acc = QTableWidgetItem(cd.account_number)
            c_p = QTableWidgetItem(cd.formatted_principal)
            c_apy = QTableWidgetItem(cd.formatted_apy)
            c_tenor = QTableWidgetItem(f"{cd.tenor_months}m")
            c_issue = QTableWidgetItem(cd.issue_date)
            c_maturity = QTableWidgetItem(cd.maturity_date)
            c_accrued = QTableWidgetItem(cd.formatted_accrued_interest)

            status_badge = QLabel(cd.status)
            status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            if cd.status == "ACTIVE":
                status_badge.setStyleSheet(
                    "background-color: #DCFCE7; color: #15803D; border-radius: 3px; font-weight: 700; font-size: 11px; padding: 2px 6px;"
                )
            elif cd.status == "MATURED":
                status_badge.setStyleSheet(
                    "background-color: #EFF6FF; color: #2563EB; border-radius: 3px; font-weight: 700; font-size: 11px; padding: 2px 6px;"
                )
            elif cd.status == "PREMATURELY_CLOSED":
                status_badge.setStyleSheet(
                    "background-color: #FEF2F2; color: #DC2626; border-radius: 3px; font-weight: 700; font-size: 11px; padding: 2px 6px;"
                )
            else:
                status_badge.setStyleSheet(
                    "background-color: #F1F5F9; color: #64748B; border-radius: 3px; font-weight: 700; font-size: 11px; padding: 2px 6px;"
                )

            for it in (c_num, c_acc, c_p, c_apy, c_tenor, c_issue, c_maturity, c_accrued):
                it.setFont(QFont("Consolas", 10))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            c_p.setForeground(QColor("#17365D"))
            c_accrued.setForeground(QColor("#15803D"))

            self.portfolio_table.setItem(row, 0, c_num)
            self.portfolio_table.setItem(row, 1, c_acc)
            self.portfolio_table.setItem(row, 2, c_p)
            self.portfolio_table.setItem(row, 3, c_apy)
            self.portfolio_table.setItem(row, 4, c_tenor)
            self.portfolio_table.setItem(row, 5, c_issue)
            self.portfolio_table.setItem(row, 6, c_maturity)
            self.portfolio_table.setItem(row, 7, c_accrued)
            self.portfolio_table.setCellWidget(row, 8, status_badge)

            # Actions Cell Widget
            actions_widget = QWidget()
            a_layout = QHBoxLayout(actions_widget)
            a_layout.setContentsMargins(4, 2, 4, 2)
            a_layout.setSpacing(6)

            btn_view = QPushButton("Details")
            btn_view.setStyleSheet(self._btn_tertiary_style())
            btn_view.clicked.connect(lambda _, c=cd: self._inspect_cd(c))
            a_layout.addWidget(btn_view)

            if cd.status == "ACTIVE":
                btn_break = QPushButton("Break CD")
                btn_break.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #FEF2F2;
                        color: #DC2626;
                        border: 1px solid #FECACA;
                        border-radius: 4px;
                        padding: 3px 8px;
                        font-size: 11px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background-color: #FEE2E2;
                    }
                    """
                )
                btn_break.clicked.connect(lambda _, cid=cd.id: self._on_break_cd_clicked(cid))
                a_layout.addWidget(btn_break)

                btn_redeem = QPushButton("Maturity Redeem")
                btn_redeem.setStyleSheet(
                    """
                    QPushButton {
                        background-color: #F0FDF4;
                        color: #16A34A;
                        border: 1px solid #BBF7D0;
                        border-radius: 4px;
                        padding: 3px 8px;
                        font-size: 11px;
                        font-weight: 600;
                    }
                    QPushButton:hover {
                        background-color: #DCFCE7;
                    }
                    """
                )
                btn_redeem.clicked.connect(lambda _, cid=cd.id: self._on_redeem_at_maturity_clicked(cid))
                a_layout.addWidget(btn_redeem)

            self.portfolio_table.setCellWidget(row, 9, actions_widget)

    def _on_cds_load_failed(self, msg: str) -> None:
        QMessageBox.warning(self, "Portfolio Load Failed", f"Could not load Certificates of Deposit:\n\n{msg}")

    def _on_portfolio_cell_double_clicked(self, row: int, col: int) -> None:
        if row < len(self.vm.current_cds):
            self._inspect_cd(self.vm.current_cds[row])

    def _inspect_cd(self, cd: CertificateOfDepositDTO) -> None:
        self.cert_search_input.setText(cd.certificate_number)
        self._on_certificate_loaded(cd)
        self.tab_widget.setCurrentIndex(2)

    def _on_break_cd_clicked(self, cd_id: str) -> None:
        self._pending_break_cd_id = cd_id
        self.vm.preview_early_redemption(cd_id)

    def _on_redemption_preview_ready(self, preview: EarlyRedemptionPreviewDTO) -> None:
        dialog = CDEarlyRedemptionDialog(preview, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if self._pending_break_cd_id:
                self.vm.redeem_cd(self._pending_break_cd_id, is_premature=True)
        self._pending_break_cd_id = None

    def _on_redeem_at_maturity_clicked(self, cd_id: str) -> None:
        confirm = QMessageBox.question(
            self,
            "Confirm Maturity Redemption",
            "Are you sure you want to process this Certificate of Deposit at maturity payout?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            self.vm.redeem_cd(cd_id, is_premature=False)

    def _on_redemption_completed(self, result: RedemptionResultDTO) -> None:
        QMessageBox.information(
            self,
            "Redemption Processed",
            f"Certificate {result.certificate_number} successfully redeemed!\n\n"
            f"Net Payout Credited: {result.formatted_net_payout}\n"
            f"New Account Balance: {result.formatted_new_account_balance}",
        )
        self.refresh_portfolio()

    def _on_redemption_failed(self, msg: str) -> None:
        QMessageBox.critical(self, "Redemption Failed", f"Could not process CD redemption:\n\n{msg}")

    # -------------------------------------------------------------------------
    # TAB 3: Certificate Details & Accrual Schedule Handlers
    # -------------------------------------------------------------------------

    def _on_search_certificate_clicked(self) -> None:
        c_num = self.cert_search_input.text().strip()
        if not c_num:
            return

        # Check in loaded list or load
        matching = [c for c in self.vm.current_cds if c.certificate_number.upper() == c_num.upper()]
        if matching:
            self._on_certificate_loaded(matching[0])
        else:
            self.vm.load_certificate(c_num)

    def _on_certificate_loaded(self, cd: CertificateOfDepositDTO) -> None:
        self.vm.selected_cd = cd
        self.doc_val_cert_num.setText(cd.certificate_number)
        self.doc_val_status.setText(cd.status)
        self.doc_val_account.setText(cd.account_number)

        self.doc_val_principal.setText(cd.formatted_principal)
        self.doc_val_apy.setText(cd.formatted_apy)
        self.doc_val_maturity_amount.setText(cd.formatted_maturity_amount)

        self.doc_val_tenor.setText(f"{cd.tenor_months} Months")
        self.doc_val_issue_date.setText(cd.issue_date)
        self.doc_val_maturity_date.setText(cd.maturity_date)

        self.doc_val_accrued.setText(cd.formatted_accrued_interest)
        self.doc_val_payout_freq.setText(cd.payout_frequency.replace("_", " ").title())
        self.doc_val_rollover.setText(cd.rollover_option.replace("_", " ").title())

        # Populate schedule table
        self.schedule_table.setRowCount(len(cd.accrual_milestones))
        for row, ms in enumerate(cd.accrual_milestones):
            m0 = QTableWidgetItem(f"Month {ms.milestone_month}")
            m1 = QTableWidgetItem(ms.accrual_date)
            m2 = QTableWidgetItem(ms.formatted_periodic_interest)
            m3 = QTableWidgetItem(ms.formatted_cumulative_interest)
            m4 = QTableWidgetItem(ms.formatted_balance_after)

            for it in (m0, m1, m2, m3, m4):
                it.setFont(QFont("Consolas", 10))
                it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            m2.setForeground(QColor("#15803D"))
            m3.setForeground(QColor("#15803D"))
            m4.setForeground(QColor("#17365D"))

            self.schedule_table.setItem(row, 0, m0)
            self.schedule_table.setItem(row, 1, m1)
            self.schedule_table.setItem(row, 2, m2)
            self.schedule_table.setItem(row, 3, m3)
            self.schedule_table.setItem(row, 4, m4)

    def _on_export_portfolio_csv(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export CD Vault Portfolio",
            "cd_vault_portfolio.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not filename:
            return
        self.vm.export_cds_csv(destination_path=filename)

    def _on_export_schedule_csv(self) -> None:
        if not self.vm.selected_cd:
            QMessageBox.information(self, "No Certificate Selected", "Please select or load a Certificate first.")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export CD Accrual Schedule",
            f"cd_schedule_{self.vm.selected_cd.certificate_number}.csv",
            "CSV Files (*.csv);;All Files (*)",
        )
        if not filename:
            return

        # Export schedule directly
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write("Milestone Month,Accrual Date,Periodic Interest,Cumulative Yield,Projected Balance\n")
                for ms in self.vm.selected_cd.accrual_milestones:
                    f.write(
                        f"{ms.milestone_month},{ms.accrual_date},{ms.periodic_interest},{ms.cumulative_interest},{ms.balance_after}\n"
                    )
            QMessageBox.information(self, "Schedule Exported", f"Accrual schedule exported to:\n{filename}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", f"Could not write schedule CSV:\n{exc}")

    def _on_csv_exported(self, path_or_content: str) -> None:
        QMessageBox.information(self, "Export Successful", f"CD Vault data exported successfully:\n\n{path_or_content}")

    def _on_csv_export_failed(self, msg: str) -> None:
        QMessageBox.warning(self, "Export Failed", f"Could not export CSV:\n\n{msg}")

    # -------------------------------------------------------------------------
    # Styling Helpers
    # -------------------------------------------------------------------------

    def _group_box_style(self) -> str:
        return """
            QGroupBox {
                font-size: 13px;
                font-weight: 700;
                color: #17365D;
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                border-radius: 6px;
                margin-top: 8px;
                padding-top: 14px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
            }
        """

    def _label_style(self) -> str:
        return "font-size: 12px; font-weight: 600; color: #172033;"

    def _input_mono_style(self) -> str:
        return """
            QLineEdit, QSpinBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 13px;
                font-family: 'Consolas', monospace;
                color: #172033;
            }
            QLineEdit:focus, QSpinBox:focus {
                border-color: #2563EB;
            }
        """

    def _combo_style(self) -> str:
        return """
            QComboBox {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 10px;
                font-size: 13px;
                color: #172033;
            }
            QComboBox:focus {
                border-color: #2563EB;
            }
        """

    def _pill_style(self, active: bool = False) -> str:
        if active:
            return """
                QPushButton {
                    background-color: #17365D;
                    color: #FFFFFF;
                    border: 1px solid #17365D;
                    border-radius: 13px;
                    padding: 2px 10px;
                    font-size: 11px;
                    font-weight: 700;
                }
            """
        return """
            QPushButton {
                background-color: #F8FAFC;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 13px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                color: #172033;
            }
        """

    def _tenor_pill_style(self, active: bool = False) -> str:
        if active:
            return """
                QPushButton {
                    background-color: #17365D;
                    color: #FFFFFF;
                    border: 1px solid #17365D;
                    border-radius: 6px;
                    padding: 4px 8px;
                    font-size: 11px;
                    font-weight: 700;
                }
            """
        return """
            QPushButton {
                background-color: #F8FAFC;
                color: #334155;
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                padding: 4px 8px;
                font-size: 11px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
                border-color: #94A3B8;
            }
        """

    def _btn_secondary_style(self) -> str:
        return """
            QPushButton {
                background-color: #F8FAFC;
                color: #17365D;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
            }
        """

    def _btn_tertiary_style(self) -> str:
        return """
            QPushButton {
                background-color: #F1F5F9;
                color: #475569;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #E2E8F0;
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
