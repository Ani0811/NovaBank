"""Data Transfer Objects for Audit logging and compliance inspection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class AuditEventDTO:
    """Read-only view of a recorded audit event."""

    event_id: int
    event_type: str
    entity_type: str
    entity_id: str
    actor: str
    payload: dict[str, Any]
    timestamp: datetime

    @property
    def formatted_timestamp(self) -> str:
        """Format timestamp as standard ISO string."""
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S")

    @property
    def formatted_json(self) -> str:
        """Format payload as indented JSON string for UI inspection."""
        return json.dumps(self.payload or {}, indent=2, default=str)
