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
        root_layout.setContentsMargins(24, 20, 24, 20)
        root_layout.setSpacing(16)

        # 1. Header & Connection Status Card
        header_card = QFrame()
        header_card.setObjectName("AIHeaderCard")
        header_card.setProperty("class", "CardFrame")
        header_layout = QHBoxLayout(header_card)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(12)

        info_box = QVBoxLayout()
        info_box.setSpacing(2)
        title_lbl = QLabel("🤖 Local Banking Assistant")
        title_lbl.setProperty("class", "CardTitle")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: 700; color: #38bdf8;")
        desc_lbl = QLabel("Private, client-side financial intelligence connecting strictly to local loopback (LM Studio).")
        desc_lbl.setProperty("class", "CardMuted")
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

        self.btn_refresh_status = QPushButton("🔄 Ping AI")
        self.btn_refresh_status.setObjectName("BtnRefreshAIStatus")
        self.btn_refresh_status.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        self.btn_refresh_status.clicked.connect(self.vm.check_connection)

        header_layout.addWidget(self.badge_lbl)
        header_layout.addWidget(self.btn_refresh_status)
        root_layout.addWidget(header_card)

        # 2. Context & Quick Action Controls Bar
        controls_card = QFrame()
        controls_card.setProperty("class", "CardFrame")
        controls_layout = QVBoxLayout(controls_card)
        controls_layout.setContentsMargins(16, 12, 16, 12)
        controls_layout.setSpacing(10)

        # Account Context Bar
        acc_box = QHBoxLayout()
        acc_box.setSpacing(8)
        acc_lbl = QLabel("Target Account:")
        acc_lbl.setStyleSheet("font-weight: 600; color: #94a3b8;")

        self.account_input = QLineEdit()
        self.account_input.setObjectName("AIAccountContextInput")
        self.account_input.setPlaceholderText("Enter 12-digit Account Number (e.g. 100000000001)")
        self.account_input.setMaxLength(14)
        self.account_input.setStyleSheet("padding: 6px 10px; background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; color: #f8fafc;")
        self.account_input.textChanged.connect(self.vm.set_active_account)

        acc_box.addWidget(acc_lbl)
        acc_box.addWidget(self.account_input, stretch=1)
        controls_layout.addLayout(acc_box)

        # Quick Actions Row
        quick_actions_box = QHBoxLayout()
        quick_actions_box.setSpacing(8)

        quick_lbl = QLabel("Quick Actions:")
        quick_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b; text-transform: uppercase;")
        quick_actions_box.addWidget(quick_lbl)

        self.btn_summarize = QPushButton("📋 Summarize Statement")
        self.btn_summarize.setObjectName("BtnQuickSummarize")
        self.btn_summarize.setStyleSheet("padding: 6px 12px; background-color: #1e3a8a; border-radius: 6px; font-weight: 500;")
        self.btn_summarize.clicked.connect(lambda: self.vm.quick_action_summarize())

        self.btn_large_expenses = QPushButton("💸 Find Large Expenses")
        self.btn_large_expenses.setObjectName("BtnQuickLargeExpenses")
        self.btn_large_expenses.setStyleSheet("padding: 6px 12px; background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; font-weight: 500;")
        self.btn_large_expenses.clicked.connect(lambda: self.vm.quick_action_find_large_expenses())

        self.btn_explain_flags = QPushButton("🛡️ Explain Active Flags")
        self.btn_explain_flags.setObjectName("BtnQuickExplainFlags")
        self.btn_explain_flags.setStyleSheet("padding: 6px 12px; background-color: #1e293b; border: 1px solid #334155; border-radius: 6px; font-weight: 500;")
        self.btn_explain_flags.clicked.connect(lambda: self.vm.quick_action_explain_flags())

        quick_actions_box.addWidget(self.btn_summarize)
        quick_actions_box.addWidget(self.btn_large_expenses)
        quick_actions_box.addWidget(self.btn_explain_flags)
        quick_actions_box.addStretch()

        self.btn_clear_chat = QPushButton("🗑️ Clear Chat")
        self.btn_clear_chat.setObjectName("BtnClearChat")
        self.btn_clear_chat.setStyleSheet("padding: 4px 10px; font-size: 11px; background: transparent; border: none; color: #94a3b8;")
        self.btn_clear_chat.clicked.connect(self._clear_chat)
        quick_actions_box.addWidget(self.btn_clear_chat)

        controls_layout.addLayout(quick_actions_box)
        root_layout.addWidget(controls_card)

        # 3. Conversational Chat Log Display
        self.chat_display = QTextEdit()
        self.chat_display.setObjectName("AIChatDisplay")
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet(
            "background-color: #0b1120; border: 1px solid #1e293b; border-radius: 8px; "
            "padding: 16px; font-size: 13px; line-height: 1.5; color: #e2e8f0;"
        )
        root_layout.addWidget(self.chat_display, stretch=1)

        # 4. Input Prompt & Submit Bar
        input_container = QFrame()
        input_container.setProperty("class", "CardFrame")
        input_layout = QHBoxLayout(input_container)
        input_layout.setContentsMargins(12, 8, 12, 8)
        input_layout.setSpacing(8)

        self.prompt_input = QLineEdit()
        self.prompt_input.setObjectName("AIPromptInput")
        self.prompt_input.setPlaceholderText("Ask a question (e.g. 'Show deposits over 5,000 from last month')...")
        self.prompt_input.setStyleSheet("padding: 10px 14px; background-color: #0f172a; border: 1px solid #334155; border-radius: 6px; font-size: 13px; color: #f8fafc;")
        self.prompt_input.returnPressed.connect(self._on_send_clicked)

        self.btn_send = QPushButton("🚀 Send")
        self.btn_send.setObjectName("BtnSendAIPrompt")
        self.btn_send.setProperty("class", "PrimaryButton")
        self.btn_send.setMinimumWidth(90)
        self.btn_send.clicked.connect(self._on_send_clicked)

        input_layout.addWidget(self.prompt_input, stretch=1)
        input_layout.addWidget(self.btn_send)

        root_layout.addWidget(input_container)

        # Initial Welcome Message
        self._append_message(
            "assistant",
            "👋 Welcome to **NovaBank AI Assistant**.\n"
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
            self.btn_send.setText("⏳...")
        else:
            self.btn_send.setText("🚀 Send")

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
                f"<div style='margin-bottom: 12px; text-align: right;'>"
                f"  <span style='font-size: 11px; color: #64748b; margin-right: 4px;'>{timestamp}</span>"
                f"  <span style='font-weight: 600; color: #38bdf8;'>Teller</span><br>"
                f"  <div style='display: inline-block; background-color: #1e3a8a; color: #ffffff; "
                f"              padding: 8px 14px; border-radius: 8px; margin-top: 4px; text-align: left; max-width: 80%;'>"
                f"    {formatted}"
                f"  </div>"
                f"</div>"
            )
        else:
            block = (
                f"<div style='margin-bottom: 16px; text-align: left;'>"
                f"  <span style='font-weight: 600; color: #34d399;'>🤖 NovaBank AI</span>"
                f"  <span style='font-size: 11px; color: #64748b; margin-left: 6px;'>{timestamp}</span><br>"
                f"  <div style='background-color: #1e293b; color: #f1f5f9; padding: 12px 16px; "
                f"              border: 1px solid #334155; border-radius: 8px; margin-top: 4px; line-height: 1.5;'>"
                f"    {formatted}"
                f"  </div>"
                f"</div>"
            )

        self.chat_display.append(block)
        # Scroll to bottom
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

