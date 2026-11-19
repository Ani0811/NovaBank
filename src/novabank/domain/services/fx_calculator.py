"""Mathematical engine for Foreign Exchange (FX) cross-currency conversions, spreads, and treasury pricing."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from novabank.domain.exceptions import (
    InvalidFXAmountError,
    UnsupportedCurrencyError,
)
from novabank.domain.value_objects.money import Money

SUPPORTED_CURRENCIES: set[str] = {
    "USD",  # US Dollar (Institutional Base / Reporting)
    "EUR",  # Euro
    "GBP",  # British Pound Sterling
    "JPY",  # Japanese Yen
    "CHF",  # Swiss Franc
    "CAD",  # Canadian Dollar
    "AUD",  # Australian Dollar
    "SGD",  # Singapore Dollar
}

# Default mid-market benchmark rates against USD (1 Unit = X USD or 1 USD = X Units)
# Standard convention: EUR, GBP, AUD quoted as USD per unit; JPY, CHF, CAD, SGD quoted as units per USD
DEFAULT_USD_BENCHMARK_RATES: dict[str, Decimal] = {
    "EUR/USD": Decimal("1.0850"),
    "GBP/USD": Decimal("1.2720"),
    "AUD/USD": Decimal("0.6550"),
    "USD/JPY": Decimal("154.50"),
    "USD/CHF": Decimal("0.8920"),
    "USD/CAD": Decimal("1.3650"),
    "USD/SGD": Decimal("1.3480"),
}


class FXCalculator:
    """Institutional FX rate calculator enforcing currency precision, bid/ask spreads, and cross triangulation."""

    @staticmethod
    def get_currency_decimals(currency: str) -> int:
        """Return ISO decimal exponent (JPY is 0, standard majors are 2)."""
        return 0 if currency.upper() == "JPY" else 2

    @staticmethod
    def quantize_amount(amount: Decimal, currency: str) -> Decimal:
        """Quantize currency amount adhering to banking rounding standards."""
        decimals = FXCalculator.get_currency_decimals(currency)
        if decimals == 0:
            return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @staticmethod
    def quantize_rate(rate: Decimal, quote_currency: str) -> Decimal:
        """Quantize exchange rate (JPY pairs use 3 decimals, other majors use 5 decimals)."""
        if quote_currency.upper() == "JPY":
            return rate.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        return rate.quantize(Decimal("0.00001"), rounding=ROUND_HALF_UP)

    @staticmethod
    def resolve_spot_rate(
        base_currency: str,
        quote_currency: str,
        rates_map: Optional[dict[str, Decimal]] = None,
    ) -> Decimal:
        """Resolve mid-market spot rate between any two supported currencies via direct quote or USD triangulation."""
        base = base_currency.upper()
        quote = quote_currency.upper()

        if base not in SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(base)
        if quote not in SUPPORTED_CURRENCIES:
            raise UnsupportedCurrencyError(quote)

        if base == quote:
            return Decimal("1.00000")

        rates = rates_map or DEFAULT_USD_BENCHMARK_RATES

        # 1. Direct quote
        pair = f"{base}/{quote}"
        if pair in rates:
            return rates[pair]

        # 2. Inverted quote
        inv_pair = f"{quote}/{base}"
        if inv_pair in rates:
            inv_rate = rates[inv_pair]
            if inv_rate > Decimal("0.00"):
                return FXCalculator.quantize_rate(Decimal("1.00000000") / inv_rate, quote)

        # 3. Triangulation via USD
        # Step A: Convert Base to USD
        base_to_usd: Decimal
        if base == "USD":
            base_to_usd = Decimal("1.00000000")
        elif f"{base}/USD" in rates:
            base_to_usd = rates[f"{base}/USD"]
        elif f"USD/{base}" in rates:
            base_to_usd = Decimal("1.00000000") / rates[f"USD/{base}"]
        else:
            raise UnsupportedCurrencyError(f"Cannot resolve rate from {base} to USD")

        # Step B: Convert USD to Quote
        usd_to_quote: Decimal
        if quote == "USD":
            usd_to_quote = Decimal("1.00000000")
        elif f"USD/{quote}" in rates:
            usd_to_quote = rates[f"USD/{quote}"]
        elif f"{quote}/USD" in rates:
            usd_to_quote = Decimal("1.00000000") / rates[f"{quote}/USD"]
        else:
            raise UnsupportedCurrencyError(f"Cannot resolve rate from USD to {quote}")

        spot_rate = base_to_usd * usd_to_quote
        return FXCalculator.quantize_rate(spot_rate, quote)

    @staticmethod
    def calculate_effective_rate(
        spot_rate: Decimal,
        spread_bps: int = 20,
        is_client_buying_target: bool = True,
    ) -> Decimal:
        """Apply institutional spread to spot rate.

        When client exchanges Source for Target:
        - If client is buying target currency (effective conversion):
          Effective rate = Spot * (1 - spread_bps / 10000) so client receives slightly less target currency,
          yielding the bank's spread revenue.
        """
        spread_factor = Decimal(spread_bps) / Decimal("10000.00")
        if is_client_buying_target:
            effective = spot_rate * (Decimal("1.00000000") - spread_factor)
        else:
            effective = spot_rate * (Decimal("1.00000000") + spread_factor)
        return effective

    @staticmethod
    def calculate_fx_fee(
        source_amount: Decimal,
        source_currency: str,
        rates_map: Optional[dict[str, Decimal]] = None,
    ) -> Decimal:
        """Calculate standardized institutional exchange transaction fee ($5.00 min or 0.10%)."""
        # Convert source amount to USD equivalent for min fee threshold
        rate_to_usd = FXCalculator.resolve_spot_rate(source_currency, "USD", rates_map)
        amount_usd = source_amount * rate_to_usd

        min_fee_usd = Decimal("5.00")
        pct_fee_usd = amount_usd * Decimal("0.0010")  # 0.10% (10 bps)
        fee_usd = max(min_fee_usd, pct_fee_usd)

        # Convert back to source currency
        rate_from_usd = FXCalculator.resolve_spot_rate("USD", source_currency, rates_map)
        fee_in_source = fee_usd * rate_from_usd
        return FXCalculator.quantize_amount(fee_in_source, source_currency)

    @staticmethod
    def compute_conversion(
        source_currency: str,
        target_currency: str,
        source_amount: Decimal,
        spread_bps: int = 20,
        rates_map: Optional[dict[str, Decimal]] = None,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
        """Compute complete FX conversion quote.

        Returns:
            (spot_rate, effective_rate, target_amount, fee_amount, spread_revenue_usd)
        """
        if source_amount <= Decimal("0.00"):
            raise InvalidFXAmountError("Exchange amount must be strictly positive.")

        spot_rate = FXCalculator.resolve_spot_rate(source_currency, target_currency, rates_map)
        effective_rate = FXCalculator.calculate_effective_rate(
            spot_rate=spot_rate,
            spread_bps=spread_bps,
            is_client_buying_target=True,
        )

        fee = FXCalculator.calculate_fx_fee(source_amount, source_currency, rates_map)
        net_source = max(Decimal("0.00"), source_amount - fee)
        raw_target = net_source * effective_rate
        target_amount = FXCalculator.quantize_amount(raw_target, target_currency)

        # Calculate bank spread revenue in USD
        spread_diff = (spot_rate - effective_rate) * net_source
        rate_target_to_usd = FXCalculator.resolve_spot_rate(target_currency, "USD", rates_map)
        spread_revenue_usd = (spread_diff * rate_target_to_usd).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        effective_rate_quant = FXCalculator.quantize_rate(effective_rate, target_currency)

        return (
            spot_rate,
            effective_rate_quant,
            target_amount,
            fee,
            max(Decimal("0.00"), spread_revenue_usd),
        )
