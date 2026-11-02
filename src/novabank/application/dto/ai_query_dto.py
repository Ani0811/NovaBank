"""Data Transfer Objects for AI-translated transaction search queries."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    from novabank.application.dto.statement_dto import StatementEntryDTO


@dataclass(frozen=True)
class StructuredQueryDTO:
    """Structured, validated query parameters derived from natural language or fallback."""

    raw_query: str
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    transaction_type: Optional[str] = None  # "DEPOSIT", "WITHDRAWAL", "TRANSFER"
    keyword: Optional[str] = None
    is_fallback: bool = False
    explanation: Optional[str] = None

    def matches(self, entry: StatementEntryDTO) -> bool:
        """Evaluate whether a transaction entry satisfies all filter criteria."""
        # 1. Transaction Type filter
        if self.transaction_type:
            if entry.transaction_type.upper() != self.transaction_type.upper():
                return False

        # 2. Min amount
        if self.min_amount is not None:
            if entry.amount < self.min_amount:
                return False

        # 3. Max amount
        if self.max_amount is not None:
            if entry.amount > self.max_amount:
                return False

        # 4. Start date (inclusive)
        if self.start_date is not None:
            if entry.created_at.date() < self.start_date:
                return False

        # 5. End date (inclusive)
        if self.end_date is not None:
            if entry.created_at.date() > self.end_date:
                return False

        # 6. Keyword search (case-insensitive substring in description or reference)
        if self.keyword:
            kw = self.keyword.strip().lower()
            if kw:
                desc_match = kw in entry.description.lower()
                ref_match = kw in entry.transaction_ref.lower()
                if not (desc_match or ref_match):
                    return False

        return True

    def filter_entries(
        self, entries: Sequence[StatementEntryDTO]
    ) -> list[StatementEntryDTO]:
        """Filter a list of StatementEntryDTOs against this structured query."""
        return [e for e in entries if self.matches(e)]

