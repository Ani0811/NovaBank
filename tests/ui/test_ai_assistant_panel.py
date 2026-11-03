"""Unit tests for AIAssistantPanel UI view and AIAssistantViewModel."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from PySide6.QtWidgets import QApplication

from novabank.application.dto.activity_flag_dto import ActivityFlagDTO
from novabank.application.dto.statement_dto import AccountStatementDTO, StatementEntryDTO
from novabank.application.services.banking_service import BankingService
from novabank.infrastructure.ai.lm_studio_client import LMStudioClient
from novabank.ui.viewmodels.ai_assistant_viewmodel import AIAssistantViewModel
from novabank.ui.views.ai_assistant_panel import AIAssistantPanel


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def mock_lm_client() -> MagicMock:
    client = MagicMock(spec=LMStudioClient)
    client.check_health.return_value = True
    return client


@pytest.fixture
def mock_banking_service() -> MagicMock:
    srv = MagicMock(spec=BankingService)
    srv._session_factory = MagicMock()
    entry = StatementEntryDTO(
        transaction_id=1,
        transaction_ref="TXN-001",
        created_at=datetime(2026, 3, 1, 10, 0),
        transaction_type="WITHDRAWAL",
        direction="DEBIT",
        description="Wire Outflow to Vendor",
        amount=Decimal("500.00"),
        debit_amount=Decimal("500.00"),
        credit_amount=None,
        balance_after=Decimal("4500.00"),
        currency="USD",
        created_by="teller",
        formatted_amount="$500.00",
        formatted_balance_after="$4,500.00",
        formatted_debit="-$500.00",
        formatted_credit="",
    )
    stmt = AccountStatementDTO(
        account_number="100000000001",
        holder_name="Diana Prince",
        account_status="Active",
        currency="USD",
        start_date=datetime(2026, 3, 1),
        end_date=datetime(2026, 3, 31),
        generated_at=datetime(2026, 4, 1),
        opening_balance=Decimal("5000.00"),
        total_credits=Decimal("0.00"),
        total_debits=Decimal("500.00"),
        net_change=Decimal("-500.00"),
        closing_balance=Decimal("4500.00"),
        transaction_count=1,
        entries=(entry,),
    )
    srv.get_statement.return_value = stmt
    return srv


def test_ai_connection_indicator_connected(qapp: QApplication, mock_lm_client: MagicMock) -> None:
    """When LM Studio is healthy, badge displays Connected with success styling."""
    mock_lm_client.check_health.return_value = True
    vm = AIAssistantViewModel(lm_client=mock_lm_client)
    panel = AIAssistantPanel(viewmodel=vm)

    assert "Connected (Local LM Studio)" in panel.badge_lbl.text()
    assert panel.badge_lbl.property("status") == "success"


def test_ai_connection_indicator_offline(qapp: QApplication, mock_lm_client: MagicMock) -> None:
    """When LM Studio check fails, badge displays Offline with warning styling."""
    mock_lm_client.check_health.return_value = False
    vm = AIAssistantViewModel(lm_client=mock_lm_client)
    panel = AIAssistantPanel(viewmodel=vm)

    assert "Offline (Local Mode Only)" in panel.badge_lbl.text()
    assert panel.badge_lbl.property("status") == "warning"


def test_quick_action_summarize_no_account(qapp: QApplication, mock_lm_client: MagicMock) -> None:
    """Clicking summarize without account context warns teller in chat."""
    vm = AIAssistantViewModel(lm_client=mock_lm_client)
    panel = AIAssistantPanel(viewmodel=vm)

    panel.btn_summarize.click()
    chat_text = panel.chat_display.toPlainText()
    assert "Please enter an Account Number" in chat_text


def test_quick_action_summarize_with_account(
    qapp: QApplication, mock_lm_client: MagicMock, mock_banking_service: MagicMock
) -> None:
    """Clicking summarize with account context produces financial summary in chat."""
    vm = AIAssistantViewModel(
        lm_client=mock_lm_client,
        banking_service=mock_banking_service,
    )
    panel = AIAssistantPanel(viewmodel=vm)

    panel.account_input.setText("100000000001")
    panel.btn_summarize.click()

    chat_text = panel.chat_display.toPlainText()
    assert "Summarize statement for account 100000000001" in chat_text
    assert "$5,000.00" in chat_text or "$4,500.00" in chat_text


def test_quick_action_large_expenses(
    qapp: QApplication, mock_lm_client: MagicMock, mock_banking_service: MagicMock
) -> None:
    """Clicking large expenses lists notable debits for the account."""
    vm = AIAssistantViewModel(
        lm_client=mock_lm_client,
        banking_service=mock_banking_service,
    )
    panel = AIAssistantPanel(viewmodel=vm)

    panel.account_input.setText("100000000001")
    panel.btn_large_expenses.click()

    chat_text = panel.chat_display.toPlainText()
    assert "Notable Expenses & Outflows" in chat_text
    assert "Wire Outflow to Vendor" in chat_text
    assert "-$500.00" in chat_text


def test_quick_action_explain_flags_clean(
    qapp: QApplication, mock_lm_client: MagicMock, mock_banking_service: MagicMock
) -> None:
    """Clean account returns Clean security status message."""
    vm = AIAssistantViewModel(
        lm_client=mock_lm_client,
        banking_service=mock_banking_service,
    )
    panel = AIAssistantPanel(viewmodel=vm)

    panel.account_input.setText("100000000001")
    panel.btn_explain_flags.click()

    chat_text = panel.chat_display.toPlainText()
    assert "Security Status: Clean" in chat_text


def test_quick_action_explain_flags_triggered(
    qapp: QApplication, mock_lm_client: MagicMock, mock_banking_service: MagicMock
) -> None:
    """Triggered security flags include teller guidance and compliance rationale."""
    vm = AIAssistantViewModel(
        lm_client=mock_lm_client,
        banking_service=mock_banking_service,
    )
    # Mock activity_monitoring_service to return a flag
    flag = ActivityFlagDTO(
        flag_code="LARGE_TRANSACTION",
        severity="HIGH",
        rule_name="Large Transaction BSA/CTR Threshold",
        triggered_at=datetime(2026, 3, 1),
        description="Single transaction of $25,000.00 exceeds threshold.",
        metrics={"amount": "25000.00"},
        account_number_masked="****-****-0001",
        ai_explanation="A transaction of $25,000 was executed. Please verify customer identity and complete Form 112.",
    )
    vm.activity_monitoring_service.evaluate_and_explain = MagicMock(return_value=[flag])

    panel = AIAssistantPanel(viewmodel=vm)
    panel.account_input.setText("100000000001")
    panel.btn_explain_flags.click()

    chat_text = panel.chat_display.toPlainText()
    assert "Active Security & Compliance Alerts" in chat_text
    assert "Large Transaction BSA/CTR Threshold" in chat_text
    assert "Form 112" in chat_text


def test_send_natural_language_prompt(
    qapp: QApplication, mock_lm_client: MagicMock, mock_banking_service: MagicMock
) -> None:
    """Entering prompt in input and sending dispatches query to AI and shows in chat."""
    mock_lm_client.chat_completion.return_value = """
    {
        "min_amount": 100,
        "max_amount": null,
        "start_date": null,
        "end_date": null,
        "transaction_type": "WITHDRAWAL",
        "keyword": "Wire",
        "explanation": "Withdrawals >= $100 with keyword 'Wire'"
    }
    """
    vm = AIAssistantViewModel(
        lm_client=mock_lm_client,
        banking_service=mock_banking_service,
    )
    panel = AIAssistantPanel(viewmodel=vm)
    panel.account_input.setText("100000000001")

    panel.prompt_input.setText("show withdrawals over 100 for Wire")
    panel.btn_send.click()

    chat_text = panel.chat_display.toPlainText()
    assert "show withdrawals over 100 for Wire" in chat_text
    assert "Query Analysis" in chat_text
    assert "Wire Outflow to Vendor" in chat_text


def test_clear_chat(qapp: QApplication, mock_lm_client: MagicMock) -> None:
    """Clicking Clear Chat clears the display."""
    vm = AIAssistantViewModel(lm_client=mock_lm_client)
    panel = AIAssistantPanel(viewmodel=vm)

    panel.btn_clear_chat.click()
    chat_text = panel.chat_display.toPlainText()
    assert "Chat log cleared" in chat_text
