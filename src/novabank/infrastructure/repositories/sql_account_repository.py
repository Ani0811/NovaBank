"""SQLAlchemy implementation of the Account repository with parameterized queries."""

from __future__ import annotations

from typing import Optional, Union

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from novabank.domain.entities.account import Account
from novabank.domain.repositories.account_repository import AccountRepositoryInterface
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.infrastructure.db.models import AccountModel


class SQLAccountRepository(AccountRepositoryInterface):
    """Repository handling Account persistence using SQLAlchemy Core/ORM."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _normalize_account_number(self, account_number: Union[AccountNumber, str]) -> str:
        if isinstance(account_number, AccountNumber):
            return account_number.value
        return str(account_number).strip().replace("-", "").replace(" ", "")

    def save(self, account: Account) -> None:
        """Persist new or modified account model."""
        acc_num = account.account_number.value
        model = self._session.get(AccountModel, acc_num)

        if model is None:
            # Create new
            model = AccountModel.from_entity(account)
            self._session.add(model)
        else:
            # Update existing in-place
            model.holder_name = account.holder_name
            model.dob = account.dob
            model.address_line = account.address_line
            model.city = account.city
            model.state = account.state
            model.country = account.country
            model.phone_number = account.phone_number
            model.is_active = account.is_active
            model.balance = account.balance.amount
            model.currency = account.balance.currency
            model.version = account.version
            model.updated_at = account.updated_at

        self._session.flush()

    def get_by_number(self, account_number: Union[AccountNumber, str]) -> Optional[Account]:
        """Fetch account entity by account number."""
        acc_num = self._normalize_account_number(account_number)
        model = self._session.get(AccountModel, acc_num)
        return model.to_entity() if model else None

    def get_by_number_for_update(
        self, account_number: Union[AccountNumber, str]
    ) -> Optional[Account]:
        """Fetch account with pessimistic row lock (SELECT ... FOR UPDATE)."""
        acc_num = self._normalize_account_number(account_number)
        stmt = select(AccountModel).where(AccountModel.account_number == acc_num).with_for_update()
        model = self._session.execute(stmt).scalar_one_or_none()
        return model.to_entity() if model else None

    def list_accounts(
        self,
        search: Optional[str] = None,
        active_only: bool = False,
        is_active: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Account]:
        """Retrieve paginated and filtered accounts with parameterized queries."""
        stmt = select(AccountModel)

        if is_active is not None:
            stmt = stmt.where(AccountModel.is_active.is_(is_active))
        elif active_only:
            stmt = stmt.where(AccountModel.is_active.is_(True))

        if search and search.strip():
            clean_search = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    AccountModel.account_number.like(clean_search),
                    AccountModel.holder_name.ilike(clean_search),
                    AccountModel.phone_number.like(clean_search),
                    AccountModel.city.ilike(clean_search),
                )
            )

        stmt = (
            stmt.order_by(AccountModel.holder_name.asc())
            .offset(max(0, offset))
            .limit(max(1, limit))
        )

        models = self._session.execute(stmt).scalars().all()
        return [m.to_entity() for m in models]

    def count_accounts(
        self,
        search: Optional[str] = None,
        active_only: bool = False,
        is_active: Optional[bool] = None,
    ) -> int:
        """Count total accounts matching filter parameters."""
        stmt = select(func.count(AccountModel.account_number))

        if is_active is not None:
            stmt = stmt.where(AccountModel.is_active.is_(is_active))
        elif active_only:
            stmt = stmt.where(AccountModel.is_active.is_(True))

        if search and search.strip():
            clean_search = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    AccountModel.account_number.like(clean_search),
                    AccountModel.holder_name.ilike(clean_search),
                    AccountModel.phone_number.like(clean_search),
                    AccountModel.city.ilike(clean_search),
                )
            )

        count = self._session.execute(stmt).scalar()
        return int(count or 0)

    def exists(self, account_number: Union[AccountNumber, str]) -> bool:
        """Check whether an account exists."""
        acc_num = self._normalize_account_number(account_number)
        stmt = select(func.count(AccountModel.account_number)).where(
            AccountModel.account_number == acc_num
        )
        count = self._session.execute(stmt).scalar()
        return bool(count and count > 0)
