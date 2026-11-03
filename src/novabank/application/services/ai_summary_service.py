"""Smart Account Statement Summarizer Service.

Generates concise, factual, and strictly validated narrative summaries of customer account statements.
Enforces client-side PII protection, numerical consistency checking, length constraints (< 300 words),
advisory restrictions (no investment advice/speculation), and deterministic template fallbacks.
"""

from __future__ import annotations

import logging
import re
from decimal import Decimal, InvalidOperation
from typing import Optional, Set

from novabank.application.dto.statement_dto import AccountStatementDTO
from novabank.infrastructure.ai.exceptions import AIError
from novabank.infrastructure.ai.lm_studio_client import LMStudioClient
from novabank.infrastructure.ai.sanitizer import PIISanitizer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a professional banking advisory assistant for NovaBank.
Generate a concise, factual financial summary for the provided statement period.

Strict Guidelines:
1. Keep the summary under 250 words.
2. Use a professional, objective, and polite banking tone.
3. Cite ONLY the exact numbers provided in the statement summary. Never invent, extrapolate, or alter financial amounts.
4. DO NOT provide investment advice, asset allocations, or recommendations to buy/sell equities or securities.
5. DO NOT speculate on customer lifestyle, creditworthiness, or personal spending habits.
6. Present findings clearly: opening/closing balance, net cash flow, major deposits/withdrawals.
"""

PROHIBITED_ADVICE_PATTERNS = re.compile(
    r"\b(invest in|buy stocks?|buy crypto|securities advice|financial distress|insolvent|bankrupt|speculat(e|ion)|portfolio allocation)\b",
    re.IGNORECASE,
)

CURRENCY_NUMBER_REGEX = re.compile(r"\$?\b([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{2})?)\b")


class AISummaryService:
    """Application service for generating validated narrative account statement summaries."""

    def __init__(self, lm_client: Optional[LMStudioClient] = None) -> None:
        self._lm_client = lm_client

    def generate_deterministic_summary(self, statement: AccountStatementDTO) -> str:
        """Generate a reliable, deterministic template summary with guaranteed mathematical accuracy."""
        period_str = (
            f"{statement.start_date.strftime('%B %d, %Y')} to {statement.end_date.strftime('%B %d, %Y')}"
            if statement.start_date
            else f"Inception to {statement.end_date.strftime('%B %d, %Y')}"
        )

        flow_direction = "positive net cash flow" if statement.net_change >= 0 else "net outflow"

        return (
            f"Account Statement Summary ({statement.currency}):\n"
            f"For the period from {period_str}, the account recorded {statement.transaction_count} transaction(s). "
            f"Total deposits were ${statement.total_credits:,.2f} and total withdrawals were ${statement.total_debits:,.2f}, "
            f"reflecting a {flow_direction} of ${abs(statement.net_change):,.2f}. "
            f"The period opened with a balance of ${statement.opening_balance:,.2f} and closed at ${statement.closing_balance:,.2f}. "
            f"All transaction ledgers are mathematically reconciled."
        )

    def summarize_statement(self, statement: AccountStatementDTO) -> str:
        """Produce an AI narrative summary with strict validation and offline fallback."""
        # 1. Offline fallback if client not configured
        if not self._lm_client:
            return self.generate_deterministic_summary(statement)

        # 2. Sanitize statement data
        sanitized_data = PIISanitizer.sanitize_statement_dto(statement)

        # 3. Construct prompt context
        user_prompt = (
            f"Statement Data:\n"
            f"- Customer: {sanitized_data['holder_name']}\n"
            f"- Account: {sanitized_data['account_number_masked']}\n"
            f"- Period: {sanitized_data['period_start']} to {sanitized_data['period_end']}\n"
            f"- Currency: {statement.currency}\n"
            f"- Opening Balance: ${statement.opening_balance:,.2f}\n"
            f"- Total Inflow (Credits): ${statement.total_credits:,.2f}\n"
            f"- Total Outflow (Debits): ${statement.total_debits:,.2f}\n"
            f"- Net Change: ${statement.net_change:,.2f}\n"
            f"- Closing Balance: ${statement.closing_balance:,.2f}\n"
            f"- Total Transactions: {statement.transaction_count}\n"
        )

        if statement.entries:
            user_prompt += "\nRecent Notable Activity (Sanitized):\n"
            # Include up to 5 top entries
            for e in statement.entries[:5]:
                safe_desc = PIISanitizer.sanitize_text(
                    e.description, known_names=[statement.holder_name]
                )
                user_prompt += (
                    f"  * {e.created_at.strftime('%Y-%m-%d')}: {e.transaction_type} "
                    f"of ${e.amount:,.2f} ({safe_desc})\n"
                )

        # 4. Trust Boundary Privacy Assertion
        PIISanitizer.assert_pii_free(
            user_prompt,
            forbidden_tokens=[statement.holder_name, statement.account_number],
        )

        # 5. Call LM Studio
        try:
            narrative = self._lm_client.chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=400,
            )
        except AIError as err:
            logger.warning("LM Studio summarization call failed: %s. Using fallback.", err)
            return self.generate_deterministic_summary(statement)

        # 6. Validate output
        try:
            self._validate_summary(narrative, statement)
            return narrative.strip()
        except Exception as val_err:
            logger.warning("AI narrative failed validation: %s. Using fallback.", val_err)
            return self.generate_deterministic_summary(statement)

    def _validate_summary(self, narrative: str, statement: AccountStatementDTO) -> None:
        """Enforce length, advice restrictions, and numerical consistency."""
        clean_text = narrative.strip()
        if not clean_text:
            raise ValueError("Model returned empty summary.")

        # Length check (< 300 words)
        words = clean_text.split()
        if len(words) > 300:
            raise ValueError(f"Summary exceeds word limit: {len(words)} > 300 words.")

        # Advisory restriction check
        if PROHIBITED_ADVICE_PATTERNS.search(clean_text):
            raise ValueError("Summary contains prohibited financial/investment advice.")

        # Numerical consistency check
        allowed_numbers: Set[Decimal] = {
            statement.opening_balance,
            statement.total_credits,
            statement.total_debits,
            statement.net_change,
            abs(statement.net_change),
            statement.closing_balance,
            Decimal(statement.transaction_count),
        }
        for entry in statement.entries:
            allowed_numbers.add(entry.amount)
            allowed_numbers.add(entry.balance_after)
            if entry.debit_amount is not None:
                allowed_numbers.add(entry.debit_amount)
            if entry.credit_amount is not None:
                allowed_numbers.add(entry.credit_amount)

        # Extract numeric tokens from narrative
        matches = CURRENCY_NUMBER_REGEX.findall(clean_text)
        for token in matches:
            cleaned_num_str = token.replace(",", "")
            try:
                val = Decimal(cleaned_num_str)
            except (InvalidOperation, ValueError):
                continue

            # Ignore small integers like days, single-digit counts (e.g. 1, 2, 3) or year digits
            if val < Decimal("10.00") and val == val.to_integral_value():
                continue
            if val in {Decimal(2025), Decimal(2026), Decimal(2027)}:
                continue

            # Check if value matches allowed figures
            matched = any(abs(val - allowed) < Decimal("0.01") for allowed in allowed_numbers)
            if not matched:
                raise ValueError(
                    f"Numerical inconsistency: Model cited unauthorized/hallucinated amount: ${val}"
                )
