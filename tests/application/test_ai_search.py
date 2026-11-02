"""Unit tests for AISearchService natural language transaction query translation."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from novabank.application.dto.ai_query_dto import StructuredQueryDTO
from novabank.application.dto.statement_dto import StatementEntryDTO
from novabank.application.services.ai_search_service import AISearchService
from novabank.infrastructure.ai.exceptions import AIConnectionError, AITimeoutError
from novabank.infrastructure.ai.lm_studio_client import LMStudioClient


@pytest.fixture
def mock_lm_client() -> MagicMock:
    client = MagicMock(spec=LMStudioClient)
    return client


def test_translate_query_empty_input() -> None:
    """Empty or whitespace query should return fallback without calling AI."""
    service = AISearchService()
    result = service.translate_query("")
    assert result.is_fallback is True
    assert result.raw_query == ""
    assert result.keyword == ""

    result2 = service.translate_query("   ")
    assert result2.is_fallback is True


def test_translate_query_offline_no_client() -> None:
    """When no LMStudioClient is configured, falls back gracefully to keyword."""
    service = AISearchService(lm_client=None)
    result = service.translate_query("Large wire transfers to vendor")

    assert result.is_fallback is True
    assert result.keyword == "Large wire transfers to vendor"
    assert "not configured" in result.explanation


def test_translate_query_valid_json_response(mock_lm_client: MagicMock) -> None:
    """Valid JSON from AI model parses into StructuredQueryDTO with expected types."""
    mock_lm_client.chat_completion.return_value = """
    {
        "min_amount": 5000,
        "max_amount": null,
        "start_date": "2026-02-01",
        "end_date": "2026-02-28",
        "transaction_type": "DEPOSIT",
        "keyword": "payroll",
        "explanation": "Filtered for deposits >= $5,000 in February 2026 with keyword 'payroll'"
    }
    """
    service = AISearchService(lm_client=mock_lm_client, reference_date=date(2026, 3, 1))
    result = service.translate_query("show deposits over 5000 from last month for payroll")

    assert result.is_fallback is False
    assert result.min_amount == Decimal("5000")
    assert result.max_amount is None
    assert result.start_date == date(2026, 2, 1)
    assert result.end_date == date(2026, 2, 28)
    assert result.transaction_type == "DEPOSIT"
    assert result.keyword == "payroll"
    assert "payroll" in result.explanation


def test_translate_query_with_markdown_fences(mock_lm_client: MagicMock) -> None:
    """Markdown code blocks should be stripped cleanly."""
    mock_lm_client.chat_completion.return_value = """```json
    {
        "min_amount": 100.50,
        "max_amount": 500.00,
        "start_date": null,
        "end_date": null,
        "transaction_type": "WITHDRAWAL",
        "keyword": "ATM",
        "explanation": "Withdrawals between $100.50 and $500.00"
    }
    ```"""
    service = AISearchService(lm_client=mock_lm_client)
    result = service.translate_query("ATM withdrawals between 100.50 and 500")

    assert result.is_fallback is False
    assert result.min_amount == Decimal("100.50")
    assert result.max_amount == Decimal("500.00")
    assert result.transaction_type == "WITHDRAWAL"
    assert result.keyword == "ATM"


def test_translate_query_swapped_ranges_normalized(mock_lm_client: MagicMock) -> None:
    """If model outputs min > max or start > end, they should be swapped/normalized."""
    mock_lm_client.chat_completion.return_value = """
    {
        "min_amount": 1000,
        "max_amount": 200,
        "start_date": "2026-05-10",
        "end_date": "2026-05-01",
        "transaction_type": "TRANSFER",
        "keyword": null,
        "explanation": "Transfers"
    }
    """
    service = AISearchService(lm_client=mock_lm_client)
    result = service.translate_query("transfers")

    assert result.is_fallback is False
    assert result.min_amount == Decimal("200")
    assert result.max_amount == Decimal("1000")
    assert result.start_date == date(2026, 5, 1)
    assert result.end_date == date(2026, 5, 10)


def test_translate_query_rejects_sql_injection(mock_lm_client: MagicMock) -> None:
    """Any response containing SQL commands triggers fallback immediately."""
    mock_lm_client.chat_completion.return_value = """
    {
        "min_amount": 100,
        "sql": "SELECT * FROM transactions WHERE amount > 100",
        "explanation": "SQL query"
    }
    """
    service = AISearchService(lm_client=mock_lm_client)
    result = service.translate_query("all transactions > 100")

    assert result.is_fallback is True
    assert "invalid query schema" in result.explanation


def test_translate_query_rejects_invalid_transaction_type(mock_lm_client: MagicMock) -> None:
    """Invalid transaction types like CRYPTO or STOCK trigger fallback."""
    mock_lm_client.chat_completion.return_value = """
    {
        "min_amount": 50,
        "max_amount": null,
        "start_date": null,
        "end_date": null,
        "transaction_type": "CRYPTO_PURCHASE",
        "keyword": null,
        "explanation": "Crypto"
    }
    """
    service = AISearchService(lm_client=mock_lm_client)
    result = service.translate_query("show crypto transactions")

    assert result.is_fallback is True
    assert "Invalid transaction_type" in result.explanation


def test_translate_query_non_json_fallback(mock_lm_client: MagicMock) -> None:
    """Non-JSON conversational response triggers keyword fallback."""
    mock_lm_client.chat_completion.return_value = (
        "Sure, I can help you search for deposits! You had 5 deposits last week."
    )
    service = AISearchService(lm_client=mock_lm_client)
    result = service.translate_query("recent deposits")

    assert result.is_fallback is True
    assert result.keyword == "recent deposits"


def test_translate_query_ai_connection_error_fallback(mock_lm_client: MagicMock) -> None:
    """If LM Studio connection fails, graceful fallback to keyword search."""
    mock_lm_client.chat_completion.side_effect = AIConnectionError("Connection refused on 127.0.0.1:1234")
    service = AISearchService(lm_client=mock_lm_client)
    result = service.translate_query("deposits over 1000")

    assert result.is_fallback is True
    assert result.keyword == "deposits over 1000"
    assert "AI connection error" in result.explanation


def test_translate_query_scrubs_pii_before_call(mock_lm_client: MagicMock) -> None:
    """Customer phone number and account number in query are scrubbed before reaching AI."""
    mock_lm_client.chat_completion.return_value = """
    {
        "min_amount": null,
        "max_amount": null,
        "start_date": null,
        "end_date": null,
        "transaction_type": null,
        "keyword": "refund",
        "explanation": "Keyword refund"
    }
    """
    service = AISearchService(lm_client=mock_lm_client)
    service.translate_query("Refund for account 100000001234 or call 555-123-4567")

    # Inspect call arguments to LM Studio
    call_args = mock_lm_client.chat_completion.call_args
    user_prompt = call_args[1]["messages"][1]["content"]

    assert "100000001234" not in user_prompt
    assert "555-123-4567" not in user_prompt
    assert "****-****-1234" in user_prompt
    assert "[Phone-Redacted]" in user_prompt


def test_structured_query_dto_filtering() -> None:
    """Test StructuredQueryDTO.matches and filter_entries filtering on real entries."""
    e1 = StatementEntryDTO(
        transaction_id=1,
        transaction_ref="TXN-001",
        created_at=datetime(2026, 1, 15, 10, 0),
        transaction_type="DEPOSIT",
        direction="CREDIT",
        description="Salary Direct Deposit from Acme Corp",
        amount=Decimal("4500.00"),
        debit_amount=None,
        credit_amount=Decimal("4500.00"),
        balance_after=Decimal("4500.00"),
        currency="USD",
        created_by="teller",
        formatted_amount="$4,500.00",
        formatted_balance_after="$4,500.00",
        formatted_debit="",
        formatted_credit="+$4,500.00",
    )
    e2 = StatementEntryDTO(
        transaction_id=2,
        transaction_ref="TXN-002",
        created_at=datetime(2026, 2, 10, 14, 30),
        transaction_type="WITHDRAWAL",
        direction="DEBIT",
        description="ATM Cash Withdrawal Downtown Branch",
        amount=Decimal("200.00"),
        debit_amount=Decimal("200.00"),
        credit_amount=None,
        balance_after=Decimal("4300.00"),
        currency="USD",
        created_by="teller",
        formatted_amount="$200.00",
        formatted_balance_after="$4,300.00",
        formatted_debit="-$200.00",
        formatted_credit="",
    )
    e3 = StatementEntryDTO(
        transaction_id=3,
        transaction_ref="TXN-003",
        created_at=datetime(2026, 2, 20, 9, 0),
        transaction_type="DEPOSIT",
        direction="CREDIT",
        description="Client invoice payment Wire Transfer",
        amount=Decimal("8000.00"),
        debit_amount=None,
        credit_amount=Decimal("8000.00"),
        balance_after=Decimal("12300.00"),
        currency="USD",
        created_by="teller",
        formatted_amount="$8,000.00",
        formatted_balance_after="$12,300.00",
        formatted_debit="",
        formatted_credit="+$8,000.00",
    )

    entries = [e1, e2, e3]

    # Query 1: DEPOSIT over $5000
    q1 = StructuredQueryDTO(
        raw_query="deposits over 5000",
        min_amount=Decimal("5000.00"),
        transaction_type="DEPOSIT",
    )
    filtered1 = q1.filter_entries(entries)
    assert len(filtered1) == 1
    assert filtered1[0].transaction_ref == "TXN-003"

    # Query 2: Date filter for February 2026
    q2 = StructuredQueryDTO(
        raw_query="February transactions",
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 28),
    )
    filtered2 = q2.filter_entries(entries)
    assert len(filtered2) == 2
    assert {e.transaction_ref for e in filtered2} == {"TXN-002", "TXN-003"}

    # Query 3: Keyword "ATM"
    q3 = StructuredQueryDTO(
        raw_query="ATM",
        keyword="ATM",
    )
    filtered3 = q3.filter_entries(entries)
    assert len(filtered3) == 1
    assert filtered3[0].transaction_ref == "TXN-002"

