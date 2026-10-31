"""Safe display helpers for Excel cells used in RFQ evidence rows."""

from __future__ import annotations

import math
import re
from datetime import date, datetime
from typing import Any

_ZERO_PAD_FORMAT = re.compile(r"0+")


def format_excel_value(value: Any, number_format: str | None = None) -> str:
    """Preserve simple Excel zero-padding formats for numeric identifiers.

    This only formats a stored value for display. It never evaluates formulas
    or attempts to implement Excel's general number-format language.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        if (
            isinstance(value, int)
            and value >= 0
            and number_format
            and _ZERO_PAD_FORMAT.fullmatch(number_format)
        ):
            return str(value).zfill(len(number_format))
    return str(value).strip()


def numeric_identifier_precision_risk(value: Any) -> bool:
    """Detect numeric part identifiers beyond Excel's 15-digit precision."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            return False
        value = int(value)
    return len(str(abs(value))) > 15


def render_excel_cell(formula_cell: Any, cached_cell: Any | None = None) -> str:
    """Render a formula and any stored cached result without implying recalculation."""
    value = formula_cell.value
    if getattr(formula_cell, "data_type", None) == "f":
        formula = format_excel_value(value)
        cached = format_excel_value(
            getattr(cached_cell, "value", None),
            getattr(cached_cell, "number_format", None),
        )
        if cached:
            return f"{formula} [cached value, not recalculated: {cached}]"
        return formula
    return format_excel_value(value, getattr(formula_cell, "number_format", None))
