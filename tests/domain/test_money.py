"""Comprehensive unit tests for Money value object."""

from decimal import Decimal

import pytest

from novabank.domain.exceptions import (
    CurrencyMismatchError,
    InvalidMoneyError,
    NegativeMoneyError,
)
from novabank.domain.value_objects.money import Money


def test_construction_from_int_str_and_decimal():
    """Verify Money can be created from int, str, and Decimal with 2 decimal quantization."""
    m_int = Money(100)
    m_str = Money("100.00")
    m_dec = Money(Decimal("100.00"))

    assert m_int.amount == Decimal("100.00")
    assert m_str.amount == Decimal("100.00")
    assert m_dec.amount == Decimal("100.00")
    assert m_int == m_str == m_dec


def test_float_input_is_strictly_forbidden():
    """Verify floats are rejected with TypeError to prevent precision loss."""
    with pytest.raises(TypeError, match="Float types are strictly prohibited in Money"):
        Money(10.50)

    with pytest.raises(TypeError, match="Cents must be an integer"):
        Money.from_cents(1050.0)


def test_quantization_and_rounding():
    """Verify rounding follows ROUND_HALF_UP exact decimal arithmetic."""
    # 10.555 -> 10.56
    m1 = Money("10.555")
    assert m1.amount == Decimal("10.56")

    # 10.554 -> 10.55
    m2 = Money("10.554")
    assert m2.amount == Decimal("10.55")


def test_negative_money_rejection_by_default():
    """Verify negative money amounts raise NegativeMoneyError unless explicitly permitted."""
    with pytest.raises(NegativeMoneyError, match="Negative money amount"):
        Money("-0.01")

    # When allow_negative is True
    neg_m = Money("-50.25", allow_negative=True)
    assert neg_m.amount == Decimal("-50.25")
    assert neg_m.is_negative() is True


def test_zero_and_predicates():
    """Verify zero construction and predicate methods."""
    zero_m = Money.zero("USD")
    assert zero_m.is_zero() is True
    assert zero_m.is_positive() is False
    assert zero_m.is_negative() is False

    pos_m = Money("0.01")
    assert pos_m.is_positive() is True
    assert pos_m.is_zero() is False


def test_cents_conversion():
    """Verify exact cents conversion both ways."""
    m = Money("123.45")
    assert m.to_cents() == 12345

    m_from_cents = Money.from_cents(12345)
    assert m_from_cents == m

    zero = Money.from_cents(0)
    assert zero.to_cents() == 0


def test_addition_and_subtraction():
    """Verify arithmetic on same currency."""
    m1 = Money("150.25")
    m2 = Money("49.75")

    total = m1 + m2
    assert total.amount == Decimal("200.00")

    diff = m1 - m2
    assert diff.amount == Decimal("100.50")


def test_subtraction_resulting_in_negative():
    """Verify subtraction resulting in negative balance delta works cleanly."""
    m1 = Money("50.00")
    m2 = Money("75.00")

    diff = m1 - m2
    assert diff.amount == Decimal("-25.00")
    assert diff.is_negative() is True


def test_currency_mismatch_rejection():
    """Verify operating across different currencies raises CurrencyMismatchError."""
    usd = Money("100.00", currency="USD")
    inr = Money("100.00", currency="INR")

    with pytest.raises(CurrencyMismatchError, match="Cannot operate between different currencies"):
        _ = usd + inr

    with pytest.raises(CurrencyMismatchError, match="Cannot operate between different currencies"):
        _ = usd - inr

    with pytest.raises(CurrencyMismatchError, match="Cannot operate between different currencies"):
        _ = usd < inr


def test_multiplication_and_division():
    """Verify multiplication and division by integer and Decimal scalars."""
    m = Money("25.50")

    # Multiply by int
    m_mul_int = m * 3
    assert m_mul_int.amount == Decimal("76.50")

    # Reverse multiplication (3 * m)
    m_rmul = 3 * m
    assert m_rmul.amount == Decimal("76.50")

    # Multiply by Decimal
    m_mul_dec = m * Decimal("1.5")
    assert m_mul_dec.amount == Decimal("38.25")

    # Division by int
    m_div = m / 2
    assert m_div.amount == Decimal("12.75")

    # Division by zero
    with pytest.raises(ZeroDivisionError):
        _ = m / 0

    # Float multiplication prohibited
    with pytest.raises(TypeError, match="Multiplication by float is prohibited"):
        _ = m * 2.5


