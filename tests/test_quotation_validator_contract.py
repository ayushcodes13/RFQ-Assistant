"""Direct tests for every quote validation safety gate."""

from decimal import Decimal

import pytest

from rfq_assistant.quotation.validate import (
    ProposedQuote,
    QuoteLine,
    validate_proposed_quote,
    validate_quote_line,
)


def _valid_line(**changes):
    values = {
        "line_no": 1,
        "requested_mpn": "PN-123",
        "requested_manufacturer": "Synthetic Manufacturer",
        "catalogue_part_id": "SKU-123",
        "quantity": Decimal("2"),
        "unit": "EA",
        "unit_price": Decimal("4.25"),
        "currency": "USD",
        "source_price_id": "catalog-row-1",
        "match_status": "exact",
        "requires_human_review": False,
    }
    values.update(changes)
    return QuoteLine.model_construct(**values)


def test_valid_exact_quote_line_has_no_validation_errors():
    assert validate_quote_line(_valid_line()) == []


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"match_status": "candidate"}, "non-exact status"),
        ({"requires_human_review": True}, "pending reviewer approval"),
        ({"unit_price": None}, "No authoritative unit price"),
        ({"unit_price": Decimal("NaN")}, "Unit price cannot be NaN or Infinite"),
        ({"unit_price": Decimal("-0.01")}, "Unit price cannot be negative"),
        ({"unit_price": "not-a-price"}, "Malformed unit price"),
        ({"source_price_id": None}, "no authoritative source ID"),
        ({"quantity": Decimal("NaN")}, "Quantity cannot be NaN or Infinite"),
        ({"quantity": Decimal("0")}, "Quantity must be greater than zero"),
        ({"quantity": "not-a-quantity"}, "Malformed quantity"),
        ({"currency": None}, "Currency is missing"),
    ],
)
def test_quote_line_invalid_values_are_reported(changes, expected):
    assert any(
        expected in error for error in validate_quote_line(_valid_line(**changes))
    )


def test_quote_validator_rejects_empty_quotes_and_reports_mixed_currency():
    empty = ProposedQuote.model_construct(quote_id="Q-1", case_id="C-1", lines=[])
    assert "Quotation draft contains no line items." in validate_proposed_quote(empty)

    quote = ProposedQuote.model_construct(
        quote_id="Q-2",
        case_id="C-2",
        currency="USD",
        lines=[_valid_line(currency="USD"), _valid_line(line_no=2, currency="EUR")],
    )
    assert any(
        "Mixed currencies detected" in error for error in validate_proposed_quote(quote)
    )
