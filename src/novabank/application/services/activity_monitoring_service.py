"""Rule-Based Activity Monitoring and AI Flag Explainer Service.

Executes deterministic banking compliance rules against customer ledger activity:
1. Large transaction threshold (>= $10,000.00 BSA/CTR).
2. Rapid consecutive withdrawals (>= 3 debits within 24 hours).
3. Dormant account velocity spike (>= 3 transactions after >= 90 days of inactivity).

Generates explainable, human-in-the-loop narrative explanations for branch tellers via LM Studio
with deterministic template fallbacks. The AI never has authority to freeze or block accounts.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Sequence

from novabank.application.dto.activity_flag_dto import ActivityFlagDTO
from novabank.domain.entities.transaction import Transaction
from novabank.domain.value_objects.transaction_type import TransactionDirection, TransactionType
from novabank.infrastructure.ai.exceptions import AIError
from novabank.infrastructure.ai.lm_studio_client import LMStudioClient
from novabank.infrastructure.ai.sanitizer import PIISanitizer

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

LARGE_TRANSACTION_THRESHOLD = Decimal("10000.00")
RAPID_WITHDRAWAL_WINDOW = timedelta(hours=24)
RAPID_WITHDRAWAL_COUNT = 3
DORMANCY_THRESHOLD_DAYS = 90
BURST_WINDOW = timedelta(hours=48)
BURST_COUNT = 3

SYSTEM_PROMPT = """You are an explainable compliance assistant for NovaBank branch tellers.
Provide a concise 2-sentence explanation of why the deterministic security rule was triggered and what teller verification action is recommended.

