"""Deterministic exact MPN and manufacturer matching engine."""

from typing import List, Optional, Tuple
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.matching.normalizer import normalize_manufacturer, normalize_mpn
from rfq_assistant.schemas.enums import MatchStatus
from rfq_assistant.schemas.models import CatalogItem, MatchCandidate


class MatchResult:
    """Outcome of matching an RFQ line against the catalog."""

    def __init__(
        self,
        match_status: MatchStatus,
        candidates: List[MatchCandidate],
        selected_sku: Optional[str] = None,
        explanation: str = "",
    ):
        self.match_status = match_status
        self.candidates = candidates
        self.selected_sku = selected_sku
        self.explanation = explanation


class ExactMatchEngine:
    """Matches requested MPN and manufacturer against authorized catalog items."""

    def __init__(self, catalog: CatalogRepository):
        self.catalog = catalog

    def match_line(
        self, requested_mpn: Optional[str], requested_manufacturer: Optional[str]
    ) -> MatchResult:
        """
        Executes strict matching rules.
        Never hallucinates SKUs or loose substitutes.
        """
        norm_mpn = normalize_mpn(requested_mpn)
        norm_oem = normalize_manufacturer(requested_manufacturer)

        if not norm_mpn:
            return MatchResult(
                match_status=MatchStatus.NO_MATCH,
                candidates=[],
                selected_sku=None,
                explanation="No part number provided.",
            )

        catalog_matches = self.catalog.get_by_normalized_mpn(norm_mpn)

        if not catalog_matches:
            return MatchResult(
                match_status=MatchStatus.NO_MATCH,
                candidates=[],
                selected_sku=None,
                explanation=f"Part number '{requested_mpn}' not found in catalog.",
            )

        # If manufacturer was specified on the RFQ line
        if norm_oem:
            oem_filtered = [
                item for item in catalog_matches
                if normalize_manufacturer(item.manufacturer) == norm_oem
            ]

            if len(oem_filtered) == 1:
                item = oem_filtered[0]
                candidate = MatchCandidate(
                    catalog_item=item,
                    match_type=MatchStatus.EXACT_MATCH,
                    explanation=f"Exact match on manufacturer '{item.manufacturer}' and part number '{item.manufacturer_part_number}'.",
                    confidence_note="Ground truth catalog match.",
                )
                return MatchResult(
                    match_status=MatchStatus.EXACT_MATCH,
                    candidates=[candidate],
                    selected_sku=item.internal_sku,
                    explanation="Exact match.",
                )

            elif len(oem_filtered) > 1:
                # Multiple SKUs for the same OEM and MPN (catalog ambiguity)
                candidates = [
                    MatchCandidate(
                        catalog_item=item,
                        match_type=MatchStatus.COLLISION,
                        explanation=f"Duplicate catalog record for SKU {item.internal_sku}.",
                        confidence_note="Requires manual SKU selection.",
                    )
                    for item in oem_filtered
                ]
                return MatchResult(
                    match_status=MatchStatus.COLLISION,
                    candidates=candidates,
                    selected_sku=None,
                    explanation="Multiple internal SKUs for this manufacturer and part number.",
                )

            else:
                # Part number exists in catalog, but under different manufacturer(s)
                candidates = [
                    MatchCandidate(
                        catalog_item=item,
                        match_type=MatchStatus.COLLISION,
                        explanation=f"Catalog has this MPN under manufacturer '{item.manufacturer}' instead of requested '{requested_manufacturer}'.",
                        confidence_note="Brand mismatch collision.",
                    )
                    for item in catalog_matches
                ]
                return MatchResult(
                    match_status=MatchStatus.COLLISION,
                    candidates=candidates,
                    selected_sku=None,
                    explanation=f"Part number '{requested_mpn}' exists in catalog under different manufacturer(s).",
                )

        else:
            # Manufacturer NOT specified on RFQ line (Scenario 3)
            if len(catalog_matches) == 1:
                item = catalog_matches[0]
                candidate = MatchCandidate(
                    catalog_item=item,
                    match_type=MatchStatus.COLLISION,
                    explanation=f"Found under manufacturer '{item.manufacturer}', but manufacturer was omitted from RFQ. Confirmation required.",
                    confidence_note="Unspecified OEM.",
                )
                return MatchResult(
                    match_status=MatchStatus.COLLISION,
                    candidates=[candidate],
                    selected_sku=None,
                    explanation="Manufacturer omitted from request. Human confirmation required.",
                )
            else:
                oems = {item.manufacturer for item in catalog_matches}
                candidates = [
                    MatchCandidate(
                        catalog_item=item,
                        match_type=MatchStatus.COLLISION,
                        explanation=f"Candidate from manufacturer '{item.manufacturer}'.",
                        confidence_note="Cross-brand collision.",
                    )
                    for item in catalog_matches
                ]
                return MatchResult(
                    match_status=MatchStatus.COLLISION,
                    candidates=candidates,
                    selected_sku=None,
                    explanation=f"Part number exists under multiple manufacturers ({', '.join(sorted(oems))}). Selection required.",
                )
