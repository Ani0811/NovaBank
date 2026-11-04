"""PySide6 AI Assistant Panel View.

Integrates local LM Studio conversational banking intelligence into NovaBank:
- Real-time connection status indicator pill.
- Interactive conversational chat history with markdown/HTML rendering.
- Quick action dispatch buttons (Statement Summary, Large Expenses, Security Flag Explanations).
- Asynchronous task execution without UI stutter.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from novabank.ui.resources.icons import get_icon
from novabank.ui.viewmodels.ai_assistant_viewmodel import AIAssistantViewModel

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.infrastructure.ai.lm_studio_client import LMStudioClient
    from novabank.ui.workers.task_runner import TaskRunner


class AIAssistantPanel(QWidget):
    """Interactive conversational desktop panel for local private banking AI."""

    def __init__(
        self,
        viewmodel: Optional[AIAssistantViewModel] = None,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        lm_client: Optional[LMStudioClient] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AIAssistantPanelView")

        if viewmodel:
            self.vm = viewmodel
        else:
            self.vm = AIAssistantViewModel(
                banking_service=banking_service,
                task_runner=task_runner,
                lm_client=lm_client,
                parent=self,
            )

        self._build_ui()
        self._bind_viewmodel()

        # Initial check
        self.vm.check_connection()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(16)

        # 1. Header & Connection Status Card
        header_card = QFrame()
        header_card.setObjectName("AIHeaderCard")
        header_card.setProperty("class", "CardFrame")
        header_card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(18, 14, 18, 14)
        header_layout.setSpacing(14)

        info_box = QVBoxLayout()
        info_box.setSpacing(3)
        title_lbl = QLabel("Financial Intelligence Assistant")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #172033;")
        desc_lbl = QLabel(
            "Private, client-side financial analytics connecting strictly to local loopback (LM Studio)."
        )
        desc_lbl.setStyleSheet("font-size: 13px; color: #64748B;")
        info_box.addWidget(title_lbl)
        info_box.addWidget(desc_lbl)

        header_layout.addLayout(info_box, stretch=1)

        # Status badge & refresh button
        self.badge_lbl = QLabel("Checking AI Status...")
        self.badge_lbl.setObjectName("AIBadgeLabel")
        self.badge_lbl.setProperty("class", "StatusIndicatorPill")
        self.badge_lbl.setProperty("status", "warning")
        self.badge_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.badge_lbl.setMinimumWidth(220)
        self.badge_lbl.setStyleSheet(
            "QLabel { font-weight: 600; padding: 6px 14px; border-radius: 12px; font-size: 12px; border: 1px solid #E2E8F0; }"
            "QLabel[status='success'] { background-color: #ECFDF5; color: #15803D; border-color: #A7F3D0; }"
            "QLabel[status='warning'] { background-color: #FFFBEB; color: #D97706; border-color: #FDE68A; }"
        )

        self.btn_refresh_status = QPushButton("Check Status")
        self.btn_refresh_status.setIcon(get_icon("refresh", "#475569"))
        self.btn_refresh_status.setObjectName("BtnRefreshAIStatus")
        self.btn_refresh_status.setProperty("class", "SecondaryButton")
        self.btn_refresh_status.setStyleSheet(
            "QPushButton { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 12px; font-size: 12px; color: #334155; font-weight: 500; }"
            "QPushButton:hover { background-color: #F8FAFC; border-color: #94A3B8; }"
        )
        self.btn_refresh_status.clicked.connect(self.vm.check_connection)

        header_layout.addWidget(self.badge_lbl)
        header_layout.addWidget(self.btn_refresh_status)
        root_layout.addWidget(header_card)

        # 2. Context & Quick Action Controls Bar
        controls_card = QFrame()
        controls_card.setProperty("class", "CardFrame")
        controls_card.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        controls_layout = QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(18, 14, 18, 14)
        controls_layout.setSpacing(12)

        # Account Context Bar
        acc_box = QHBoxLayout()
        acc_box.setSpacing(10)
        acc_lbl = QLabel("Target Account:")
        acc_lbl.setStyleSheet("font-weight: 600; color: #334155; font-size: 13px;")

        self.account_input = QLineEdit()
        self.account_input.setObjectName("AIAccountContextInput")
        self.account_input.setPlaceholderText("Enter 12-digit Account Number (e.g. 100000000001)")
        self.account_input.setMaxLength(14)
        self.account_input.setFont(QFont("Consolas", 10))
        self.account_input.setStyleSheet(
            "QLineEdit { padding: 7px 12px; background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; color: #172033; font-size: 13px; }"
            "QLineEdit:focus { border: 1px solid #2563EB; }"
        )
        self.account_input.textChanged.connect(self.vm.set_active_account)

        acc_box.addWidget(acc_lbl)
        acc_box.addWidget(self.account_input, stretch=1)
        controls_layout.addLayout(acc_box)

        # Quick Actions Row
        quick_actions_box = QHBoxLayout()
        quick_actions_box.setSpacing(8)

        quick_lbl = QLabel("Quick Prompts:")
        quick_lbl.setStyleSheet(
            "font-size: 11px; font-weight: 700; color: #64748B; text-transform: uppercase; letter-spacing: 0.5px;"
        )
        quick_actions_box.addWidget(quick_lbl)

        btn_style = (
            "QPushButton { background-color: #FFFFFF; border: 1px solid #CBD5E1; border-radius: 6px; padding: 6px 12px; font-size: 12px; color: #334155; font-weight: 500; }"
            "QPushButton:hover { background-color: #F8FAFC; border-color: #94A3B8; }"
            "QPushButton:disabled { background-color: #F1F5F9; color: #94A3B8; border-color: #E2E8F0; }"
        )

        self.btn_summarize = QPushButton("Summarize Statement")
        self.btn_summarize.setIcon(get_icon("file_text", "#475569"))
        self.btn_summarize.setObjectName("BtnQuickSummarize")
        self.btn_summarize.setProperty("class", "SecondaryButton")
        self.btn_summarize.setStyleSheet(btn_style)
        self.btn_summarize.clicked.connect(lambda: self.vm.quick_action_summarize())

        self.btn_large_expenses = QPushButton("Find Large Expenses")
        self.btn_large_expenses.setIcon(get_icon("dollar_sign", "#475569"))
        self.btn_large_expenses.setObjectName("BtnQuickLargeExpenses")
        self.btn_large_expenses.setProperty("class", "SecondaryButton")
        self.btn_large_expenses.setStyleSheet(btn_style)
        self.btn_large_expenses.clicked.connect(lambda: self.vm.quick_action_find_large_expenses())

        self.btn_explain_flags = QPushButton("Explain Active Flags")
        self.btn_explain_flags.setIcon(get_icon("alert_triangle", "#475569"))
        self.btn_explain_flags.setObjectName("BtnQuickExplainFlags")
        self.btn_explain_flags.setProperty("class", "SecondaryButton")
        self.btn_explain_flags.setStyleSheet(btn_style)
        self.btn_explain_flags.clicked.connect(lambda: self.vm.quick_action_explain_flags())

        quick_actions_box.addWidget(self.btn_summarize)
        quick_actions_box.addWidget(self.btn_large_expenses)
        quick_actions_box.addWidget(self.btn_explain_flags)
        quick_actions_box.addStretch()

        self.btn_clear_chat = QPushButton("Clear Chat")
        self.btn_clear_chat.setObjectName("BtnClearChat")
        self.btn_clear_chat.setProperty("class", "SecondaryButton")
        self.btn_clear_chat.setStyleSheet(
            "QPushButton { background: transparent; border: none; padding: 4px 8px; font-size: 12px; color: #64748B; font-weight: 500; }"
            "QPushButton:hover { color: #DC2626; text-decoration: underline; }"
        )
        self.btn_clear_chat.clicked.connect(self._clear_chat)
        quick_actions_box.addWidget(self.btn_clear_chat)

        controls_layout.addLayout(quick_actions_box)
        root_layout.addWidget(controls_card)

        # 3. Conversational Chat Log Display
        self.chat_display = QTextEdit()
        self.chat_display.setObjectName("AIChatDisplay")
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(
            "QTextEdit { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; "
            "padding: 16px; font-size: 13px; line-height: 1.5; color: #172033; }"
        )
        root_layout.addWidget(self.chat_display, stretch=1)

        # 4. Input Prompt & Submit Bar
        input_container = QFrame()
        input_container.setProperty("class", "CardFrame")
        input_container.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #E2E8F0; border-radius: 8px; }"
        )
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(14, 10, 14, 10)
        input_layout.setSpacing(10)

        self.prompt_input = QLineEdit()
        self.prompt_input.setObjectName("AIPromptInput")
        self.prompt_input.setPlaceholderText(
            "Ask a question (e.g. 'Show deposits over 5,000 from last month')..."
        )
        self.prompt_input.setStyleSheet(
            "QLineEdit { padding: 9px 14px; background-color: #F8FAFC; border: 1px solid #CBD5E1; border-radius: 6px; font-size: 13px; color: #172033; }"
            "QLineEdit:focus { background-color: #FFFFFF; border-color: #2563EB; }"
        )
        self.prompt_input.returnPressed.connect(self._on_send_clicked)

        self.btn_send = QPushButton("Send")
        self.btn_send.setObjectName("BtnSendAIPrompt")
        self.btn_send.setProperty("class", "PrimaryButton")
        self.btn_send.setStyleSheet(
            "QPushButton { background-color: #2563EB; border: none; border-radius: 6px; padding: 9px 20px; color: #FFFFFF; font-weight: 600; font-size: 13px; }"
            "QPushButton:hover { background-color: #1D4ED8; }"
            "QPushButton:disabled { background-color: #94A3B8; }"
        )
        self.btn_send.setMinimumWidth(90)
        self.btn_send.clicked.connect(self._on_send_clicked)

        input_layout.addWidget(self.prompt_input, stretch=1)
        input_layout.addWidget(self.btn_send)

        root_layout.addWidget(input_container)

        # Initial Welcome Message
        self._append_message(
            "assistant",
            "Welcome to **NovaBank AI Assistant**.\n"
            "All financial queries are processed locally with strict PII scrubbing. "
            "Enter an account number above to query transactions, generate statement summaries, or inspect security flags.",
        )

    def _bind_viewmodel(self) -> None:
        self.vm.connection_status_changed.connect(self._on_connection_status_changed)
        self.vm.message_received.connect(self._append_message)
        self.vm.loading_changed.connect(self._on_loading_changed)

    def _on_connection_status_changed(self, is_connected: bool, status_text: str) -> None:
        self.badge_lbl.setText(f"{'●' if is_connected else '○'} {status_text}")
        status_prop = "success" if is_connected else "warning"
        self.badge_lbl.setProperty("status", status_prop)
        self.badge_lbl.style().unpolish(self.badge_lbl)
        self.badge_lbl.style().polish(self.badge_lbl)

    def _on_loading_changed(self, is_loading: bool) -> None:
        self.btn_send.setEnabled(not is_loading)
        self.btn_summarize.setEnabled(not is_loading)
        self.btn_large_expenses.setEnabled(not is_loading)
        self.btn_explain_flags.setEnabled(not is_loading)
        self.prompt_input.setEnabled(not is_loading)

        if is_loading:
            self.btn_send.setText("Processing...")
        else:
            self.btn_send.setText("Send")

    def _on_send_clicked(self) -> None:
        text = self.prompt_input.text().strip()
        if text:
            self.prompt_input.clear()
            self.vm.send_user_message(text)

    def _clear_chat(self) -> None:
        self.chat_display.clear()
        self._append_message(
            "assistant",
            "Chat log cleared. Ready for your next query.",
        )

    def _append_message(self, role: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")

        # Convert simple markdown / newlines to clean HTML
        escaped = html.escape(message)
        # Bold
        formatted = escaped.replace("**", "<b>", 1)
        while "**" in formatted:
            formatted = formatted.replace("**", "</b>", 1)
            formatted = formatted.replace("**", "<b>", 1)
        # Code backticks
        formatted = formatted.replace("`", "<code>", 1)
        while "`" in formatted:
            formatted = formatted.replace("`", "</code>", 1)
            formatted = formatted.replace("`", "<code>", 1)
        # Newlines
        formatted = formatted.replace("\n", "<br>")

        if role == "user":
            block = (
                f"<div style='margin-bottom: 14px; text-align: right;'>"
                f"  <span style='font-size: 11px; color: #94A3B8; margin-right: 6px;'>{timestamp}</span>"
                f"  <span style='font-weight: 600; color: #1E3A8A; font-size: 12px;'>Teller</span><br>"
                f"  <div style='display: inline-block; background-color: #2563EB; color: #FFFFFF; "
                f"              padding: 10px 16px; border-radius: 8px; margin-top: 4px; text-align: left; max-width: 80%; font-size: 13px;'>"
                f"    {formatted}"
                f"  </div>"
                f"</div>"
            )
        else:
            block = (
                f"<div style='margin-bottom: 16px; text-align: left;'>"
                f"  <span style='font-weight: 700; color: #17365D; font-size: 12px;'>NovaBank Assistant</span>"
                f"  <span style='font-size: 11px; color: #94A3B8; margin-left: 6px;'>{timestamp}</span><br>"
                f"  <div style='background-color: #F8FAFC; color: #172033; padding: 12px 16px; "
                f"              border: 1px solid #E2E8F0; border-radius: 8px; margin-top: 4px; line-height: 1.5; font-size: 13px;'>"
                f"    {formatted}"
                f"  </div>"
                f"</div>"
            )

        self.chat_display.append(block)
        # Scroll to bottom
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())
