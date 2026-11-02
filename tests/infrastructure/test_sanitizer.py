"""Tests for PIISanitizer and AI privacy trust boundary enforcement."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest

from novabank.application.dto.account_dto import AccountDTO
from novabank.application.dto.statement_dto import AccountStatementDTO, StatementEntryDTO
from novabank.infrastructure.ai.exceptions import AIPrivacyViolationError
from novabank.infrastructure.ai.sanitizer import PIISanitizer


def test_mask_account_number() -> None:
    """Verify account number masking retains only last 4 digits."""
    assert PIISanitizer.mask_account_number("100000000001") == "****-****-0001"
    assert PIISanitizer.mask_account_number("1234-5678-9012") == "****-****-9012"
    assert PIISanitizer.mask_account_number("1234") == "****-****-1234"
    assert PIISanitizer.mask_account_number("12") == "****-****-****"


def test_sanitize_text_regex_pii() -> None:
    """Verify regex scrubbing of phone numbers, emails, SSNs, and account numbers."""
    raw = (
        "Customer Alice called from 555-123-4567 or (555) 987-6543. "
        "Email is alice@bank.com, SSN is 123-45-6789, account is 100000001234."
    )
    scrubbed = PIISanitizer.sanitize_text(raw)

    assert "555-123-4567" not in scrubbed
    assert "(555) 987-6543" not in scrubbed
    assert "alice@bank.com" not in scrubbed
    assert "123-45-6789" not in scrubbed
    assert "100000001234" not in scrubbed

    assert "[Phone-Redacted]" in scrubbed
    assert "[Email-Redacted]" in scrubbed
    assert "[SSN-Redacted]" in scrubbed
    assert "****-****-1234" in scrubbed


def test_sanitize_text_known_entities() -> None:
    """Verify exact redaction of customer name and physical address."""
    raw = "Wire transfer authorized by Bruce Wayne living at 1007 Mountain Drive."
    scrubbed = PIISanitizer.sanitize_text(
        raw,
        known_names=["Bruce Wayne"],
        known_addresses=["1007 Mountain Drive"],
    )

    assert "Bruce Wayne" not in scrubbed
    assert "1007 Mountain Drive" not in scrubbed
    assert "[Customer-Redacted]" in scrubbed
    assert "[Address-Redacted]" in scrubbed


def test_sanitize_account_dto() -> None:
    """Verify AccountDTO is converted to PII-free dictionary."""
    acc = AccountDTO(
        account_number="123456789012",
        holder_name="Diana Prince",
        dob=date(1990, 8, 12),
        address_line="100 Gateway Blvd",
        city="Boston",
        state="MA",
        country="USA",
        phone_number="5558889999",
        is_active=True,
        balance=Decimal("2500.00"),
        currency="USD",
        version=1,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )

    data = PIISanitizer.sanitize_account_dto(acc)

    assert data["account_number_masked"] == "****-****-9012"
    assert data["holder_name"] == "[Customer-Redacted]"
    assert data["address"] == "[Address-Redacted]"
    assert data["phone"] == "[Phone-Redacted]"
    assert data["city"] == "Boston"
    assert data["balance"] == "2500.00"


def test_sanitize_statement_dto() -> None:
    """Verify AccountStatementDTO scrub cleans customer name and transaction lines."""
    entry = StatementEntryDTO(
        transaction_id=1,
        transaction_ref="TXN-001",
        created_at=datetime(2026, 3, 1, 10, 0),
        transaction_type="DEPOSIT",
        direction="CREDIT",
        description="Deposit from Diana Prince for project fee",
        amount=Decimal("1000.00"),
        debit_amount=None,
        credit_amount=Decimal("1000.00"),
        balance_after=Decimal("1000.00"),
        currency="USD",
        created_by="teller",
        formatted_amount="$1,000.00",
        formatted_balance_after="$1,000.00",
        formatted_debit="",
        formatted_credit="+$1,000.00",
    )

    stmt = AccountStatementDTO(
        account_number="987654321098",
        holder_name="Diana Prince",
        account_status="Active",
        currency="USD",
        start_date=None,
        end_date=datetime(2026, 3, 31),
        generated_at=datetime(2026, 4, 1),
        opening_balance=Decimal("0.00"),
        total_credits=Decimal("1000.00"),
        total_debits=Decimal("0.00"),
        net_change=Decimal("1000.00"),
        closing_balance=Decimal("1000.00"),
        transaction_count=1,
        entries=(entry,),
    )

    sanitized = PIISanitizer.sanitize_statement_dto(stmt)

    assert sanitized["account_number_masked"] == "****-****-1098"
    assert sanitized["holder_name"] == "[Customer-Redacted]"
    # Name scrubbed from transaction description
    safe_desc = sanitized["entries"][0]["description"]
    assert "Diana Prince" not in safe_desc
    assert "[Customer-Redacted]" in safe_desc


def test_assert_pii_free_raises_on_leak() -> None:
    """Verify assert_pii_free catches leaking tokens and raises AIPrivacyViolationError."""
    forbidden = ["Clark Kent", "555-111-2222", "344 Clinton St"]

    # Leaking name
    prompt_leaking_name = "Please analyze transactions for customer Clark Kent."
    with pytest.raises(AIPrivacyViolationError, match="Clark Kent"):
        PIISanitizer.assert_pii_free(prompt_leaking_name, forbidden)

    # Leaking phone
    prompt_leaking_phone = "Notify phone 555-111-2222 about suspicious activity."
    with pytest.raises(AIPrivacyViolationError, match="555-111-2222"):
        PIISanitizer.assert_pii_free(prompt_leaking_phone, forbidden)

    # Clean prompt passes without error
    clean_prompt = "Please analyze transactions for customer [Customer-Redacted] on account ****-****-1234."
    PIISanitizer.assert_pii_free(clean_prompt, forbidden)
