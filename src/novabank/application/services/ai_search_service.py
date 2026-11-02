"""Natural Language Transaction Query Translator Service.

Translates freeform user search queries into strictly validated StructuredQueryDTO filter objects.
Protects against SQL injection and hallucinations by strictly validating all fields and enforcing
fallback to standard keyword search when AI output fails schema validation.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from typing import Any, Optional

from novabank.application.dto.ai_query_dto import StructuredQueryDTO
from novabank.infrastructure.ai.exceptions import AIError
from novabank.infrastructure.ai.lm_studio_client import LMStudioClient
from novabank.infrastructure.ai.sanitizer import PIISanitizer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a transaction filter translator for NovaBank.
Convert the user's natural language transaction search into a JSON object matching this schema exactly:
{
  "min_amount": number or null,
  "max_amount": number or null,
  "start_date": "YYYY-MM-DD" or null,
  "end_date": "YYYY-MM-DD" or null,
  "transaction_type": "DEPOSIT" | "WITHDRAWAL" | "TRANSFER" | null,
  "keyword": string or null,
  "explanation": string
}

Rules:
1. ONLY return the JSON object. Do not include markdown code fences, comments, or extra text.
2. transaction_type must be strictly one of: "DEPOSIT", "WITHDRAWAL", "TRANSFER", or null.
3. Dates must be formatted as YYYY-MM-DD.
4. Set min_amount and max_amount to positive numbers without currency symbols.
5. Extract any specific merchant, counterparty, or note into keyword.
6. NEVER generate SQL queries, table names, or commands.
7. If the query does not specify a filter for a field, set it to null.
"""

FORBIDDEN_SQL_PATTERNS = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|UNION|WHERE|FROM|TRUNCATE)\b",
    re.IGNORECASE,
)


class AISearchService:
    """Application service for translating natural language queries to structured transaction filters."""

    VALID_TYPES = {"DEPOSIT", "WITHDRAWAL", "TRANSFER"}

    def __init__(
        self,
        lm_client: Optional[LMStudioClient] = None,
        reference_date: Optional[date] = None,
    ) -> None:
        self._lm_client = lm_client
        self._reference_date = reference_date

    def translate_query(
        self,
        user_query: str,
        *,
        reference_date: Optional[date] = None,
    ) -> StructuredQueryDTO:
        """Translate a natural language search query into a validated StructuredQueryDTO.

        If the AI client is unavailable, times out, or returns invalid schema/hallucinations,
        this method gracefully falls back to keyword-based filtering.
        """
        raw_text = (user_query or "").strip()
        if not raw_text:
            return StructuredQueryDTO(
                raw_query="",
                keyword="",
                is_fallback=True,
                explanation="Empty query provided.",
            )

        # 1. Scrub PII before contacting LLM
        sanitized_query = PIISanitizer.sanitize_text(raw_text)

        # 2. Check client availability
        if not self._lm_client:
            return self._build_fallback(
                raw_query=raw_text,
                keyword=sanitized_query,
                reason="AI service is not configured. Falling back to keyword search.",
            )

        ref_date = reference_date or self._reference_date or date.today()
        user_prompt = f"Reference Current Date: {ref_date.isoformat()}\nQuery: {sanitized_query}"

        # 3. Call local LM Studio with safety boundary
        try:
            response_content = self._lm_client.chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
            )
        except AIError as err:
            logger.warning("LM Studio query translation failed: %s", err)
            return self._build_fallback(
                raw_query=raw_text,
                keyword=sanitized_query,
                reason=f"AI connection error ({err}). Falling back to keyword search.",
            )

        # 4. Parse and strictly validate the JSON response
        try:
            return self._parse_and_validate(raw_text, sanitized_query, response_content)
        except Exception as parse_err:
            logger.warning("AI translation response validation failed: %s", parse_err)
            return self._build_fallback(
                raw_query=raw_text,
                keyword=sanitized_query,
                reason=f"AI returned invalid query schema ({parse_err}). Falling back to keyword search.",
            )

    def _parse_and_validate(
        self, raw_query: str, sanitized_query: str, response_content: str
    ) -> StructuredQueryDTO:
        """Parse JSON response and enforce strict typing and domain constraints."""
        clean_json_str = self._clean_json_markdown(response_content)

        # Security check: strictly reject any SQL commands or schema tampering attempts
        if FORBIDDEN_SQL_PATTERNS.search(clean_json_str):
            raise ValueError("Prohibited SQL keyword detected in model output.")

        data: dict[str, Any] = json.loads(clean_json_str)
        if not isinstance(data, dict):
            raise ValueError("Root JSON element must be an object.")

        # Prohibit hallucinated database query fields
        forbidden_keys = {"sql", "query_str", "table", "raw_sql", "query_sql"}
        if any(k in data for k in forbidden_keys):
            raise ValueError("Model hallucinated prohibited database query fields.")

        # Validate min_amount
        min_amount: Optional[Decimal] = None
        if data.get("min_amount") is not None:
            try:
                min_amount = Decimal(str(data["min_amount"]))
                if min_amount < 0:
                    raise ValueError("min_amount must be non-negative.")
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"Invalid min_amount: {exc}") from exc

        # Validate max_amount
        max_amount: Optional[Decimal] = None
        if data.get("max_amount") is not None:
            try:
                max_amount = Decimal(str(data["max_amount"]))
                if max_amount < 0:
                    raise ValueError("max_amount must be non-negative.")
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"Invalid max_amount: {exc}") from exc

        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            # If swapped, normalize
            min_amount, max_amount = max_amount, min_amount

        # Validate start_date
        start_date: Optional[date] = None
        if data.get("start_date"):
            try:
                start_date = date.fromisoformat(str(data["start_date"]))
            except ValueError as exc:
                raise ValueError(f"Invalid start_date format: {exc}") from exc

        # Validate end_date
        end_date: Optional[date] = None
        if data.get("end_date"):
            try:
                end_date = date.fromisoformat(str(data["end_date"]))
            except ValueError as exc:
                raise ValueError(f"Invalid end_date format: {exc}") from exc

        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        # Validate transaction_type
        transaction_type: Optional[str] = None
        raw_type = data.get("transaction_type")
        if raw_type:
            cleaned_type = str(raw_type).strip().upper()
            if cleaned_type not in self.VALID_TYPES:
                raise ValueError(f"Invalid transaction_type: {cleaned_type}")
            transaction_type = cleaned_type

        # Keyword
        raw_kw = data.get("keyword")
        keyword: Optional[str] = str(raw_kw).strip() if raw_kw else None

        # Explanation
        explanation = str(data.get("explanation") or "Translated via NovaBank AI.")

        return StructuredQueryDTO(
            raw_query=raw_query,
            min_amount=min_amount,
            max_amount=max_amount,
            start_date=start_date,
            end_date=end_date,
            transaction_type=transaction_type,
            keyword=keyword,
            is_fallback=False,
            explanation=explanation,
        )

    def _clean_json_markdown(self, text: str) -> str:
        """Strip markdown code blocks if the model wrapped JSON in them."""
        stripped = text.strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return stripped

    def _build_fallback(
        self, raw_query: str, keyword: str, reason: str
    ) -> StructuredQueryDTO:
        """Construct fallback keyword query DTO."""
        return StructuredQueryDTO(
            raw_query=raw_query,
            keyword=keyword,
            is_fallback=True,
            explanation=reason,
        )
