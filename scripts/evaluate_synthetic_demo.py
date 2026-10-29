"""Reproducible *synthetic-only* RFQ extraction and catalog scorecard.

Run: python -m scripts.evaluate_synthetic_demo

This is NOT a customer result, financial ROI claim, time-savings measurement
or a replacement for blind human review of authorized historical RFQs.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.matching.engine import ExactMatchEngine
from rfq_assistant.matching.normalizer import normalize_manufacturer
from rfq_assistant.schemas.models import RFQLineItem

ROOT = Path(__file__).resolve().parent.parent
BOM_FILENAME = "industrial_control_bom_20lines.xlsx"


def score_bom_lines(
    actual_lines: Sequence[Any],
    expected_lines: List[Dict[str, Any]],
    matcher: ExactMatchEngine,
    filename: str = BOM_FILENAME,
) -> Dict[str, Any]:
    """Compare synthetic annotations with extracted rows, never inferred labels."""
    actual_by_number = {line.line_number: line for line in actual_lines}
    expected_numbers = {int(line["line_number"]) for line in expected_lines}
    missing = sorted(expected_numbers - set(actual_by_number))
    extra = sorted(set(actual_by_number) - expected_numbers)
    field_checks = 0
    correct_fields = 0
    match_checks = 0
    correct_matches = 0
    covered_source = 0
    unflagged_critical = 0
    expected_warnings_missing = []
    errors = []

    for expected in expected_lines:
        line_no = int(expected["line_number"])
        actual = actual_by_number.get(line_no)
        if actual is None:
            errors.append({"line": line_no, "field": "line", "reason": "missing"})
            continue

        comparisons = {
            "mpn": actual.requested_mpn == expected.get("mpn"),
            "manufacturer": normalize_manufacturer(actual.requested_manufacturer)
                            == normalize_manufacturer(expected.get("oem")),
            "quantity": actual.quantity == expected.get("qty"),
            "unit": actual.unit == expected.get("uom"),
        }
        field_checks += len(comparisons)
        correct_fields += sum(comparisons.values())
        mismatched = [field for field, ok in comparisons.items() if not ok]
        for field in mismatched:
            errors.append({"line": line_no, "field": field, "reason": "mismatch"})

        warning_codes = {w.code for w in actual.extraction_warnings}
        if mismatched and not warning_codes:
            unflagged_critical += 1

        match = matcher.match_line(actual.requested_mpn, actual.requested_manufacturer)
        match_checks += 1
        if (
            match.match_status.value == expected.get("expected_match_status")
            and match.selected_sku == expected.get("matched_sku")
        ):
            correct_matches += 1
        else:
            errors.append({"line": line_no, "field": "catalog_match", "reason": "mismatch"})

        locator = actual.source_locator
        if (
            locator.file_name == filename
            and locator.row_number is not None
            and locator.sheet_name
        ):
            covered_source += 1

        warning = expected.get("expected_warning")
        if warning and warning not in warning_codes:
            expected_warnings_missing.append(line_no)

    return {
        "synthetic_fixture": filename,
        "evidence_type": "synthetic_ground_truth_not_customer_metrics",
        "expected_lines": len(expected_lines),
        "detected_lines": len(actual_lines),
        "missing_expected_line_numbers": missing,
        "extra_detected_line_numbers": extra,
        "critical_field_checks_correct": correct_fields,
        "critical_field_checks_total": field_checks,
        "catalog_match_checks_correct": correct_matches,
        "catalog_match_checks_total": match_checks,
        "rows_with_source_locator": covered_source,
        "unflagged_critical_mismatch_lines": unflagged_critical,
        "expected_warnings_missing": expected_warnings_missing,
        "comparison_errors": errors,
    }


def evaluate_synthetic_demo(root: Path = ROOT) -> Dict[str, Any]:
    ground_truth = json.loads(
        (root / "fixtures" / "ground_truth" / "annotations.json").read_text(encoding="utf-8")
    )
    expected = ground_truth["fixtures"][BOM_FILENAME]["lines"]
    catalog = CatalogRepository()
    catalog.import_csv(
        (root / "fixtures" / "catalogs" / "industrial_components_sample_catalog.csv").read_bytes(),
        version="synthetic",
    )
    parsed = SpreadsheetParser().parse(
        (root / "fixtures" / "rfq_samples" / BOM_FILENAME).read_bytes(), BOM_FILENAME,
    )
    return score_bom_lines(parsed.lines, expected, ExactMatchEngine(catalog))


def main():
    print(json.dumps(evaluate_synthetic_demo(), indent=2))


if __name__ == "__main__":
    main()
