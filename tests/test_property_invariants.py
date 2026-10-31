"""Property-based checks for normalization, numeric parsing, and export safety."""

from decimal import Decimal
import math

from hypothesis import given, settings, strategies as st

from rfq_assistant.exports.generator import _safe_csv_cell
from rfq_assistant.ingestion.ai_extraction import _decimal_quantity_as_float
from rfq_assistant.ingestion.parsers.text_parser import TextParser
from rfq_assistant.matching.normalizer import normalize_manufacturer, normalize_mpn


@settings(max_examples=250, deadline=None)
@given(st.one_of(st.none(), st.text(max_size=200)))
def test_mpn_normalization_is_idempotent(value):
    normalized = normalize_mpn(value)
    assert normalize_mpn(normalized) == normalized


@settings(max_examples=250, deadline=None)
@given(st.one_of(st.none(), st.text(max_size=200)))
def test_manufacturer_normalization_is_idempotent(value):
    normalized = normalize_manufacturer(value)
    assert normalize_manufacturer(normalized) == normalized


@settings(max_examples=250, deadline=None)
@given(
    formula_prefix=st.sampled_from(["=", "+", "-", "@"]),
    whitespace=st.text(alphabet=" \t\r\n\ufeff", max_size=8),
    suffix=st.text(max_size=80),
)
def test_formula_leading_untrusted_strings_never_export_as_formulas(
    formula_prefix, whitespace, suffix
):
    value = whitespace + formula_prefix + suffix
    escaped = _safe_csv_cell(value)
    assert isinstance(escaped, str)
    assert escaped.startswith("'")
    assert escaped[0] not in "=+-@"
    assert escaped[1:] == value


@settings(max_examples=250, deadline=None)
@given(
    quantity=st.integers(min_value=1, max_value=1_000_000),
    unit=st.sampled_from(["EA", "PCS", "UNIT", "FT", "M", "SET"]),
)
def test_quantity_unit_parser_preserves_supported_whole_quantities(quantity, unit):
    parsed_quantity, parsed_unit = TextParser._extract_quantity_unit(
        f"PART-123 {quantity} {unit}"
    )
    assert Decimal(str(parsed_quantity)) == Decimal(quantity)
    expected_unit = "EA" if unit in {"PCS", "UNIT"} else unit
    assert parsed_unit == expected_unit


@settings(max_examples=300, deadline=None)
@given(
    quantity=st.decimals(
        min_value=Decimal("0.000001"),
        max_value=Decimal("1000000000000000000000000"),
        allow_nan=False,
        allow_infinity=False,
        places=12,
    )
)
def test_decimal_quantity_conversion_is_exact_or_rejected(quantity):
    try:
        converted = _decimal_quantity_as_float(quantity)
    except ValueError:
        try:
            as_float = float(quantity)
        except OverflowError:
            return
        assert not math.isfinite(as_float) or Decimal(str(as_float)) != quantity
    else:
        assert Decimal(str(converted)) == quantity
