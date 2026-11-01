"""The parser manifest must account for every non-empty source region."""

import pytest

from rfq_assistant.ingestion.parsers.base import (
    EvidenceSegment,
    ParsedDocumentResult,
    ParsedLineDraft,
    SourceCoverageAccumulator,
    make_coverage_entry,
)
from rfq_assistant.schemas.models import SourceCoverageUnit, SourceLocator


def _coverage(*, structured=0, review=0, filtered=0, nonempty=None):
    locator = SourceLocator(file_name="synthetic.txt")
    if nonempty is None:
        nonempty = structured + review + filtered
    return SourceCoverageUnit(
        unit_id="document",
        locator=locator,
        nonempty_regions=nonempty,
        structured_regions=structured,
        review_regions=review,
        filtered_regions=filtered,
    )


def test_full_source_extraction_can_propose_multiple_rows_from_one_region():
    locator = SourceLocator(file_name="synthetic.txt", text_snippet="MPN-1 2 EA; MPN-2 4 EA")
    result = ParsedDocumentResult(lines=[
        ParsedLineDraft(line_number=1, raw_text="MPN-1 2 EA", source_locator=locator),
        ParsedLineDraft(line_number=2, raw_text="MPN-2 4 EA", source_locator=locator),
    ])
    assert len(result.lines) == 2
    assert all(line.source_locator == locator for line in result.lines)


def test_manifest_must_reconcile_review_regions_to_candidates():
    candidate = EvidenceSegment(
        segment_id="text-row-1",
        locator=SourceLocator(file_name="synthetic.txt", row_number=1),
        text="unmapped request",
    )
    with pytest.raises(ValueError, match="0 review regions for 1 review candidates"):
        ParsedDocumentResult(
            lines=[], candidate_segments=[candidate], source_coverage=[_coverage()]
        )


def test_manifest_rejects_unaccounted_nonempty_regions():
    with pytest.raises(ValueError, match="exactly one"):
        ParsedDocumentResult(
            lines=[],
            source_coverage=[_coverage(nonempty=1)],
        )


def test_coverage_receipts_reject_duplicate_region_ids():
    accumulator = SourceCoverageAccumulator()
    locator = SourceLocator(file_name="synthetic.txt", row_number=1)
    receipt = make_coverage_entry(
        "text-row-1", locator, "part request", "review_candidate", "UNMAPPED"
    )
    accumulator.append(receipt)
    with pytest.raises(ValueError, match="Duplicate source coverage region ID"):
        accumulator.append(receipt)


def test_coverage_receipts_reject_unknown_dispositions():
    accumulator = SourceCoverageAccumulator()
    locator = SourceLocator(file_name="synthetic.txt", row_number=1)
    receipt = make_coverage_entry(
        "text-row-1", locator, "part request", "ignored", "UNKNOWN"
    )
    with pytest.raises(ValueError, match="Unknown source coverage disposition"):
        accumulator.append(receipt)


def test_structured_and_unstructured_sources_report_different_coverage_basis():
    workbook_unit = SourceCoverageUnit(
        unit_id="sheet:Parts",
        locator=SourceLocator(file_name="synthetic.xlsx", sheet_name="Parts"),
        unit_kind="workbook_sheet",
    )
    text_unit = SourceCoverageUnit(
        unit_id="document",
        locator=SourceLocator(file_name="synthetic.txt"),
        unit_kind="text_document",
    )

    assert workbook_unit.coverage_basis == "structured_rows"
    assert text_unit.coverage_basis == "heuristic_regions"
