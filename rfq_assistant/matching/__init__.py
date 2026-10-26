"""Catalog repository and matching engine."""

from rfq_assistant.matching.catalog import CatalogImportError, CatalogRepository
from rfq_assistant.matching.engine import ExactMatchEngine, MatchResult
from rfq_assistant.matching.normalizer import normalize_manufacturer, normalize_mpn

__all__ = [
    "CatalogImportError",
    "CatalogRepository",
    "ExactMatchEngine",
    "MatchResult",
    "normalize_manufacturer",
    "normalize_mpn",
]
