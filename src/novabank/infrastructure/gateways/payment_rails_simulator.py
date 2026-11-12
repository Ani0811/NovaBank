"""Simulated Institutional Payment Rails Provider (Card, ACH, FedNow, Wire)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
import re
from typing import Optional

from novabank.domain.entities.payment import PaymentChannel
from novabank.domain.value_objects.money import Money


class PaymentRailsSimulator:
    """Institutional payment gateway rail processor and network clearance simulator."""

    @staticmethod
    def validate_luhn(card_number: str) -> bool:
        """Validate card number using standard Luhn mod 10 checksum algorithm."""
        digits = [int(c) for c in card_number if c.isdigit()]
        if len(digits) < 13 or len(digits) > 19:
            return False

        checksum = 0
        reverse_digits = digits[::-1]
        for idx, digit in enumerate(reverse_digits):
            if idx % 2 == 1:
                doubled = digit * 2
                checksum += doubled - 9 if doubled > 9 else doubled
            else:
                checksum += digit
        return checksum % 10 == 0

    @staticmethod
    def detect_card_brand(card_number: str) -> str:
        """Detect card brand network from IIN/BIN prefix."""
        clean = re.sub(r"\D", "", card_number)
        if not clean:
            return ""
        if clean.startswith("4"):
            return "VISA"
        if (
            any(clean.startswith(str(p)) for p in range(51, 56))
            or any(clean.startswith(str(p)) for p in range(2221, 2721))
        ):
            return "MASTERCARD"
        if clean.startswith(("34", "37")):
            return "AMEX"
        if clean.startswith(("6011", "65")):
            return "DISCOVER"
        return "UNKNOWN"

    @staticmethod
    def validate_expiry(exp_str: str) -> bool:
        """Validate MM/YY or MM/YYYY expiration date against current month/year."""
        clean = exp_str.strip()
        match = re.fullmatch(r"(\d{2})/(\d{2}|\d{4})", clean)
        if not match:
            return False

        month = int(match.group(1))
        year = int(match.group(2))
        if month < 1 or month > 12:
            return False

        if year < 100:
            year += 2000

        now = date.today()
        # Card is valid through the last day of the expiration month
        if year < now.year or (year == now.year and month < now.month):
            return False
        return True

    @staticmethod
    def validate_routing_number(routing: str) -> bool:
        """Validate 9-digit ABA routing transit number using Federal Reserve checksum."""
        clean = re.sub(r"\D", "", routing)
        if len(clean) != 9:
            return False
        d = [int(c) for c in clean]
        checksum = (
            3 * (d[0] + d[3] + d[6])
            + 7 * (d[1] + d[4] + d[7])
            + 1 * (d[2] + d[5] + d[8])
        )
        return checksum % 10 == 0

    @classmethod
    def calculate_interchange_fee(
        cls, channel: PaymentChannel, amount: Money
    ) -> Money:
        """Calculate network interchange and processing fees for a transaction.

        Rate Table:
        - CARD: 2.9% + $0.30
        - ACH: 0.8% (capped at $5.00)
        - FEDNOW: $0.25 flat
        - WIRE: $15.00 flat
        """
        amt = amount.amount
        curr = amount.currency

        if channel == PaymentChannel.CARD:
            fee_val = (amt * Decimal("0.029") + Decimal("0.30")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        elif channel == PaymentChannel.ACH:
            fee_val = min(
                Decimal("5.00"),
                (amt * Decimal("0.008")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            )
        elif channel == PaymentChannel.FEDNOW:
            fee_val = Decimal("0.25")
        elif channel == PaymentChannel.WIRE:
            fee_val = Decimal("15.00")
        else:
            fee_val = Decimal("0.00")

        return Money(fee_val, currency=curr)

    @classmethod
    def process_authorization(
        cls,
        channel: PaymentChannel,
        amount: Money,
        card_number: Optional[str] = None,
        card_exp: Optional[str] = None,
        card_cvv: Optional[str] = None,
        routing_number: Optional[str] = None,
    ) -> tuple[bool, str, Optional[str]]:
        """Simulate real-time payment authorization across payment rails.

        Returns:
            Tuple of (is_approved, auth_code, decline_reason).
        """
        if channel == PaymentChannel.CARD:
            if not card_number:
                return False, "", "Card number is required."
            clean_num = re.sub(r"\D", "", card_number)
            if not cls.validate_luhn(clean_num):
                return False, "", "Invalid card number checksum (Luhn check failed)."

            if card_exp and not cls.validate_expiry(card_exp):
                return False, "", "Card has expired or invalid expiration date."

            if card_cvv:
                clean_cvv = card_cvv.strip()
                if len(clean_cvv) not in (3, 4):
                    return False, "", "Invalid security code (CVV)."

            # Simulation decline test codes based on card ending:
            if clean_num.endswith("0002"):
                return False, "", "Declined by issuer: Insufficient funds in card account."
            if clean_num.endswith("0005"):
                return False, "", "Declined by issuer: Do not honor / suspicious activity."
            if clean_num.endswith("0014"):
                return False, "", "Declined by issuer: Invalid card account status."

            return True, f"AUTH-CRD-{clean_num[-4:]}", None

        elif channel == PaymentChannel.ACH:
            if routing_number:
                clean_rt = re.sub(r"\D", "", routing_number)
                if len(clean_rt) == 9 and not cls.validate_routing_number(clean_rt):
                    return False, "", "Invalid ABA routing transit number."
            return True, f"AUTH-ACH-{amount.amount:.0f}", None

        elif channel == PaymentChannel.FEDNOW:
            return True, "AUTH-FEDNOW-INSTANT", None

        elif channel == PaymentChannel.WIRE:
            return True, "AUTH-WIRE-CLEARED", None

        return True, "AUTH-OK", None
