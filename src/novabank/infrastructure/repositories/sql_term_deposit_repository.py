"""SQLAlchemy implementation of TermDepositRepositoryInterface."""

from __future__ import annotations

from typing import Optional, Union

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from novabank.domain.entities.term_deposit import CertificateOfDeposit
from novabank.domain.repositories.term_deposit_repository import (
    TermDepositRepositoryInterface,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.infrastructure.db.models import TermDepositModel


class SQLTermDepositRepository(TermDepositRepositoryInterface):
    """SQL repository for persistent Certificate of Deposit vault contracts and accruals."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _normalize(self, account_number: Union[AccountNumber, str]) -> str:
        if isinstance(account_number, AccountNumber):
            return account_number.value
        return str(account_number).strip().replace("-", "").replace(" ", "")

    def save(self, cd: CertificateOfDeposit) -> None:
        """Persist a new or modified Certificate of Deposit record."""
        model = self._session.get(TermDepositModel, cd.cd_id)
        if model is None:
            model = TermDepositModel.from_entity(cd)
            self._session.add(model)
        else:
            model.status = cd.status.value
            model.accrued_interest = cd.accrued_interest.amount
            model.closed_at = cd.closed_at
            model.early_withdrawal_penalty = (
                cd.early_withdrawal_penalty.amount if cd.early_withdrawal_penalty else None
            )
            # Update serialized accrual milestones
            model.accruals_json = [
                {
                    "milestone_index": item.milestone_index,
                    "accrual_date": item.accrual_date.isoformat(),
                    "period_interest": str(item.period_interest.amount),
                    "cumulative_interest": str(item.cumulative_interest.amount),
                    "cumulative_balance": str(item.cumulative_balance.amount),
                }
                for item in cd.accruals
            ]
        self._session.flush()

    def get_by_id(self, cd_id: str) -> Optional[CertificateOfDeposit]:
        """Fetch Certificate of Deposit by unique facility identifier."""
        clean_id = cd_id.strip()
        model = self._session.get(TermDepositModel, clean_id)
        return model.to_entity() if model is not None else None

    def list_term_deposits(
        self,
        account_number: Optional[Union[AccountNumber, str]] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[CertificateOfDeposit], int]:
        """Retrieve paginated Certificate of Deposit records matching optional filter criteria."""
        conditions = []

        if account_number is not None:
            acc_num = self._normalize(account_number)
            if acc_num:
                conditions.append(TermDepositModel.account_number == acc_num)

        if status is not None and status.strip() and status.strip().upper() != "ALL":
            conditions.append(TermDepositModel.status == status.strip().upper())

        # Total count query
        count_stmt = select(func.count(TermDepositModel.cd_id))
        if conditions:
            count_stmt = count_stmt.where(*conditions)
        total_count = int(self._session.execute(count_stmt).scalar() or 0)

        # Paginated data query
        data_stmt = (
            select(TermDepositModel)
            .order_by(TermDepositModel.created_at.desc())
            .offset(offset)
            .limit(max(1, limit))
        )
        if conditions:
            data_stmt = data_stmt.where(*conditions)

        models = self._session.execute(data_stmt).scalars().all()
        return [m.to_entity() for m in models], total_count
