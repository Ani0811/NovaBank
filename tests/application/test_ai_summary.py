"""Unit tests for AISummaryService statement summarization and safety boundaries."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from novabank.application.dto.statement_dto import AccountStatementDTO, StatementEntryDTO
from novabank.application.services.ai_summary_service import AISummaryService
from novabank.infrastructure.ai.exceptions import AIConnectionError
from novabank.infrastructure.ai.lm_studio_client import LMStudioClient


@pytest.fixture
def sample_statement() -> AccountStatementDTO:
    entry1 = StatementEntryDTO(
        transaction_id=1,
        transaction_ref="TXN-001",
        created_at=datetime(2026, 2, 5, 10, 0),
        transaction_type="DEPOSIT",
        direction="CREDIT",
        description="Payroll Direct Deposit",
        amount=Decimal("3500.00"),
        debit_amount=None,
        credit_amount=Decimal("3500.00"),
        balance_after=Decimal("4500.00"),
        currency="USD",
        created_by="system",
        formatted_amount="$3,500.00",
        formatted_balance_after="$4,500.00",
        formatted_debit="",
        formatted_credit="+$3,500.00",
    )
    entry2 = StatementEntryDTO(
        transaction_id=2,
        transaction_ref="TXN-002",
        created_at=datetime(2026, 2, 12, 14, 0),
        transaction_type="WITHDRAWAL",
        direction="DEBIT",
        description="Mortgage Payment Wire",
        amount=Decimal("1200.00"),
        debit_amount=Decimal("1200.00"),
        credit_amount=None,
        balance_after=Decimal("3300.00"),
        currency="USD",
        created_by="teller",
        formatted_amount="$1,200.00",
        formatted_balance_after="$3,300.00",
        formatted_debit="-$1,200.00",
        formatted_credit="",
    )

    return AccountStatementDTO(
        account_number="123456789012",
        holder_name="Jane Doe",
        account_status="Active",
        currency="USD",
        start_date=datetime(2026, 2, 1),
        end_date=datetime(2026, 2, 28),
        generated_at=datetime(2026, 3, 1),
        opening_balance=Decimal("1000.00"),
        total_credits=Decimal("3500.00"),
        total_debits=Decimal("1200.00"),
        net_change=Decimal("2300.00"),
        closing_balance=Decimal("3300.00"),
        transaction_count=2,
        entries=(entry1, entry2),
    )


def test_generate_deterministic_summary(sample_statement: AccountStatementDTO) -> None:
    """Deterministic summary must include all critical figures and state reconciliation."""
    service = AISummaryService()
    summary = service.generate_deterministic_summary(sample_statement)

    assert "$1,000.00" in summary
    assert "$3,500.00" in summary
    assert "$1,200.00" in summary
    assert "$2,300.00" in summary
    assert "$3,300.00" in summary
    assert "2 transaction(s)" in summary
    assert "mathematically reconciled" in summary


def test_summarize_statement_offline_fallback(sample_statement: AccountStatementDTO) -> None:
    """When LM Studio client is None, returns deterministic summary."""
    service = AISummaryService(lm_client=None)
    summary = service.summarize_statement(sample_statement)

    assert "Account Statement Summary (USD):" in summary
    assert "$3,300.00" in summary


def test_summarize_statement_ai_connection_error(sample_statement: AccountStatementDTO) -> None:
    """When LM Studio fails to connect, gracefully falls back to deterministic summary."""
    mock_client = MagicMock(spec=LMStudioClient)
    mock_client.chat_completion.side_effect = AIConnectionError("Connection refused on 127.0.0.1:1234")

    service = AISummaryService(lm_client=mock_client)
    summary = service.summarize_statement(sample_statement)

    assert "Account Statement Summary (USD):" in summary
    assert "$3,300.00" in summary


def test_summarize_statement_success(sample_statement: AccountStatementDTO) -> None:
    """Valid professional narrative adhering to numerical consistency is returned."""
    mock_client = MagicMock(spec=LMStudioClient)
    mock_client.chat_completion.return_value = (
        "During February 2026, your account opened with $1,000.00 and recorded a net increase of $2,300.00, "
        "closing at $3,300.00. Total deposits reached $3,500.00, driven by payroll, while outflows totaled $1,200.00. "
        "Overall activity remained consistent across 2 transactions."
    )

    service = AISummaryService(lm_client=mock_client)
    summary = service.summarize_statement(sample_statement)

    assert "net increase of $2,300.00" in summary
    assert "closing at $3,300.00" in summary


def test_summarize_statement_rejects_word_limit_violation(sample_statement: AccountStatementDTO) -> None:
    """Summary exceeding 300 words is rejected in favor of fallback."""
    mock_client = MagicMock(spec=LMStudioClient)
    # Generate 350 words
    mock_client.chat_completion.return_value = "word " * 350

    service = AISummaryService(lm_client=mock_client)
    summary = service.summarize_statement(sample_statement)

    # Must fall back to deterministic template
    assert "Account Statement Summary (USD):" in summary


def test_summarize_statement_rejects_prohibited_investment_advice(sample_statement: AccountStatementDTO) -> None:
    """Advisory recommending equities or speculation is rejected."""
    mock_client = MagicMock(spec=LMStudioClient)
    mock_client.chat_completion.return_value = (
        "Your account balance is $3,300.00. You should invest in crypto and buy stock to grow wealth."
    )

    service = AISummaryService(lm_client=mock_client)
    summary = service.summarize_statement(sample_statement)

    assert "Account Statement Summary (USD):" in summary


def test_summarize_statement_rejects_hallucinated_figures(sample_statement: AccountStatementDTO) -> None:
    """Narratives citing invented dollar amounts fail consistency checks."""
    mock_client = MagicMock(spec=LMStudioClient)
    mock_client.chat_completion.return_value = (
        "You had a fantastic month! Your balance reached $99,500.00 with total deposits of $50,000.00."
    )

    service = AISummaryService(lm_client=mock_client)
    summary = service.summarize_statement(sample_statement)

    # Must fall back to deterministic template because $99,500.00 does not exist in statement
    assert "Account Statement Summary (USD):" in summary


def test_summarize_statement_pii_scrubbed_in_prompt(sample_statement: AccountStatementDTO) -> None:
    """Verify customer name and account number are completely scrubbed in the prompt."""
    mock_client = MagicMock(spec=LMStudioClient)
    mock_client.chat_completion.return_value = (
        "For February 2026, the closing balance was $3,300.00."
    )

    service = AISummaryService(lm_client=mock_client)
    service.summarize_statement(sample_statement)

    call_args = mock_client.chat_completion.call_args
    prompt_sent = call_args[1]["messages"][1]["content"]

    assert "Jane Doe" not in prompt_sent
    assert "123456789012" not in prompt_sent
    assert "****-****-9012" in prompt_sent
    assert "[Customer-Redacted]" in prompt_sent

