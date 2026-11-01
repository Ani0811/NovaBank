"""Repository interface for audit event logging.

Audit events are strictly append-only and immutable. No modification or deletion
methods are supported or allowed in this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional

from novabank.application.dto.audit_dto import AuditEventDTO


class AuditRepository(ABC):
    """Abstract interface defining append-only audit persistence."""

    @abstractmethod
    def append(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor: str,
        payload: Optional[dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> AuditEventDTO:
        """Persist a new immutable audit record."""

    @abstractmethod
    def get_by_id(self, event_id: int) -> Optional[AuditEventDTO]:
        """Retrieve a specific audit event by primary key ID."""

    @abstractmethod
    def list_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEventDTO], int]:
        """Query paginated audit events with optional multi-criteria filtering.

        Returns:
            Tuple of (list_of_events, total_matching_count).
        """
