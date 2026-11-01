"""SQLAlchemy 2.0 implementation of the AuditRepository."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novabank.application.dto.audit_dto import AuditEventDTO
from novabank.domain.repositories.audit_repository import AuditRepository
from novabank.infrastructure.db.models import AuditEventModel


class SQLAuditRepository(AuditRepository):
    """SQLAlchemy repository for append-only audit log records."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def append(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor: str,
        payload: Optional[dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> AuditEventDTO:
        model = AuditEventModel(
            event_type=event_type.strip().upper(),
            entity_type=entity_type.strip().upper(),
            entity_id=str(entity_id).strip(),
            actor=actor.strip(),
            payload=payload or {},
        )
        if timestamp is not None:
            model.timestamp = timestamp

        self._session.add(model)
        self._session.flush()

        return self._to_dto(model)

    def get_by_id(self, event_id: int) -> Optional[AuditEventDTO]:
        model = self._session.get(AuditEventModel, event_id)
        if model is None:
            return None
        return self._to_dto(model)

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
        query = select(AuditEventModel)

        if start_date is not None:
            query = query.where(AuditEventModel.timestamp >= start_date)
        if end_date is not None:
            query = query.where(AuditEventModel.timestamp <= end_date)
        if event_type:
            query = query.where(AuditEventModel.event_type == event_type.strip().upper())
        if entity_id:
            query = query.where(AuditEventModel.entity_id == str(entity_id).strip())
        if actor:
            query = query.where(AuditEventModel.actor == actor.strip())

        # Total count calculation
        count_stmt = select(func.count()).select_from(query.subquery())
        total_count = self._session.scalar(count_stmt) or 0

        # Paginated results ordered latest first
        items_stmt = (
            query.order_by(AuditEventModel.timestamp.desc(), AuditEventModel.event_id.desc())
            .limit(limit)
            .offset(offset)
        )
        models = self._session.scalars(items_stmt).all()

        dtos = [self._to_dto(m) for m in models]
        return dtos, total_count

    @staticmethod
    def _to_dto(model: AuditEventModel) -> AuditEventDTO:
        return AuditEventDTO(
            event_id=model.event_id,
            event_type=model.event_type,
            entity_type=model.entity_type,
            entity_id=model.entity_id,
            actor=model.actor,
            payload=dict(model.payload) if model.payload else {},
            timestamp=model.timestamp,
        )
