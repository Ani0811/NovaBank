"""ViewModel managing conversational AI assistant interactions, health monitoring, and quick actions."""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Sequence

from PySide6.QtCore import QObject, Signal

from novabank.application.dto.activity_flag_dto import ActivityFlagDTO
from novabank.application.dto.ai_query_dto import StructuredQueryDTO
from novabank.application.services.activity_monitoring_service import ActivityMonitoringService
from novabank.application.services.ai_search_service import AISearchService
from novabank.application.services.ai_summary_service import AISummaryService
from novabank.infrastructure.ai.exceptions import AIError
from novabank.infrastructure.ai.lm_studio_client import LMStudioClient

if TYPE_CHECKING:
    from novabank.application.services.banking_service import BankingService
    from novabank.ui.workers.task_runner import TaskRunner


class AIAssistantViewModel(QObject):
    """ViewModel coordinating conversational AI queries, local LM Studio health, and banking insights."""

    # Signals
    connection_status_changed = Signal(bool, str)  # (is_connected, status_text)
    message_received = Signal(str, str)  # (role: "user" | "assistant", message_text)
    loading_changed = Signal(bool)
    flags_evaluated = Signal(list)  # list[ActivityFlagDTO]
    error_occurred = Signal(str)

    def __init__(
        self,
        lm_client: Optional[LMStudioClient] = None,
        ai_search_service: Optional[AISearchService] = None,
        ai_summary_service: Optional[AISummaryService] = None,
        activity_monitoring_service: Optional[ActivityMonitoringService] = None,
        banking_service: Optional[BankingService] = None,
        task_runner: Optional[TaskRunner] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self.lm_client = lm_client or LMStudioClient()
        self.ai_search_service = ai_search_service or AISearchService(self.lm_client)
        self.ai_summary_service = ai_summary_service or AISummaryService(self.lm_client)
        session_factory = None
        if banking_service:
            try:
                session_factory = getattr(banking_service, "_session_factory", None)
            except AttributeError:
                session_factory = None

        self.activity_monitoring_service = activity_monitoring_service or ActivityMonitoringService(
            session_factory=session_factory,
            lm_client=self.lm_client,
        )
        self.banking_service = banking_service
        self.task_runner = task_runner

        self.is_connected: bool = False
        self.status_message: str = "Checking AI status..."
        self.active_account_number: str = ""
        self.is_loading: bool = False

    def set_services(
        self,
        banking_service: BankingService,
        task_runner: TaskRunner,
        lm_client: Optional[LMStudioClient] = None,
    ) -> None:
        """Inject runtime application dependencies."""
        self.banking_service = banking_service
        self.task_runner = task_runner
        if lm_client:
            self.lm_client = lm_client
            self.ai_search_service = AISearchService(lm_client)
            self.ai_summary_service = AISummaryService(lm_client)
            session_factory = None
            if banking_service:
                try:
                    session_factory = getattr(banking_service, "_session_factory", None)
                except AttributeError:
                    session_factory = None
            self.activity_monitoring_service = ActivityMonitoringService(
                session_factory=session_factory,
                lm_client=lm_client,
            )

    def set_active_account(self, account_number: str) -> None:
        """Set the active account context for statement and flag insights."""
        self.active_account_number = account_number.strip().replace("-", "").replace(" ", "")

    def check_connection(self) -> None:
        """Asynchronously ping LM Studio health check."""
        def _ping() -> bool:
            if not self.lm_client:
                return False
            return self.lm_client.check_health()

        def _on_result(healthy: bool) -> None:
            self.is_connected = healthy
            if healthy:
                self.status_message = "Connected (Local LM Studio)"
            else:
                self.status_message = "Offline (Local Mode Only)"
            self.connection_status_changed.emit(self.is_connected, self.status_message)

        def _on_error(exc: Exception, tb: str) -> None:
            self.is_connected = False
            self.status_message = "Offline (Local Mode Only)"
            self.connection_status_changed.emit(False, self.status_message)

        if self.task_runner:
            self.task_runner.run_async(_ping, on_result=_on_result, on_error=_on_error)
        else:
            try:
                healthy = _ping()
                _on_result(healthy)
            except Exception as e:
                _on_error(e, "")

    def send_user_message(self, user_query: str) -> None:
        """Process natural language user question or search."""
        query = (user_query or "").strip()
        if not query:
            return

        self.message_received.emit("user", query)
        self._set_loading(True)

        def _process() -> str:
            # 1. Translate natural language query to structured filter
            structured = self.ai_search_service.translate_query(query)

            # 2. If active account is available, evaluate filters against account transactions
            if self.active_account_number and self.banking_service:
                try:
                    stmt = self.banking_service.get_statement(self.active_account_number)
                    matching_entries = structured.filter_entries(stmt.entries)

                    summary_lines = [
                        f"📊 **Query Analysis**: {structured.explanation}",
                        f"Found **{len(matching_entries)}** matching transaction(s) for account `{stmt.account_number}`:\n",
                    ]

                    if matching_entries:
                        for entry in matching_entries[:10]:
                            summary_lines.append(
                                f"• `{entry.created_at.strftime('%Y-%m-%d')}`: **{entry.transaction_type}** "
                                f"{entry.formatted_amount} — {entry.description} (Ref: `{entry.transaction_ref}`)"
                            )
                        if len(matching_entries) > 10:
                            summary_lines.append(f"\n*(...and {len(matching_entries) - 10} more)*")
                    else:
                        summary_lines.append("No transactions matched the specified criteria.")

                    return "\n".join(summary_lines)
                except Exception as err:
                    return f"Parsed Query: {structured.explanation}\n(Could not retrieve account ledger: {err})"

            # If no account context is selected, output structured interpretation
            return (
                f"📊 **Structured Filter Translation**:\n"
                f"• Explanation: {structured.explanation}\n"
                f"• Type: {structured.transaction_type or 'All'}\n"
                f"• Min Amount: ${structured.min_amount:,.2f}" if structured.min_amount else ""
                f"• Max Amount: ${structured.max_amount:,.2f}" if structured.max_amount else ""
                f"• Dates: {structured.start_date or 'Any'} to {structured.end_date or 'Any'}\n"
                f"• Keyword: {structured.keyword or 'None'}\n\n"
                f"*Tip: Specify an active account number above to execute this filter against live transaction ledgers.*"
            )

        def _on_success(response_text: str) -> None:
            self._set_loading(False)
            self.message_received.emit("assistant", response_text)

        def _on_error(exc: Exception, tb: str) -> None:
            self._set_loading(False)
            self.message_received.emit(
                "assistant",
                f"An error occurred while processing your request: {exc}",
            )
            self.error_occurred.emit(str(exc))

        if self.task_runner:
            self.task_runner.run_async(_process, on_result=_on_success, on_error=_on_error)
        else:
            try:
                res = _process()
                _on_success(res)
            except Exception as e:
                _on_error(e, "")

    def quick_action_summarize(self, account_number: Optional[str] = None) -> None:
        """Quick Action: Summarize current account statement."""
        target_account = account_number or self.active_account_number
        if not target_account:
            self.message_received.emit(
                "assistant",
                "⚠️ Please enter an Account Number in the input bar above to summarize its statement.",
            )
            return

        self.message_received.emit("user", f"Summarize statement for account {target_account}")
        self._set_loading(True)

        def _run_summary() -> str:
            if not self.banking_service:
                return "Banking service is unavailable."
            stmt = self.banking_service.get_statement(target_account)
            return self.ai_summary_service.summarize_statement(stmt)

        def _on_success(summary_text: str) -> None:
            self._set_loading(False)
            self.message_received.emit("assistant", summary_text)

        def _on_error(exc: Exception, tb: str) -> None:
            self._set_loading(False)
            self.message_received.emit(
                "assistant",
                f"Could not summarize statement: {exc}",
            )

        if self.task_runner:
            self.task_runner.run_async(_run_summary, on_result=_on_success, on_error=_on_error)
        else:
            try:
                res = _run_summary()
                _on_success(res)
            except Exception as e:
                _on_error(e, "")

    def quick_action_find_large_expenses(self, account_number: Optional[str] = None) -> None:
        """Quick Action: Find notable debits and withdrawals."""
        target_account = account_number or self.active_account_number
        if not target_account:
            self.message_received.emit(
                "assistant",
                "⚠️ Please enter an Account Number above to inspect notable expenses.",
            )
            return

        self.message_received.emit(
            "user", f"Find recent large expenses and withdrawals for account {target_account}"
        )
        self._set_loading(True)

        def _run_expenses() -> str:
            if not self.banking_service:
                return "Banking service is unavailable."
            stmt = self.banking_service.get_statement(target_account)
            # Filter debits >= $100.00
            query = StructuredQueryDTO(
                raw_query="withdrawals over $100",
                min_amount=Decimal("100.00"),
                transaction_type="WITHDRAWAL",
            )
            matches = [e for e in stmt.entries if e.debit_amount is not None and e.amount >= Decimal("100.00")]

            if not matches:
                return f"No large expenses (>= $100.00) found for account `{target_account}`."

            lines = [
                f"💸 **Notable Expenses & Outflows** for account `{target_account}` (Total: {len(matches)}):\n"
            ]
            for e in matches[:10]:
                lines.append(
                    f"• **{e.created_at.strftime('%Y-%m-%d')}**: `{e.formatted_debit}` — {e.description} "
                    f"(Balance After: `{e.formatted_balance_after}`)"
                )
            return "\n".join(lines)

        def _on_success(text: str) -> None:
            self._set_loading(False)
            self.message_received.emit("assistant", text)

        def _on_error(exc: Exception, tb: str) -> None:
            self._set_loading(False)
            self.message_received.emit("assistant", f"Failed to retrieve expenses: {exc}")

        if self.task_runner:
            self.task_runner.run_async(_run_expenses, on_result=_on_success, on_error=_on_error)
        else:
            try:
                res = _run_expenses()
                _on_success(res)
            except Exception as e:
                _on_error(e, "")

    def quick_action_explain_flags(self, account_number: Optional[str] = None) -> None:
        """Quick Action: Evaluate deterministic security rules and explain triggered flags."""
        target_account = account_number or self.active_account_number
        if not target_account:
            self.message_received.emit(
                "assistant",
                "⚠️ Please enter an Account Number above to inspect security flags.",
            )
            return

        self.message_received.emit(
            "user", f"Explain active security and compliance flags for account {target_account}"
        )
        self._set_loading(True)

        def _run_flags() -> tuple[list[ActivityFlagDTO], str]:
            flags = self.activity_monitoring_service.evaluate_and_explain(target_account)
            if not flags:
                msg = (
                    f"🛡️ **Security Status: Clean**\n"
                    f"No unusual activity patterns or compliance alerts triggered for account `{target_account}`.\n"
                    f"All transactions adhere to standard velocity and threshold policies."
                )
                return flags, msg

            lines = [
                f"🛡️ **Active Security & Compliance Alerts** ({len(flags)} triggered for account `{target_account}`):\n"
            ]
            for f in flags:
                lines.append(
                    f"• **[{f.severity}] {f.rule_name}** ({f.triggered_at.strftime('%Y-%m-%d')})\n"
                    f"  *{f.description}*\n"
                    f"  **Teller Guidance**: {f.ai_explanation or 'Review ledger transactions.'}\n"
                )
            return flags, "\n".join(lines)

        def _on_success(result: tuple[list[ActivityFlagDTO], str]) -> None:
            flags, msg = result
            self._set_loading(False)
            self.flags_evaluated.emit(flags)
            self.message_received.emit("assistant", msg)

        def _on_error(exc: Exception, tb: str) -> None:
            self._set_loading(False)
            self.message_received.emit("assistant", f"Failed to evaluate security flags: {exc}")

        if self.task_runner:
            self.task_runner.run_async(_run_flags, on_result=_on_success, on_error=_on_error)
        else:
            try:
                res = _run_flags()
                _on_success(res)
            except Exception as e:
                _on_error(e, "")

    def _set_loading(self, loading: bool) -> None:
        self.is_loading = loading
        self.loading_changed.emit(loading)
