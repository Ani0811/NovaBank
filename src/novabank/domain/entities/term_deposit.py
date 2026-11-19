"""Certificate of Deposit (CD) and Term Deposit domain entities and lifecycle aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum
from typing import Optional

from novabank.domain.exceptions import (
    InvalidTermDepositTermsError,
    PrematureRedemptionNotAllowedError,
    TermDepositAlreadyClosedError,
    TermDepositError,
)
from novabank.domain.services.term_deposit_calculator import TermDepositCalculator
from novabank.domain.value_objects.account_number import AccountNumber
from novabank.domain.value_objects.money import Money


class TermDepositStatus(str, Enum):
    """Lifecycle status states for Certificate of Deposit vault contracts."""

    ACTIVE = "ACTIVE"
    MATURED = "MATURED"
    PREMATURELY_CLOSED = "PREMATURELY_CLOSED"
    ROLLED_OVER = "ROLLED_OVER"


class TermDepositPayoutFrequency(str, Enum):
    """Disbursement frequency for accrued interest yields."""

    AT_MATURITY = "AT_MATURITY"
    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUALLY = "ANNUALLY"


class TermDepositRolloverOption(str, Enum):
    """Instructions upon reaching certificate maturity."""

    PAYOUT_AND_CLOSE = "PAYOUT_AND_CLOSE"
    PRINCIPAL_AND_INTEREST = "PRINCIPAL_AND_INTEREST"
    PRINCIPAL_ONLY = "PRINCIPAL_ONLY"


@dataclass(frozen=True)
class CDAccrualMilestone:
    """Monthly milestone tracking compounding growth and interest accrual."""

    milestone_index: int
    accrual_date: date
    period_interest: Money
    cumulative_interest: Money
    cumulative_balance: Money


@dataclass
class CertificateOfDeposit:
    """Core aggregate root representing a time-locked deposit vault contract."""

    cd_id: str
    account_number: AccountNumber
    principal_amount: Money
    interest_rate_apy: Decimal
    tenor_months: int
    issue_date: date
    maturity_date: date
    payout_frequency: TermDepositPayoutFrequency = TermDepositPayoutFrequency.AT_MATURITY
    rollover_option: TermDepositRolloverOption = TermDepositRolloverOption.PAYOUT_AND_CLOSE
    accrued_interest: Money = field(default_factory=Money.zero)
    projected_interest_at_maturity: Money = field(default_factory=Money.zero)
    early_withdrawal_penalty_months: int = 3
    status: TermDepositStatus = TermDepositStatus.ACTIVE
    certificate_number: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None
    early_withdrawal_penalty: Optional[Money] = None
    accruals: list[CDAccrualMilestone] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.principal_amount.is_positive():
            raise InvalidTermDepositTermsError("Deposit principal must be strictly positive.")
        if self.principal_amount.amount < Decimal("500.00"):
            raise InvalidTermDepositTermsError("Minimum principal for CD vault issuance is $500.00.")
        if self.tenor_months <= 0 or self.tenor_months > 120:
            raise InvalidTermDepositTermsError(f"Tenor must be between 1 and 120 months, got {self.tenor_months}.")
        if self.interest_rate_apy <= Decimal("0.00") or self.interest_rate_apy > Decimal("30.00"):
            raise InvalidTermDepositTermsError(f"APY rate must be between 0.01% and 30.00%, got {self.interest_rate_apy}%.")
        if self.maturity_date <= self.issue_date:
            raise InvalidTermDepositTermsError("Maturity date must be strictly after issue date.")

        if not self.certificate_number:
            self.certificate_number = f"CD-VLT-{self.cd_id.replace('CD-', '')}"

        if self.projected_interest_at_maturity.is_zero():
            self.projected_interest_at_maturity = TermDepositCalculator.calculate_projected_interest(
                principal=self.principal_amount,
                apy_percentage=self.interest_rate_apy,
                tenor_months=self.tenor_months,
            )

        if not self.accruals:
            self._generate_accrual_milestones()

    def _generate_accrual_milestones(self) -> None:
        """Generate month-by-month accrual progression schedule."""
        milestones: list[CDAccrualMilestone] = []
        p = self.principal_amount.amount
        total_months = self.tenor_months

        for m in range(1, total_months + 1):
            m_date = TermDepositCalculator.add_months(self.issue_date, m)
            # Compute compound value at month m
            years = Decimal(m) / Decimal("12.00")
            rate_factor = Decimal("1.00") + (self.interest_rate_apy / Decimal("100.00"))
            factor_float = float(rate_factor) ** float(years)
            m_balance = (p * Decimal(str(factor_float))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            cum_interest = m_balance - p
            prev_balance = milestones[-1].cumulative_balance.amount if milestones else p
            period_int = m_balance - prev_balance

            milestones.append(
                CDAccrualMilestone(
                    milestone_index=m,
                    accrual_date=m_date,
                    period_interest=Money(max(Decimal("0.00"), period_int)),
                    cumulative_interest=Money(max(Decimal("0.00"), cum_interest)),
                    cumulative_balance=Money(m_balance),
                )
            )
        self.accruals = milestones

    def calculate_accrued_interest(self, as_of_date: Optional[date] = None) -> Money:
        """Calculate live accrued interest up to specified date."""
        target_date = as_of_date or date.today()
        return TermDepositCalculator.calculate_accrued_interest(
            principal=self.principal_amount,
            apy_percentage=self.interest_rate_apy,
            issue_date=self.issue_date,
            as_of_date=target_date,
            maturity_date=self.maturity_date,
        )

    def calculate_early_redemption_preview(self, as_of_date: Optional[date] = None) -> tuple[Money, Money, Money, Money]:
        """Preview early breakage penalty and net payout without changing state.
        
        Returns:
            (principal, accrued_interest, penalty, net_payout)
        """
        target_date = as_of_date or date.today()
        accrued = self.calculate_accrued_interest(target_date)
        penalty = TermDepositCalculator.calculate_early_withdrawal_penalty(
            principal=self.principal_amount,
            apy_percentage=self.interest_rate_apy,
            penalty_months=self.early_withdrawal_penalty_months,
        )

        net_earnings = accrued.amount - penalty.amount
        total_payout = self.principal_amount.amount + net_earnings
        if total_payout < Decimal("0.00"):
            total_payout = Decimal("0.00")

        return (
            self.principal_amount,
            accrued,
            penalty,
            Money(total_payout),
        )

    def mature(self, as_of_date: Optional[date] = None, actor: str = "system") -> Money:
        """Mature the certificate and release total principal + guaranteed interest."""
        if self.status != TermDepositStatus.ACTIVE:
            raise TermDepositAlreadyClosedError(f"Cannot mature CD in status {self.status.value}")

        self.status = TermDepositStatus.MATURED
        self.accrued_interest = self.projected_interest_at_maturity
        self.closed_at = datetime.now(timezone.utc)
        return self.principal_amount + self.projected_interest_at_maturity

    def close_prematurely(self, as_of_date: Optional[date] = None, actor: str = "teller") -> tuple[Money, Money, Money]:
        """Liquidate CD before maturity applying early withdrawal penalty forfeiture.
        
        Returns:
            (principal, net_interest, penalty)
        """
        if self.status != TermDepositStatus.ACTIVE:
            raise TermDepositAlreadyClosedError(f"Cannot break CD in status {self.status.value}")

        target_date = as_of_date or date.today()
        principal, accrued, penalty, net_payout = self.calculate_early_redemption_preview(target_date)

        self.status = TermDepositStatus.PREMATURELY_CLOSED
        self.accrued_interest = accrued
        self.early_withdrawal_penalty = penalty
        self.closed_at = datetime.now(timezone.utc)

        net_interest_amount = accrued.amount - penalty.amount
        net_interest = Money(net_interest_amount, allow_negative=True)

        return principal, net_interest, penalty
