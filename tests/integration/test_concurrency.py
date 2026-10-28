"""High-concurrency and stress testing suite for NovaBank transaction engine.

Verifies:
1. Conservation of money under high concurrency.
2. Complete freedom from deadlocks during bi-directional and circular transfers.
3. Strict non-negative balance invariants and overdraft prevention under load.
4. Full audit trail consistency across all account ledgers.
"""

import os
import random
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from novabank.application.dto.transaction_dto import TransactionDTO
from novabank.application.services.banking_service import BankingService
from novabank.domain.entities.account import Account
from novabank.domain.exceptions import InsufficientFundsError
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType
from novabank.infrastructure.db.session import init_database
from novabank.infrastructure.repositories.sql_account_repository import SQLAccountRepository
from novabank.infrastructure.repositories.sql_transaction_repository import SQLTransactionRepository


@pytest.fixture
def stress_db():
    """Create a temporary high-concurrency SQLite database with WAL mode and connection pooling."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name

    engine = create_engine(
        f"sqlite:///{db_path}?timeout=60",
        pool_size=25,
        max_overflow=50,
    )
    with engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
        conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
    init_database(engine)
    session_factory = sessionmaker(bind=engine)

    yield session_factory, engine

    engine.dispose()
    try:
        os.remove(db_path)
        for ext in ["-wal", "-shm"]:
            if os.path.exists(db_path + ext):
                os.remove(db_path + ext)
    except Exception:
        pass


def seed_accounts(
    session_factory: sessionmaker[Session],
    count: int = 5,
    initial_balance: str = "1000.00",
) -> list[str]:
    """Helper to seed accounts in the database."""
    account_numbers: list[str] = []
    with session_factory() as sess:
        with sess.begin():
            repo = SQLAccountRepository(sess)
            for i in range(1, count + 1):
                acc_num = f"50000000000{i}"
                account_numbers.append(acc_num)
                repo.save(
                    Account(
                        account_number=AccountNumber(acc_num),
                        holder_name=f"Stress Customer {i}",
                        dob=date(1990, 1, 1),
                        address_line=f"{i} Financial Blvd",
                        city="New York",
                        state="NY",
                        country="USA",
                        phone_number=f"555000000{i}",
                        balance=Money(initial_balance),
                    )
                )
    return account_numbers


@dataclass
class WorkloadStats:
    """Thread-safe statistics tracking for mixed concurrent workload."""

    total_deposited: Decimal = Decimal("0.00")
    total_withdrawn: Decimal = Decimal("0.00")
    successful_deposits: int = 0
    successful_withdrawals: int = 0
    successful_transfers: int = 0
    rejected_withdrawals: int = 0
    _lock: threading.Lock = threading.Lock()

    def record_deposit(self, amount: Decimal) -> None:
        with self._lock:
            self.total_deposited += amount
            self.successful_deposits += 1

    def record_withdrawal(self, amount: Decimal) -> None:
        with self._lock:
            self.total_withdrawn += amount
            self.successful_withdrawals += 1

    def record_rejected_withdrawal(self) -> None:
        with self._lock:
            self.rejected_withdrawals += 1

    def record_transfer(self) -> None:
        with self._lock:
            self.successful_transfers += 1


def test_multi_account_mixed_workload_stress(stress_db):
    """Stress test: 20 parallel threads executing 120 mixed operations across 5 accounts.

    Verifies:
    1. Perfect conservation of system money.
    2. Zero negative balances.
    3. Exact ledger transition replay matches final balance for all accounts.
    4. Exact pairing of all transfer records.
    """
    session_factory, _ = stress_db
    account_numbers = seed_accounts(session_factory, count=5, initial_balance="1000.00")
    initial_total_system_money = Decimal("5000.00")

    service = BankingService(session_factory=session_factory)
    stats = WorkloadStats()

    # Pre-generate 120 deterministic operations using a fixed random seed
    rng = random.Random(1337)
    operations = []
    for idx in range(120):
        op_type = rng.choice(["deposit", "withdraw", "transfer", "transfer"])
        src = rng.choice(account_numbers)
        amt = Decimal(str(rng.randint(10, 80))) + Decimal("0.00")
        if op_type == "transfer":
            dst = rng.choice([a for a in account_numbers if a != src])
            operations.append((idx, op_type, src, dst, amt))
        else:
            operations.append((idx, op_type, src, None, amt))

    def execute_operation(op):
        idx, op_type, src, dst, amt = op
        if op_type == "deposit":
            dto = service.deposit(
                account_number=src,
                amount=amt,
                description=f"Stress deposit {idx}",
                ref=f"stress-dep-{idx}",
            )
            stats.record_deposit(amt)
            return dto
        elif op_type == "withdraw":
            try:
                dto = service.withdraw(
                    account_number=src,
                    amount=amt,
                    description=f"Stress withdraw {idx}",
                    ref=f"stress-with-{idx}",
                )
                stats.record_withdrawal(amt)
                return dto
            except InsufficientFundsError:
                stats.record_rejected_withdrawal()
                return None
        elif op_type == "transfer":
            try:
                dto = service.transfer(
                    source_account_number=src,
                    destination_account_number=dst,
                    amount=amt,
                    description=f"Stress transfer {idx}",
                    correlation_id=f"stress-tx-{idx}",
                )
                stats.record_transfer()
                return dto
            except InsufficientFundsError:
                stats.record_rejected_withdrawal()
                return None

    # Execute all 120 operations across 20 concurrent threads
    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(execute_operation, operations))

    assert len(results) == 120
    assert stats.successful_deposits + stats.successful_withdrawals + stats.successful_transfers > 0

    # -----------------------------------------------------------------------
    # Invariant Verification in Database
    # -----------------------------------------------------------------------
    with session_factory() as sess:
        account_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        final_accounts = [account_repo.get_by_number(acc_no) for acc_no in account_numbers]
        assert all(acc is not None for acc in final_accounts)

        # 1. Non-negative balance invariant
        for acc in final_accounts:
            assert acc.balance.amount >= Decimal("0.00"), (
                f"Account {acc.account_number.value} has negative balance!"
            )

        # 2. Conservation of Money invariant
        final_total_system_money = sum(acc.balance.amount for acc in final_accounts)
        expected_total_system_money = (
            initial_total_system_money + stats.total_deposited - stats.total_withdrawn
        )
        assert final_total_system_money == expected_total_system_money, (
            f"Money conservation violated! Expected {expected_total_system_money}, got {final_total_system_money}"
        )

        # 3. Ledger audit trail replay for each account
        for acc in final_accounts:
            acc_num = acc.account_number.value
            transactions = tx_repo.list_by_account(acc_num, limit=500, descending=False)

            reconstructed_balance = Decimal("1000.00")
            for tx in transactions:
                if tx.direction == TransactionDirection.CREDIT:
                    reconstructed_balance += tx.amount.amount
                elif tx.direction == TransactionDirection.DEBIT:
                    reconstructed_balance -= tx.amount.amount
                # Invariant: each ledger entry must accurately capture balance_after
                assert tx.balance_after.amount == reconstructed_balance

            # Final ledger reconstructed balance must strictly equal entity balance
            assert reconstructed_balance == acc.balance.amount

        # 4. Pairwise transfer correlation audit
        all_transfers_out = [
            t
            for acc in final_accounts
            for t in tx_repo.list_by_account(acc.account_number.value, limit=500)
            if t.transaction_type == TransactionType.TRANSFER_OUT
        ]
        all_transfers_in = [
            t
            for acc in final_accounts
            for t in tx_repo.list_by_account(acc.account_number.value, limit=500)
            if t.transaction_type == TransactionType.TRANSFER_IN
        ]

        assert len(all_transfers_out) == len(all_transfers_in) == stats.successful_transfers
        in_refs = {t.transaction_ref for t in all_transfers_in}
        for t_out in all_transfers_out:
            corr_id = t_out.transaction_ref.removesuffix("-out")
            matching_in_ref = f"{corr_id}-in"
            assert matching_in_ref in in_refs


def test_single_account_high_contention_hotspot(stress_db):
    """Hotspot stress test: 20 threads simultaneously operating on a single account.

    10 threads deposit $25.00 each ($250.00).
    10 threads withdraw $25.00 each ($250.00).
    Verifies:
    - Zero deadlocks or race conditions.
    - Final balance strictly equals starting balance.
    - Version increments by exactly 20.
    """
    session_factory, _ = stress_db
    account_numbers = seed_accounts(session_factory, count=1, initial_balance="500.00")
    hotspot_acc = account_numbers[0]

    service = BankingService(session_factory=session_factory)

    def worker_action(args):
        idx, action = args
        amt = Decimal("25.00")
        if action == "deposit":
            return service.deposit(
                account_number=hotspot_acc,
                amount=amt,
                ref=f"hotspot-dep-{idx}",
            )
        else:
            return service.withdraw(
                account_number=hotspot_acc,
                amount=amt,
                ref=f"hotspot-with-{idx}",
            )

    tasks = [(i, "deposit") for i in range(10)] + [(i, "withdraw") for i in range(10)]

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(worker_action, tasks))

    assert len(results) == 20

    with session_factory() as sess:
        account_repo = SQLAccountRepository(sess)
        tx_repo = SQLTransactionRepository(sess)

        acc = account_repo.get_by_number(hotspot_acc)
        assert acc is not None
        assert acc.balance == Money("500.00")
        assert acc.version == 21  # 1 initial + 20 updates
        assert tx_repo.count_by_account(hotspot_acc) == 20


def test_circular_ring_transfers_deadlock_freedom(stress_db):
    """Circular transfers: A -> B -> C -> D -> E -> A executed by 25 concurrent threads.

    Guarantees deterministic lock acquisition eliminates circular-wait deadlocks.
    """
    session_factory, _ = stress_db
    accs = seed_accounts(session_factory, count=5, initial_balance="1000.00")
    service = BankingService(session_factory=session_factory)

    # Pairs in a ring: (A->B), (B->C), (C->D), (D->E), (E->A)
    ring_pairs = [
        (accs[0], accs[1]),
        (accs[1], accs[2]),
        (accs[2], accs[3]),
        (accs[3], accs[4]),
        (accs[4], accs[0]),
    ]

    def perform_ring_transfer(args):
        task_id, (src, dst) = args
        return service.transfer(
            source_account_number=src,
            destination_account_number=dst,
            amount=Decimal("20.00"),
            correlation_id=f"ring-tx-{task_id}",
        )

    # 5 runs of each ring pair = 25 concurrent circular transfers
    tasks = [(i, ring_pairs[i % 5]) for i in range(25)]

    with ThreadPoolExecutor(max_workers=15) as executor:
        results = list(executor.map(perform_ring_transfer, tasks))

    assert len(results) == 25

    with session_factory() as sess:
        account_repo = SQLAccountRepository(sess)
        final_balances = [account_repo.get_by_number(a).balance.amount for a in accs]

        # In a balanced ring where every account gives $100 (5*20) and receives $100 (5*20),
        # every account balance should end up back at $1000.00!
        for b in final_balances:
            assert b == Decimal("1000.00")

        # Total system balance remains strictly $5000.00
        assert sum(final_balances) == Decimal("5000.00")


def test_rapid_concurrency_with_overdraft_boundary(stress_db):
    """Boundary test: 20 threads simultaneously try to withdraw $20 from $100 balance.

    Guarantees:
    - Exactly 5 withdrawals succeed.
    - Exactly 15 withdrawals fail with InsufficientFundsError.
    - Final balance is strictly $0.00; never negative.
    """
    session_factory, _ = stress_db
    acc_numbers = seed_accounts(session_factory, count=1, initial_balance="100.00")
    acc_num = acc_numbers[0]
    service = BankingService(session_factory=session_factory)

    def attempt_withdraw(worker_id: int):
        try:
            return service.withdraw(
                account_number=acc_num,
                amount=Decimal("20.00"),
                ref=f"boundary-w-{worker_id}",
            )
        except InsufficientFundsError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(attempt_withdraw, range(20)))

    successes = [r for r in results if isinstance(r, TransactionDTO)]
    failures = [r for r in results if isinstance(r, InsufficientFundsError)]

    assert len(successes) == 5
    assert len(failures) == 15

    with session_factory() as sess:
        acc = SQLAccountRepository(sess).get_by_number(acc_num)
        assert acc.balance == Money("0.00")
        assert acc.version == 6  # 1 initial + 5 successful withdrawals
        assert SQLTransactionRepository(sess).count_by_account(acc_num) == 5
