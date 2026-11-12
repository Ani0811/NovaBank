"""Audit logging service for tracking lifecycle events and compliance trails."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Optional, Union

from sqlalchemy.orm import Session, sessionmaker

from novabank.application.dto.audit_dto import AuditEventDTO
from novabank.application.events import (
    AccountClosedEvent,
    AccountFrozenEvent,
    AccountOpenedEvent,
    AccountUnfrozenEvent,
    BeneficiaryAddedEvent,
    BeneficiaryRemovedEvent,
    DepositCompletedEvent,
    InterestAccruedEvent,
    ProfileUpdatedEvent,
    TransferCompletedEvent,
    WithdrawalCompletedEvent,
)
from novabank.infrastructure.repositories.sql_audit_repository import SQLAuditRepository


class AuditService:
    """Service managing append-only audit event recording and query views."""

    EVENT_ACCOUNT_CREATED = "ACCOUNT_CREATED"
    EVENT_ACCOUNT_UPDATED = "ACCOUNT_UPDATED"
    EVENT_ACCOUNT_CLOSED = "ACCOUNT_CLOSED"
    EVENT_ACCOUNT_FROZEN = "ACCOUNT_FROZEN"
    EVENT_ACCOUNT_UNFROZEN = "ACCOUNT_UNFROZEN"
    EVENT_DEPOSIT = "DEPOSIT"
    EVENT_WITHDRAWAL = "WITHDRAWAL"
    EVENT_TRANSFER = "TRANSFER"
    EVENT_BENEFICIARY_ADDED = "BENEFICIARY_ADDED"
    EVENT_BENEFICIARY_REMOVED = "BENEFICIARY_REMOVED"
    EVENT_INTEREST_ACCRUED = "INTEREST_ACCRUED"

    def __init__(
        self, session_factory: Union[sessionmaker[Session], Callable[[], Session]]
    ) -> None:
        self._session_factory = session_factory

    def record_event(
        self,
        event_type: str,
        entity_type: str,
        entity_id: str,
        actor: str = "system",
        payload: Optional[dict[str, Any]] = None,
        timestamp: Optional[datetime] = None,
    ) -> AuditEventDTO:
        """Explicitly record an audit event."""
        sanitized_payload = self._sanitize_payload(payload)

        with self._session_factory() as session:
            with session.begin():
                repo = SQLAuditRepository(session)
                return repo.append(
                    event_type=event_type,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    actor=actor,
                    payload=sanitized_payload,
                    timestamp=timestamp or datetime.now(timezone.utc),
                )

    def handle_event(self, event: Any) -> Optional[AuditEventDTO]:
        """Lifecycle listener hook mapping application events directly into audit records."""
        if isinstance(event, AccountOpenedEvent):
            return self.record_event(
                event_type=self.EVENT_ACCOUNT_CREATED,
                entity_type="ACCOUNT",
                entity_id=event.account_number,
                actor=event.actor,
                payload={
                    "holder_name": event.holder_name,
                    "initial_deposit": str(event.initial_deposit),
                    "phone_number": event.phone_number,
                    "currency": event.currency,
                },
                timestamp=event.timestamp,
            )

        if isinstance(event, ProfileUpdatedEvent):
            return self.record_event(
                event_type=self.EVENT_ACCOUNT_UPDATED,
                entity_type="ACCOUNT",
                entity_id=event.account_number,
                actor=event.actor,
                payload={
                    "phone_number": event.phone_number,
                    "city": event.city,
                    "state": event.state,
                },
                timestamp=event.timestamp,
            )

        if isinstance(event, AccountClosedEvent):
            return self.record_event(
                event_type=self.EVENT_ACCOUNT_CLOSED,
                entity_type="ACCOUNT",
                entity_id=event.account_number,
                actor=event.actor,
                payload={"reason": event.reason},
                timestamp=event.timestamp,
            )

        if isinstance(event, AccountFrozenEvent):
            return self.record_event(
                event_type=self.EVENT_ACCOUNT_FROZEN,
                entity_type="ACCOUNT",
                entity_id=event.account_number,
                actor=event.actor,
                payload={"reason": event.reason},
                timestamp=event.timestamp,
            )

        if isinstance(event, AccountUnfrozenEvent):
            return self.record_event(
                event_type=self.EVENT_ACCOUNT_UNFROZEN,
                entity_type="ACCOUNT",
                entity_id=event.account_number,
                actor=event.actor,
                payload={"reason": event.reason},
                timestamp=event.timestamp,
            )

        if isinstance(event, DepositCompletedEvent):
            return self.record_event(
                event_type=self.EVENT_DEPOSIT,
                entity_type="TRANSACTION",
                entity_id=event.transaction_ref,
                actor=event.actor,
                payload={
                    "account_number": event.account_number,
                    "amount": str(event.amount),
                    "balance_after": str(event.balance_after),
                    "currency": event.currency,
                    "description": event.description,
                },
                timestamp=event.timestamp,
            )

        if isinstance(event, WithdrawalCompletedEvent):
            return self.record_event(
                event_type=self.EVENT_WITHDRAWAL,
                entity_type="TRANSACTION",
                entity_id=event.transaction_ref,
                actor=event.actor,
                payload={
                    "account_number": event.account_number,
                    "amount": str(event.amount),
                    "balance_after": str(event.balance_after),
                    "currency": event.currency,
                    "description": event.description,
                },
                timestamp=event.timestamp,
            )

        if isinstance(event, TransferCompletedEvent):
            return self.record_event(
                event_type=self.EVENT_TRANSFER,
                entity_type="TRANSACTION",
                entity_id=event.correlation_id,
                actor=event.actor,
                payload={
                    "source_account": event.source_account,
                    "destination_account": event.destination_account,
                    "amount": str(event.amount),
                    "source_balance_after": str(event.source_balance_after),
                    "destination_balance_after": str(event.destination_balance_after),
                    "currency": event.currency,
                    "description": event.description,
                },
                timestamp=event.timestamp,
            )

        if isinstance(event, BeneficiaryAddedEvent):
            return self.record_event(
                event_type=self.EVENT_BENEFICIARY_ADDED,
                entity_type="BENEFICIARY",
                entity_id=f"{event.source_account}->{event.destination_account}",
                actor=event.actor,
                payload={
                    "source_account": event.source_account,
                    "destination_account": event.destination_account,
                    "destination_holder_name": event.destination_holder_name,
                    "nickname": event.nickname,
                },
                timestamp=event.timestamp,
            )

        if isinstance(event, BeneficiaryRemovedEvent):
            return self.record_event(
                event_type=self.EVENT_BENEFICIARY_REMOVED,
                entity_type="BENEFICIARY",
                entity_id=str(event.beneficiary_id),
                actor=event.actor,
                payload={
                    "beneficiary_id": event.beneficiary_id,
                    "source_account": event.source_account,
                    "destination_account": event.destination_account,
                },
                timestamp=event.timestamp,
            )

        if isinstance(event, InterestAccruedEvent):
            return self.record_event(
                event_type=self.EVENT_INTEREST_ACCRUED,
                entity_type="SYSTEM",
                entity_id="BATCH_INTEREST",
                actor=event.actor,
                payload={
                    "accounts_credited": event.accounts_credited,
                    "total_interest_credited": str(event.total_interest_credited),
                    "annual_rate_percentage": str(event.annual_rate_percentage),
                },
                timestamp=event.timestamp,
            )

        return None

    def query_events(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        event_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        actor: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditEventDTO], int]:
        """Query historical audit events with pagination and multi-column criteria."""
        with self._session_factory() as session:
            repo = SQLAuditRepository(session)
            return repo.list_events(
                start_date=start_date,
                end_date=end_date,
                event_type=event_type,
                entity_id=entity_id,
                actor=actor,
                limit=limit,
                offset=offset,
            )

    def get_event(self, event_id: int) -> Optional[AuditEventDTO]:
        """Retrieve single audit entry by primary key."""
        with self._session_factory() as session:
            repo = SQLAuditRepository(session)
            return repo.get_by_id(event_id)

    @classmethod
    def _sanitize_payload(cls, data: Optional[dict[str, Any]]) -> dict[str, Any]:
        """Recursively serialize decimals and complex types to JSON-safe primitives."""
        if not data:
            return {}

        sanitized: dict[str, Any] = {}
        for key, val in data.items():
            if isinstance(val, Decimal):
                sanitized[key] = str(val)
            elif isinstance(val, datetime):
                sanitized[key] = val.isoformat()
            elif isinstance(val, dict):
                sanitized[key] = cls._sanitize_payload(val)
            elif isinstance(val, (list, tuple)):
                sanitized[key] = [str(x) if isinstance(x, Decimal) else x for x in val]
            else:
                sanitized[key] = val
        return sanitized
