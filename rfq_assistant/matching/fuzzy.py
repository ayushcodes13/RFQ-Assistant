"""Fuzzy candidate generation using RapidFuzz behind deterministic exact matching.

Safety Invariant:
Similarity is NOT engineering equivalence. RapidFuzz is used purely as a candidate
generator over catalog items. Matches below exact agreement surface as candidates
and must never automatically rewrite an MPN or substitute a component without human review.
"""

import re
from typing import Dict, List, Optional, Tuple
from rapidfuzz import fuzz, process

from rfq_assistant.schemas.models import CatalogItem


def canonical_mpn(value: Optional[str]) -> str:
    """Produces canonical representation of MPN for lookup and candidate indexing.

    Strips whitespace, hyphens, periods, underscores, slashes, and converts to uppercase.
    Original raw part number is always preserved separately.
    """
    if not value:
        return ""
    return re.sub(r"[\s._\-/]", "", value).upper()


class RapidFuzzCandidateEngine:
    """RapidFuzz candidate ranker over catalog items."""

    def __init__(self, catalog_items: Optional[List[CatalogItem]] = None):
        self.catalog_items: List[CatalogItem] = []
        self._canonical_index: Dict[str, List[CatalogItem]] = {}
        self._keys: List[str] = []
        if catalog_items:
            self.index_catalog(catalog_items)

    def index_catalog(self, items: List[CatalogItem]) -> None:
        """Indexes catalog items by canonical MPN."""
        self.catalog_items = list(items)
        self._canonical_index.clear()
        for item in self.catalog_items:
            c_mpn = canonical_mpn(item.manufacturer_part_number)
            if c_mpn:
                self._canonical_index.setdefault(c_mpn, []).append(item)
        self._keys = list(self._canonical_index.keys())

    def find_candidates(
        self,
        requested_mpn: str,
        requested_oem: Optional[str] = None,
        limit: int = 5,
        score_cutoff: float = 65.0,
    ) -> List[Tuple[CatalogItem, float, str]]:
        """Searches catalog for exact matches and ranked fuzzy candidates.

        Returns list of tuples: (CatalogItem, similarity_score, reason)
        """
        query = canonical_mpn(requested_mpn)
        if not query or not self._keys:
            return []

        # 1. Exact canonical match check
        if query in self._canonical_index:
            exact_items = self._canonical_index[query]
            # If OEM provided, prioritize OEM match
            results = []
            for it in exact_items:
                oem_match = (
                    requested_oem
                    and requested_oem.lower() in it.manufacturer.lower()
                )
                reason = "Exact canonical match" + (" with matching OEM" if oem_match else "")
                results.append((it, 100.0, reason))
            return results

        # 2. RapidFuzz candidate retrieval
        # Similarity is candidate evidence, NOT engineering substitution.
        fuzzy_matches = process.extract(
            query,
            self._keys,
            scorer=fuzz.ratio,
            limit=limit,
            score_cutoff=score_cutoff,
        )

        candidates: List[Tuple[CatalogItem, float, str]] = []
        for matched_key, score, _ in fuzzy_matches:
            items = self._canonical_index.get(matched_key, [])
            for item in items:
                reason = f"Candidate string similarity ({score:.1f}% ratio). Requires human engineering review."
                candidates.append((item, float(score), reason))

        # Sort by score descending
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[:limit]
