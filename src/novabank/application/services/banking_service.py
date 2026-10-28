"""Application BankingService orchestrating financial workflows and transaction boundaries."""

from __future__ import annotations

import threading
import uuid
from decimal import Decimal
from typing import Any, Callable, Optional, Union

from sqlalchemy.orm import Session, sessionmaker

from novabank.application.dto.transaction_dto import TransactionDTO, TransferResultDTO
from novabank.application.events import (
    DepositCompletedEvent,
    TransferCompletedEvent,
    WithdrawalCompletedEvent,
)
from novabank.domain.exceptions import (
    AccountClosedError,
    AccountNotFoundError,
    CurrencyMismatchError,
    InvalidAmountError,
    SelfTransferError,
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

    def withdraw(
        self,
        account_number: Union[AccountNumber, str],
        amount: Union[Money, Decimal, str, int],
        description: str = "Cash Withdrawal",
        ref: Optional[str] = None,
        actor: str = "system",
    ) -> TransactionDTO:
        """Atomically withdraw funds from a customer account.

        Steps:
        1. Parse and validate account number and monetary amount (> 0).
        2. Acquire fine-grained in-process mutex for the account.
        3. Begin atomic database transaction with pessimistic row lock (SELECT ... FOR UPDATE).
        4. Validate account existence and active status.
        5. Verify sufficient funds (balance >= amount, overdraft protection).
        6. Apply debit mutation to Account domain entity (updating balance & version).
        7. Persist updated Account and append immutable Transaction record.
        8. Commit database transaction (or rollback entirely on failure).
        9. Emit WithdrawalCompletedEvent and return TransactionDTO.

        Raises:
            AccountNotFoundError: If account does not exist.
            AccountClosedError: If account is deactivated or closed.
            InvalidAmountError: If amount is non-positive or invalid.
            InsufficientFundsError: If requested amount exceeds available balance.
            DuplicateTransactionRefError: If reference is duplicate.
        """
        # 1. Normalize account number string
        if isinstance(account_number, AccountNumber):
            acc_str = account_number.value
        else:
            acc_str = str(account_number).strip().replace("-", "").replace(" ", "")

        # 2. Parse and validate amount
        if isinstance(amount, Money):
            withdraw_money = amount
        else:
            try:
                withdraw_money = Money(amount, allow_negative=True)
            except Exception as exc:
                raise InvalidAmountError(f"Invalid monetary withdrawal amount: {amount}") from exc

        if not withdraw_money.is_positive():
            raise InvalidAmountError(
                f"Withdrawal amount must be strictly positive, got {withdraw_money.formatted()}"
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

                    # Domain entity debit execution (checks balance >= amount)
                    tx_entity = account.debit(
                        amount=withdraw_money,
                        transaction_type=TransactionType.WITHDRAWAL,
                        description=description,
                        ref=ref,
                        actor=actor,
                    )

                    # Persist changes
                    account_repo.save(account)
                    tx_repo.append(tx_entity)

                    # Prepare DTO and Event before exiting transaction
                    dto = TransactionDTO.from_entity(tx_entity)
                    event = WithdrawalCompletedEvent(
                        account_number=account.account_number.value,
                        amount=withdraw_money.amount,
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

    def transfer(
        self,
        source_account_number: Union[AccountNumber, str],
        destination_account_number: Union[AccountNumber, str],
        amount: Union[Money, Decimal, str, int],
        description: str = "Account Transfer",
        correlation_id: Optional[str] = None,
        actor: str = "system",
    ) -> TransferResultDTO:
        """Atomically transfer funds between two accounts with deadlock-free dual locking.

        Steps:
        1. Validate source and destination are different accounts (reject self-transfers).
        2. Normalize account numbers and parse monetary amount (> 0).
        3. Acquire fine-grained in-process mutexes in deterministic ascending order.
        4. Begin atomic database transaction.
        5. Acquire pessimistic DB row locks in deterministic ascending order (SELECT ... FOR UPDATE).
        6. Validate existence, active status, currency compatibility, and sufficient funds.
        7. Apply debit mutation to source and credit mutation to destination.
        8. Write two immutable linked transaction records (TRANSFER_OUT and TRANSFER_IN).
        9. Commit database transaction (or rollback entirely on failure).
        10. Emit TransferCompletedEvent and return TransferResultDTO.

        Raises:
            SelfTransferError: If source and destination accounts are identical.
            AccountNotFoundError: If source or destination account does not exist.
            AccountClosedError: If either account is deactivated or closed.
            InvalidAmountError: If amount is non-positive or invalid.
            InsufficientFundsError: If source balance is less than transfer amount.
            CurrencyMismatchError: If account currencies do not match.
            DuplicateTransactionRefError: If correlation ID or transaction ref exists.
        """
        # 1. Normalize account numbers
        if isinstance(source_account_number, AccountNumber):
            src_str = source_account_number.value
        else:
            src_str = str(source_account_number).strip().replace("-", "").replace(" ", "")

        if isinstance(destination_account_number, AccountNumber):
            dst_str = destination_account_number.value
        else:
            dst_str = str(destination_account_number).strip().replace("-", "").replace(" ", "")

        # 2. Reject self-transfer
        if src_str == dst_str:
            raise SelfTransferError(src_str)

        # 3. Parse and validate amount
        if isinstance(amount, Money):
            transfer_money = amount
        else:
            try:
                transfer_money = Money(amount, allow_negative=True)
            except Exception as exc:
                raise InvalidAmountError(f"Invalid monetary transfer amount: {amount}") from exc

        if not transfer_money.is_positive():
            raise InvalidAmountError(
                f"Transfer amount must be strictly positive, got {transfer_money.formatted()}"
            )

        # 4. Deterministic lock ordering (lexicographical) to prevent deadlocks
        first_acc, second_acc = sorted([src_str, dst_str])
        lock_first = self._lock_manager.get_lock(first_acc)
        lock_second = self._lock_manager.get_lock(second_acc)

        corr_id = correlation_id or str(uuid.uuid4())
        src_ref = f"{corr_id}-out"
        dst_ref = f"{corr_id}-in"

        with lock_first, lock_second:
            with self._session_factory() as session:
                with session.begin():
                    account_repo = SQLAccountRepository(session)
                    tx_repo = SQLTransactionRepository(session)

                    # Acquire pessimistic row-level locks in deterministic order
                    first_model = account_repo.get_by_number_for_update(first_acc)
                    second_model = account_repo.get_by_number_for_update(second_acc)

                    accounts_by_num = {
                        first_acc: first_model,
                        second_acc: second_model,
                    }
                    source_account = accounts_by_num[src_str]
                    destination_account = accounts_by_num[dst_str]

                    if source_account is None:
                        raise AccountNotFoundError(src_str)
                    if destination_account is None:
                        raise AccountNotFoundError(dst_str)

                    if not source_account.is_active:
                        raise AccountClosedError(src_str)
                    if not destination_account.is_active:
                        raise AccountClosedError(dst_str)

                    if source_account.balance.currency != destination_account.balance.currency:
                        raise CurrencyMismatchError(
                            f"Source currency '{source_account.balance.currency}' does not "
                            f"match destination currency '{destination_account.balance.currency}'."
                        )

                    # Execute domain mutations: debit source, credit destination
                    src_tx = source_account.debit(
                        amount=transfer_money,
                        transaction_type=TransactionType.TRANSFER_OUT,
                        description=description or f"Transfer to {dst_str}",
                        ref=src_ref,
                        actor=actor,
                    )
                    dst_tx = destination_account.credit(
                        amount=transfer_money,
                        transaction_type=TransactionType.TRANSFER_IN,
                        description=description or f"Transfer from {src_str}",
                        ref=dst_ref,
                        actor=actor,
                    )

                    # Persist account mutations and transaction records
                    account_repo.save(source_account)
                    account_repo.save(destination_account)
                    tx_repo.append(src_tx)
                    tx_repo.append(dst_tx)

                    src_dto = TransactionDTO.from_entity(src_tx)
                    dst_dto = TransactionDTO.from_entity(dst_tx)
                    result_dto = TransferResultDTO(
                        correlation_id=corr_id,
                        source_transaction=src_dto,
                        destination_transaction=dst_dto,
                        amount=transfer_money.amount,
                        currency=transfer_money.currency,
                        timestamp=src_tx.created_at,
                    )

                    event = TransferCompletedEvent(
                        source_account=src_str,
                        destination_account=dst_str,
                        amount=transfer_money.amount,
                        source_balance_after=source_account.balance.amount,
                        destination_balance_after=destination_account.balance.amount,
                        currency=transfer_money.currency,
                        correlation_id=corr_id,
                        timestamp=src_tx.created_at,
                        actor=actor,
                        description=description,
                    )

            # 5. Emit event after transaction commits successfully
            self._emit(event)
            return result_dto
