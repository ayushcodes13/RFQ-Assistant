"""Shared fail-closed RFQ line blockers used for readiness and draft export.

Review state is necessary but not sufficient: an approved line can still
contain unsafe quantities or unresolved high-severity source contradictions.
"""

import math
from typing import List

from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.schemas.enums import MatchStatus, ReviewDecision
from rfq_assistant.schemas.models import RFQLineItem


def stock_shortfall_issue(line: RFQLineItem, catalog: CatalogRepository) -> str | None:
    """Return a blocker when requested quantity exceeds recorded on-hand stock."""
    if line.quantity is None or not line.selected_catalog_sku or line.catalog_rematch_required:
        return None
    try:
        quantity = float(line.quantity)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(quantity):
        return None
    selected_item = catalog.get_by_sku(line.selected_catalog_sku)
    if selected_item is None or selected_item.stock_qty is None or quantity <= selected_item.stock_qty:
        return None
    return f"requested quantity {quantity:g} exceeds catalog stock {selected_item.stock_qty}"


def blocking_line_issues(line: RFQLineItem, catalog: CatalogRepository) -> List[str]:
    """Return human-readable blockers that prohibit a full validated worksheet."""
    issues: List[str] = []

    if line.quantity is None:
        issues.append("missing quantity")
    else:
        try:
            quantity = float(line.quantity)
            if not math.isfinite(quantity) or quantity <= 0:
                issues.append("quantity must be positive and finite")
        except (TypeError, ValueError, OverflowError):
            issues.append("quantity is invalid")

    if not line.unit or not line.unit.strip():
        issues.append("missing unit of measure")

    if line.match_status not in (MatchStatus.EXACT_MATCH, MatchStatus.MANUAL_OVERRIDE):
        issues.append(f"part match is {line.match_status.value}")
    elif not line.selected_catalog_sku or catalog.get_by_sku(line.selected_catalog_sku) is None:
        issues.append("selected catalog SKU is missing or unknown")
    else:
        selected_item = catalog.get_by_sku(line.selected_catalog_sku)
        if (
            line.catalog_rematch_required
            or line.matched_catalog_version != selected_item.catalog_version
        ):
            issues.append("catalog changed since match; rematch required")
        stock_issue = stock_shortfall_issue(line, catalog)
        if stock_issue:
            issues.append(stock_issue)

    for warning in line.extraction_warnings:
        if warning.severity.lower() == "error":
            issues.append(f"unresolved extraction error ({warning.code})")

    if line.review_decision != ReviewDecision.APPROVED:
        issues.append(f"decision is {line.review_decision.value}")

    return issues
