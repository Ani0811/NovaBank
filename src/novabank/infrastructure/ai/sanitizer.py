"""Client-Side PII Sanitizer and AI Trust Boundary Privacy Guard."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Optional, Sequence

from novabank.infrastructure.ai.exceptions import AIPrivacyViolationError

if TYPE_CHECKING:
    from novabank.application.dto.account_dto import AccountDTO
    from novabank.application.dto.statement_dto import AccountStatementDTO


class PIISanitizer:
    """Sanitizes Personally Identifiable Information (PII) before passing data to local LLMs."""

    # Regex patterns
    PHONE_REGEX = re.compile(r"(?<!\d)(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)")
    EMAIL_REGEX = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b")
    SSN_REGEX = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
    ACCOUNT_NUM_REGEX = re.compile(r"(?<!\d)\d{12}(?!\d)")

    REPLACEMENT_NAME = "[Customer-Redacted]"
    REPLACEMENT_PHONE = "[Phone-Redacted]"
    REPLACEMENT_ADDRESS = "[Address-Redacted]"
    REPLACEMENT_EMAIL = "[Email-Redacted]"
    REPLACEMENT_SSN = "[SSN-Redacted]"

    @classmethod
    def mask_account_number(cls, account_number: str) -> str:
        """Mask account number retaining only the last 4 digits (e.g. ****-****-1234)."""
        clean = account_number.replace("-", "").replace(" ", "").strip()
        if len(clean) >= 4:
            last4 = clean[-4:]
            return f"****-****-{last4}"
        return "****-****-****"

    @classmethod
    def sanitize_text(
        cls,
        text: str,
        *,
        known_names: Optional[Sequence[str]] = None,
        known_addresses: Optional[Sequence[str]] = None,
        known_phones: Optional[Sequence[str]] = None,
    ) -> str:
        """Scrub PII from freeform text using regex patterns and exact known tokens."""
        if not text:
            return ""

        scrubbed = text

        # 1. Redact known names
        if known_names:
            for name in known_names:
                if name and len(name.strip()) > 2:
                    pattern = re.compile(re.escape(name.strip()), re.IGNORECASE)
                    scrubbed = pattern.sub(cls.REPLACEMENT_NAME, scrubbed)

        # 2. Redact known addresses
        if known_addresses:
            for addr in known_addresses:
                if addr and len(addr.strip()) > 3:
                    pattern = re.compile(re.escape(addr.strip()), re.IGNORECASE)
                    scrubbed = pattern.sub(cls.REPLACEMENT_ADDRESS, scrubbed)

        # 3. Redact known phones
        if known_phones:
            for ph in known_phones:
                if ph and len(ph.strip()) >= 7:
                    pattern = re.compile(re.escape(ph.strip()), re.IGNORECASE)
                    scrubbed = pattern.sub(cls.REPLACEMENT_PHONE, scrubbed)

        # 4. Regex mask 12-digit account numbers first
        def _mask_match(m: re.Match) -> str:
            raw = m.group(0)
            return cls.mask_account_number(raw)

        scrubbed = cls.ACCOUNT_NUM_REGEX.sub(_mask_match, scrubbed)

        # 5. Regex scrub phone numbers
        scrubbed = cls.PHONE_REGEX.sub(cls.REPLACEMENT_PHONE, scrubbed)

        # 6. Regex scrub emails
        scrubbed = cls.EMAIL_REGEX.sub(cls.REPLACEMENT_EMAIL, scrubbed)

        # 7. Regex scrub SSNs
        scrubbed = cls.SSN_REGEX.sub(cls.REPLACEMENT_SSN, scrubbed)

        return scrubbed

    @classmethod
    def sanitize_account_dto(cls, account: AccountDTO) -> dict[str, Any]:
        """Convert AccountDTO to an AI-safe, PII-scrubbed dictionary."""
        return {
            "account_number_masked": cls.mask_account_number(account.account_number),
            "holder_name": cls.REPLACEMENT_NAME,
            "address": cls.REPLACEMENT_ADDRESS,
            "city": account.city,
            "state": account.state,
            "country": account.country,
            "phone": cls.REPLACEMENT_PHONE,
            "is_active": account.is_active,
            "balance": str(account.balance),
            "currency": account.currency,
        }

    @classmethod
    def sanitize_statement_dto(cls, statement: AccountStatementDTO) -> dict[str, Any]:
        """Convert AccountStatementDTO to an AI-safe financial dataset."""
        known_names = [statement.holder_name]

        sanitized_entries = []
        for e in statement.entries:
            safe_desc = cls.sanitize_text(e.description, known_names=known_names)
            sanitized_entries.append({
                "date": e.created_at.strftime("%Y-%m-%d"),
                "type": e.transaction_type,
                "direction": e.direction,
                "amount": str(e.amount),
                "debit": str(e.debit_amount) if e.debit_amount is not None else None,
                "credit": str(e.credit_amount) if e.credit_amount is not None else None,
                "balance_after": str(e.balance_after),
                "description": safe_desc,
            })

        return {
            "account_number_masked": cls.mask_account_number(statement.account_number),
            "holder_name": cls.REPLACEMENT_NAME,
            "account_status": statement.account_status,
            "currency": statement.currency,
            "period_start": (
                statement.start_date.strftime("%Y-%m-%d")
                if statement.start_date
                else "Inception"
            ),
            "period_end": statement.end_date.strftime("%Y-%m-%d"),
            "opening_balance": str(statement.opening_balance),
            "total_credits": str(statement.total_credits),
            "total_debits": str(statement.total_debits),
            "closing_balance": str(statement.closing_balance),
            "transaction_count": statement.transaction_count,
            "entries": sanitized_entries,
        }

    @classmethod
    def assert_pii_free(
        cls,
        prompt_payload: str,
        forbidden_tokens: Sequence[str],
    ) -> None:
        """Enforce strict trust boundary: verify no forbidden customer PII tokens leaked into prompt.

        Raises:
            AIPrivacyViolationError: If any unmasked forbidden token is found in prompt_payload.
        """
        for token in forbidden_tokens:
            if not token or len(token.strip()) < 3:
                continue
            if token.lower() in prompt_payload.lower():
                raise AIPrivacyViolationError(
                    f"Privacy Trust Boundary Violation: Prompt payload contains unmasked customer PII: '{token}'"
                )