Rules:
1. Keep the explanation to exactly 2 sentences.
2. Maintain an objective, professional banking compliance tone.
3. Note that AI has no authority to freeze accounts or block transactions; all action decisions belong to human branch staff.
4. Do not invent or alter amounts or facts outside the provided rule metrics.
"""


class ActivityMonitoringService:
    """Application service for detecting suspicious activity patterns and generating teller explanations."""

    def __init__(
        self,
        session_factory: Optional[sessionmaker[Session]] = None,
        lm_client: Optional[LMStudioClient] = None,
    ) -> None:
        self._session_factory = session_factory
        self._lm_client = lm_client

    def evaluate_rules(self, account_number: str) -> list[ActivityFlagDTO]:
        """Fetch transactions from database and evaluate all deterministic activity rules."""
        if not self._session_factory:
            return []

        from novabank.infrastructure.repositories.sql_transaction_repository import (
            SQLTransactionRepository,
        )

        with self._session_factory() as session:
            tx_repo = SQLTransactionRepository(session)
            # Retrieve recent ledger entries in ascending chronological order
            txs = tx_repo.list_by_account(account_number, limit=200, descending=False)
            return self.evaluate_transactions(account_number, txs)

    def evaluate_transactions(
        self, account_number: str, transactions: Sequence[Transaction]
    ) -> list[ActivityFlagDTO]:
        """Evaluate deterministic rules in-memory against a list of transactions."""
        flags: list[ActivityFlagDTO] = []
        masked_acc = PIISanitizer.mask_account_number(account_number)

        if not transactions:
            return flags

        # Ensure sorted ascending by created_at
        sorted_txs = sorted(transactions, key=lambda t: t.created_at)

        # 1. Rule: Large Transaction (>= $10,000)
        for tx in sorted_txs:
            if tx.amount.amount >= LARGE_TRANSACTION_THRESHOLD:
                flags.append(
                    ActivityFlagDTO(
                        flag_code="LARGE_TRANSACTION",
                        severity="HIGH",
                        rule_name="Large Transaction BSA/CTR Threshold",
                        triggered_at=tx.created_at,
                        description=(
                            f"Single {tx.transaction_type.value} of ${tx.amount.amount:,.2f} "
                            f"exceeds regulatory monitoring threshold of ${LARGE_TRANSACTION_THRESHOLD:,.2f}."
                        ),
                        metrics={
                            "amount": str(tx.amount.amount),
                            "transaction_ref": tx.transaction_ref,
                            "type": tx.transaction_type.value,
                            "threshold": str(LARGE_TRANSACTION_THRESHOLD),
                        },
                        account_number_masked=masked_acc,
                    )
                )

        # 2. Rule: Rapid Consecutive Withdrawals (>= 3 within 24h window)
        debit_txs = [
            t
            for t in sorted_txs
            if t.direction == TransactionDirection.DEBIT
            or t.transaction_type == TransactionType.WITHDRAWAL
        ]

        for i in range(len(debit_txs)):
            window_start = debit_txs[i].created_at
            window_debits = [
                t
                for t in debit_txs[i:]
                if t.created_at <= window_start + RAPID_WITHDRAWAL_WINDOW
            ]
            if len(window_debits) >= RAPID_WITHDRAWAL_COUNT:
                total_withdrawn = sum(
                    (t.amount.amount for t in window_debits), Decimal("0.00")
                )
                flags.append(
                    ActivityFlagDTO(
                        flag_code="RAPID_WITHDRAWALS",
                        severity="MEDIUM",
                        rule_name="Rapid Consecutive Withdrawals",
                        triggered_at=window_debits[-1].created_at,
                        description=(
                            f"{len(window_debits)} withdrawals executed within 24 hours "
                            f"totaling ${total_withdrawn:,.2f}."
                        ),
                        metrics={
                            "withdrawal_count": len(window_debits),
                            "total_withdrawn": str(total_withdrawn),
                            "window_hours": 24,
                        },
                        account_number_masked=masked_acc,
                    )
                )
                break  # Alert once per evaluation window

        # 3. Rule: Dormant Account Velocity Spike (>= 90 days gap followed by >= 3 txs in 48h)
        for i in range(1, len(sorted_txs)):
            gap = sorted_txs[i].created_at - sorted_txs[i - 1].created_at
            if gap >= timedelta(days=DORMANCY_THRESHOLD_DAYS):
                # Check for burst following the dormancy gap
                burst_start = sorted_txs[i].created_at
                burst_txs = [
                    t
                    for t in sorted_txs[i:]
                    if t.created_at <= burst_start + BURST_WINDOW
                ]
                if len(burst_txs) >= BURST_COUNT:
                    flags.append(
                        ActivityFlagDTO(
                            flag_code="DORMANT_ACCOUNT_SPIKE",
                            severity="MEDIUM",
                            rule_name="Dormant Account Velocity Spike",
                            triggered_at=burst_txs[-1].created_at,
                            description=(
                                f"Account exhibited sudden burst of {len(burst_txs)} transactions "
                                f"after {gap.days} days of inactivity."
                            ),
                            metrics={
                                "dormancy_days": gap.days,
                                "burst_count": len(burst_txs),
                                "burst_window_hours": 48,
                            },
                            account_number_masked=masked_acc,
                        )
                    )
                    break

        return flags

    def generate_deterministic_explanation(self, flag: ActivityFlagDTO) -> str:
        """Provide a clear, reliable fallback explanation for teller review."""
        if flag.flag_code == "LARGE_TRANSACTION":
            amt = flag.metrics.get("amount", "0.00")
            tx_type = flag.metrics.get("type", "transaction")
            return (
                f"A single {tx_type} transaction of ${Decimal(amt):,.2f} on account {flag.account_number_masked} "
                f"exceeded the ${LARGE_TRANSACTION_THRESHOLD:,.2f} regulatory threshold. "
                f"Please verify customer identity and complete standard Currency Transaction Report (CTR) filing."
            )
        elif flag.flag_code == "RAPID_WITHDRAWALS":
            count = flag.metrics.get("withdrawal_count", "multiple")
            total = flag.metrics.get("total_withdrawn", "0.00")
            return (
                f"{count} consecutive cash withdrawals totaling ${Decimal(total):,.2f} were executed within 24 hours. "
                f"Staff should review transaction patterns with the customer to ensure card security and prevent skimming."
            )
        elif flag.flag_code == "DORMANT_ACCOUNT_SPIKE":
            days = flag.metrics.get("dormancy_days", "90+")
            burst = flag.metrics.get("burst_count", "multiple")
            return (
                f"Account {flag.account_number_masked} experienced {burst} transactions following {days} days of zero ledger activity. "
                f"Verify account ownership and contact details with the account holder before processing further transactions."
            )
        return (
            f"Rule {flag.rule_name} triggered on account {flag.account_number_masked}. "
            f"Please review recent ledger activity and confirm customer authorization."
        )

    def explain_flag(self, flag: ActivityFlagDTO) -> str:
        """Generate a concise 2-sentence explanation for tellers using local LM Studio."""
        if not self._lm_client:
            return self.generate_deterministic_explanation(flag)

        user_prompt = (
            f"Rule Code: {flag.flag_code}\n"
            f"Rule Name: {flag.rule_name}\n"
            f"Severity: {flag.severity}\n"
            f"Account: {flag.account_number_masked}\n"
            f"Metrics: {flag.metrics}\n"
            f"Summary: {flag.description}\n"
        )

        # Enforce trust boundary: verify no raw unmasked 12-digit account number leaked
        forbidden: list[str] = []
        if flag.account_number_masked and not flag.account_number_masked.startswith("*"):
            forbidden.append(flag.account_number_masked)
        PIISanitizer.assert_pii_free(user_prompt, forbidden_tokens=forbidden)

        try:
            explanation = self._lm_client.chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.1,
                max_tokens=150,
            )
            clean_text = explanation.strip()
            # Basic validation: ensure reasonable length (< 120 words) and no autonomous freeze instructions
            if 10 < len(clean_text.split()) < 120 and "freeze" not in clean_text.lower():
                return clean_text
            return self.generate_deterministic_explanation(flag)
        except AIError as err:
            logger.warning("LM Studio explain_flag call failed: %s", err)
            return self.generate_deterministic_explanation(flag)

    def evaluate_and_explain(self, account_number: str) -> list[ActivityFlagDTO]:
        """Evaluate deterministic rules and populate AI explanations for all triggered flags."""
        flags = self.evaluate_rules(account_number)
        return [f.with_explanation(self.explain_flag(f)) for f in flags]