def test_comparison_operators():
    """Verify exact ordering comparisons."""
    m_small = Money("10.00")
    m_medium = Money("50.00")
    m_large = Money("100.00")

    assert m_small < m_medium < m_large
    assert m_large > m_medium > m_small
    assert m_small <= Money("10.00") <= m_medium
    assert m_large >= Money("100.00") >= m_medium
    assert m_small != m_large
    assert m_small != "10.00"  # Non-Money comparison returns False


def test_immutability():
    """Verify Money instances cannot be mutated in place."""
    m = Money("100.00")

    with pytest.raises(AttributeError, match="Money instances are immutable"):
        m._amount = Decimal("200.00")

    with pytest.raises(AttributeError, match="Money instances are immutable"):
        m.new_attr = "hack"


def test_formatting():
    """Verify string formatting with currency symbols and thousands separators."""
    m_usd = Money("1234567.89", currency="USD")
    assert m_usd.formatted() == "$1,234,567.89"
    assert m_usd.formatted(include_symbol=False) == "1,234,567.89"

    m_inr = Money("50000.00", currency="INR")
    assert m_inr.formatted() == "₹50,000.00"

    m_eur = Money("150.00", currency="EUR")
    assert m_eur.formatted() == "€150.00"


def test_hashing_and_set_membership():
    """Verify Money can be used in sets and as dictionary keys."""
    m1 = Money("100.00", currency="USD")
    m2 = Money("100.00", currency="USD")
    m3 = Money("200.00", currency="USD")

    money_set = {m1, m2, m3}
    assert len(money_set) == 2
    assert m1 in money_set


def test_invalid_currency_code():
    """Verify empty or non-string currency codes raise InvalidMoneyError."""
    with pytest.raises(InvalidMoneyError, match="Currency code must be a non-empty string"):
        Money("10.00", currency="")

    with pytest.raises(InvalidMoneyError, match="Currency code must be a non-empty string"):
        Money("10.00", currency=123)  # type: ignore


def test_invalid_string_construction():
    """Verify malformed numeric strings raise InvalidMoneyError."""
    with pytest.raises(InvalidMoneyError, match="Cannot construct Money from invalid value"):
        Money("invalid_amount")


def test_from_str_with_commas():
    """Verify parsing string containing commas."""
    m = Money.from_str("1,250,500.50")
    assert m.amount == Decimal("1250500.50")
    assert m.formatted() == "$1,250,500.50"


def test_formatted_unknown_currency():
    """Verify formatted output with an unmapped currency code."""
    m = Money("100.00", currency="JPY")
    assert m.formatted() == "JPY 100.00"
    assert m.formatted(include_symbol=False) == "100.00"


def test_invalid_operand_types():
    """Verify adding, multiplying, or dividing with invalid types raises TypeError."""
    m = Money("50.00")

    with pytest.raises(TypeError, match="Cannot perform Money operation with type"):
        _ = m + 10  # type: ignore

    with pytest.raises(TypeError, match="Cannot multiply Money by"):
        _ = m * "two"  # type: ignore

    with pytest.raises(TypeError, match="Cannot divide Money by"):
        _ = m / "two"  # type: ignore


def test_unary_neg_and_abs():
    """Verify unary negation and absolute value."""
    pos = Money("25.00")
    neg = -pos
    assert neg.amount == Decimal("-25.00")
    assert neg.is_negative() is True

    abs_m = abs(neg)
    assert abs_m.amount == Decimal("25.00")
    assert abs_m.is_positive() is True


def test_delattr_and_repr_str():
    """Verify deletion protection, string and repr outputs."""
    m = Money("100.00", currency="USD")
    with pytest.raises(AttributeError, match="Money instances are immutable"):
        del m._amount

    assert repr(m) == "Money(Decimal('100.00'), currency='USD')"
    assert str(m) == "$100.00"
