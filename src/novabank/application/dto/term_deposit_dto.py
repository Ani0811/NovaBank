"""Data Transfer Objects for Term Deposits & Certificate of Deposit (CD) Vault."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from novabank.domain.entities.term_deposit import (
    CDAccrualMilestone,
    CertificateOfDeposit,
)


@dataclass(frozen=True)
class CDSimulationRequestDTO:
    """Inbound request to simulate CD compounding and maturity yields."""

    principal: Decimal
    apy_percentage: Decimal
    tenor_months: int
    payout_frequency: str = "AT_MATURITY"


@dataclass(frozen=True)
class CDSimulationResponseDTO:
    """Outbound simulation quote with maturity projection."""

    principal: Decimal
    apy_percentage: Decimal
    tenor_months: int
    projected_interest: Decimal
    total_payout_at_maturity: Decimal
    issue_date: str
    maturity_date: str
    accrual_milestones: list[CDAccrualMilestoneDTO] = field(default_factory=list)

    @property
    def formatted_principal(self) -> str:
        return f"${self.principal:,.2f}"

    @property
    def formatted_projected_interest(self) -> str:
        return f"${self.projected_interest:,.2f}"

    @property
    def formatted_total_interest(self) -> str:
        return self.formatted_projected_interest

    @property
    def formatted_total_payout(self) -> str:
        return f"${self.total_payout_at_maturity:,.2f}"

    @property
    def formatted_projected_maturity_amount(self) -> str:
        return self.formatted_total_payout


@dataclass(frozen=True)
class OpenCDRequestDTO:
    """Inbound request payload to lock funds and issue a Certificate of Deposit."""

    account_number: str
    principal: Decimal
    apy_percentage: Decimal
    tenor_months: int
    payout_frequency: str = "AT_MATURITY"
    rollover_option: str = "PAYOUT_AND_CLOSE"


@dataclass(frozen=True)
class CDAccrualMilestoneDTO:
    """Read-only view representation of a monthly compound milestone."""

    milestone_index: int
    accrual_date: str
    period_interest: Decimal
    cumulative_interest: Decimal
    cumulative_balance: Decimal

    @property
    def milestone_month(self) -> int:
        return self.milestone_index

    @property
    def periodic_interest(self) -> Decimal:
        return self.period_interest

    @property
    def balance_after(self) -> Decimal:
        return self.cumulative_balance

    @property
    def formatted_period_interest(self) -> str:
        return f"${self.period_interest:,.2f}"

    @property
    def formatted_periodic_interest(self) -> str:
        return self.formatted_period_interest

    @property
    def formatted_cumulative_interest(self) -> str:
        return f"${self.cumulative_interest:,.2f}"

    @property
    def formatted_cumulative_balance(self) -> str:
        return f"${self.cumulative_balance:,.2f}"

    @property
    def formatted_balance_after(self) -> str:
        return self.formatted_cumulative_balance

    @classmethod
    def from_entity(cls, entity: CDAccrualMilestone) -> CDAccrualMilestoneDTO:
        return cls(
            milestone_index=entity.milestone_index,
            accrual_date=entity.accrual_date.isoformat(),
            period_interest=entity.period_interest.amount,
            cumulative_interest=entity.cumulative_interest.amount,
            cumulative_balance=entity.cumulative_balance.amount,
        )


@dataclass(frozen=True)
class CertificateOfDepositDTO:
    """Read-only view representation of a Certificate of Deposit vault contract."""

    cd_id: str
    certificate_number: str
    account_number: str
    principal_amount: Decimal
    interest_rate_apy: Decimal
    tenor_months: int
    issue_date: str
    maturity_date: str
    payout_frequency: str
    rollover_option: str
    accrued_interest: Decimal
    projected_interest_at_maturity: Decimal
    total_payout_at_maturity: Decimal
    status: str
    created_at: datetime
    closed_at: Optional[datetime]
    early_withdrawal_penalty: Optional[Decimal]
    accruals: list[CDAccrualMilestoneDTO]

    @property
    def id(self) -> str:
        return self.cd_id

    @property
    def principal(self) -> Decimal:
        return self.principal_amount

    @property
    def apy_percentage(self) -> Decimal:
        return self.interest_rate_apy

    @property
    def formatted_apy(self) -> str:
        return f"{self.interest_rate_apy:.2f}%"

    @property
    def projected_maturity_amount(self) -> Decimal:
        return self.total_payout_at_maturity

    @property
    def formatted_maturity_amount(self) -> str:
        return self.formatted_total_payout

    @property
    def accrual_milestones(self) -> list[CDAccrualMilestoneDTO]:
        return self.accruals

    @property
    def formatted_principal(self) -> str:
        return f"${self.principal_amount:,.2f}"

    @property
    def formatted_accrued_interest(self) -> str:
        return f"${self.accrued_interest:,.2f}"

    @property
    def formatted_projected_interest(self) -> str:
        return f"${self.projected_interest_at_maturity:,.2f}"

    @property
    def formatted_total_payout(self) -> str:
        return f"${self.total_payout_at_maturity:,.2f}"

    @property
    def days_to_maturity(self) -> int:
        mat = date.fromisoformat(self.maturity_date)
        today = date.today()
        return max(0, (mat - today).days)

    @property
    def is_matured(self) -> bool:
        return self.status == "MATURED" or date.fromisoformat(self.maturity_date) <= date.today()

    @property
    def progress_percentage(self) -> float:
        iss = date.fromisoformat(self.issue_date)
        mat = date.fromisoformat(self.maturity_date)
        today = date.today()
        total_days = max(1, (mat - iss).days)
        elapsed = max(0, min(total_days, (today - iss).days))
        return float((Decimal(elapsed) / Decimal(total_days)) * Decimal("100.0"))

    @classmethod
    def from_entity(cls, entity: CertificateOfDeposit) -> CertificateOfDepositDTO:
        total_payout = entity.principal_amount.amount + entity.projected_interest_at_maturity.amount
        return cls(
            cd_id=entity.cd_id,
            certificate_number=entity.certificate_number,
            account_number=entity.account_number.value,
            principal_amount=entity.principal_amount.amount,
            interest_rate_apy=entity.interest_rate_apy,
            tenor_months=entity.tenor_months,
            issue_date=entity.issue_date.isoformat(),
            maturity_date=entity.maturity_date.isoformat(),
            payout_frequency=entity.payout_frequency.value,
            rollover_option=entity.rollover_option.value,
            accrued_interest=entity.accrued_interest.amount,
            projected_interest_at_maturity=entity.projected_interest_at_maturity.amount,
            total_payout_at_maturity=total_payout,
            status=entity.status.value,
            created_at=entity.created_at,
            closed_at=entity.closed_at,
            early_withdrawal_penalty=entity.early_withdrawal_penalty.amount
            if entity.early_withdrawal_penalty
            else None,
            accruals=[CDAccrualMilestoneDTO.from_entity(m) for m in entity.accruals],
        )


@dataclass(frozen=True)
class EarlyRedemptionPreviewDTO:
    """Preview breakdown of early CD liquidation and penalty forfeiture."""

    cd_id: str
    account_number: str
    principal: Decimal
    accrued_interest: Decimal
    penalty: Decimal
    net_payout: Decimal
    certificate_number: str = ""
    days_held: int = 0
    penalty_months: int = 3

    @property
    def formatted_principal(self) -> str:
        return f"${self.principal:,.2f}"

    @property
    def formatted_accrued_interest(self) -> str:
        return f"${self.accrued_interest:,.2f}"

    @property
    def formatted_penalty(self) -> str:
        return f"${self.penalty:,.2f}"

    @property
    def formatted_net_payout(self) -> str:
        return f"${self.net_payout:,.2f}"


@dataclass(frozen=True)
class RedemptionResultDTO:
    """Result payload after completing CD maturity payout or early liquidation."""

    cd_id: str
    certificate_number: str
    account_number: str
    principal: Decimal
    interest_paid: Decimal
    penalty_deducted: Decimal
    net_payout: Decimal
    status: str
    timestamp: datetime
    new_account_balance: Optional[Decimal] = None

    @property
    def formatted_net_payout(self) -> str:
        return f"${self.net_payout:,.2f}"

    @property
    def formatted_new_account_balance(self) -> str:
        if self.new_account_balance is not None:
            return f"${self.new_account_balance:,.2f}"
        return "Updated"
