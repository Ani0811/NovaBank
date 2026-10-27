"""Application BankingService orchestrating financial workflows and transaction boundaries."""

from __future__ import annotations

import threading
from decimal import Decimal
from typing import Any, Callable, Optional, Union

from sqlalchemy.orm import Session, sessionmaker

from novabank.application.dto.transaction_dto import TransactionDTO
from novabank.application.events import DepositCompletedEvent
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountNotFoundError,
    InvalidAmountError,
)
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionType
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_transaction_repository import SQLTransactionRepository


class AccountLockManager:
    """Fine-grained per-account re-entrant mutex for in-process thread serialization."""

    def __init__(self) -> None:
        self._global_lock = threading.Lock()
        self._account_locks: dict[str, threading.RLock] = {}

    def get_lock(self, account_number: str) -> threading.RLock:
        with self._global_lock:
            if account_number not in self._account_locks:
                self._account_locks[account_number] = threading.RLock()
            return self._account_locks[account_number]


class BankingService:
    """Application service coordinating financial transactions, row locking, and domain invariants."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        event_publisher: Optional[Callable[[Any], None]] = None,
    ) -> None:
        self._session_factory = session_factory
        self._lock_manager = AccountLockManager()
        self._listeners: list[Callable[[Any], None]] = []
        if event_publisher is not None:
            self._listeners.append(event_publisher)

    def subscribe(self, listener: Callable[[Any], None]) -> None:
        """Register an event listener/subscriber callback."""
        self._listeners.append(listener)

    def _emit(self, event: Any) -> None:
        """Publish event to all registered listeners."""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                # Listener exceptions must not break core business flows
                pass

    def deposit(
        self,
        account_number: Union[AccountNumber, str],
        amount: Union[Money, Decimal, str, int],
        description: str = "Cash Deposit",
        ref: Optional[str] = None,
        actor: str = "system",
    ) -> TransactionDTO:
        """Atomically deposit funds into a customer account.

        Steps:
        1. Parse and validate account number and monetary amount (> 0).
        2. Acquire fine-grained in-process mutex for the account.
        3. Begin atomic database transaction with pessimistic row lock (SELECT ... FOR UPDATE).
        4. Validate account existence and active status.
        5. Apply credit mutation to Account domain entity (updating balance & version).
        6. Persist updated Account and append immutable Transaction record.
        7. Commit database transaction (or rollback entirely on failure).
        8. Emit DepositCompletedEvent and return TransactionDTO.

        Raises:
            AccountNotFoundError: If account does not exist.
            AccountClosedError: If account is deactivated or closed.
            InvalidAmountError: If amount is non-positive or invalid.
            DuplicateTransactionRefError: If reference is duplicate.
        """
        # 1. Normalize account number string
        if isinstance(account_number, AccountNumber):
            acc_str = account_number.value
        else:
            acc_str = str(account_number).strip().replace("-", "").replace(" ", "")

        # 2. Parse and validate amount
        if isinstance(amount, Money):
            deposit_money = amount
        else:
            try:
                deposit_money = Money(amount, allow_negative=True)
            except Exception as exc:
                raise InvalidAmountError(f"Invalid monetary deposit amount: {amount}") from exc

        if not deposit_money.is_positive():
            raise InvalidAmountError(
                f"Deposit amount must be strictly positive, got {deposit_money.formatted()}"
            )

        # 3. Synchronize in-process concurrent workers for this account
        with self._lock_manager.get_lock(acc_str):
            # 4. Atomic database transaction block
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)

                    # Acquire pessimistic row-level lock
                    account = account_repo.get_by_number_for_update(acc_str)
                    if account is None:
                        raise AccountNotFoundError(acc_str)

                    if not account.is_active:
                        raise AccountClosedError(acc_str)

                    # Domain entity credit execution
                    tx_entity = account.credit(
                        amount=deposit_money,
                        transaction_type=TransactionType.DEPOSIT,
                        description=description,
                        ref=ref,
                        actor=actor,
                    )

                    # Persist changes
                    account_repo.save(account)
                    tx_repo.append(tx_entity)

                    # Prepare DTO and Event before exiting transaction
                    dto = TransactionDTO.from_entity(tx_entity)
                    event = DepositCompletedEvent(
                        account_number=account.account_number.value,
                        amount=deposit_money.amount,
                        balance_after=account.balance.amount,
                        currency=account.balance.currency,
                        transaction_ref=tx_entity.transaction_ref,
                        timestamp=tx_entity.created_at,
                        actor=actor,
                        description=description,
                    )

            # 5. Emit event after transaction commits successfully
            self._emit(event)
            return dto
