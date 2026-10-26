"""Shared fail-closed RFQ line blockers used for readiness and draft export.

Review state is necessary but not sufficient: an approved line can still
contain unsafe quantities or unresolved high-severity source contradictions.
"""

import math
from typing import List

from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.schemas.enums import MatchStatus, ReviewDecision
from rfq_assistant.schemas.models import RFQLineItem


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

    for warning in line.extraction_warnings:
        if warning.severity.lower() == "error":
            issues.append(f"unresolved extraction error ({warning.code})")

    if line.review_decision != ReviewDecision.APPROVED:
        issues.append(f"decision is {line.review_decision.value}")

    return issues
