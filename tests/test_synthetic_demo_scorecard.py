"""Tests for synthetic benchmark integrity; no real buyer metrics are implied."""

import json

from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.matching.engine import ExactMatchEngine
from scripts.evaluate_synthetic_demo import (
    BOM_FILENAME,
    ROOT,
    evaluate_synthetic_demo,
    score_bom_lines,
)


def test_synthetic_demo_scorecard_has_complete_annotated_line_coverage():
    report = evaluate_synthetic_demo()
    assert report["evidence_type"] == "synthetic_ground_truth_not_customer_metrics"
    assert report["expected_lines"] == 20
    assert report["detected_lines"] == 20
    assert report["missing_expected_line_numbers"] == []
    assert report["extra_detected_line_numbers"] == []
    assert report["critical_field_checks_total"] == 80
    assert report["catalog_match_checks_total"] == 20
    assert report["rows_with_source_locator"] == 20
    assert report["expected_warnings_missing"] == []
    json.dumps(report)  # Machine-readable and reproducible.


def test_scorecard_detects_unflagged_quantity_error_in_synthetic_annotation():
    fixture = ROOT / "fixtures" / "rfq_samples" / BOM_FILENAME
    lines = SpreadsheetParser().parse(fixture.read_bytes(), BOM_FILENAME).lines
    reference = {
        "line_number": 1, "mpn": "LC1D09BD", "oem": "Schneider Electric",
        "qty": 999, "uom": "EA",
        "matched_sku": "SKU-SCH-001", "expected_match_status": "EXACT_MATCH",
    }
    catalog = CatalogRepository()
    catalog.import_csv(
        (ROOT / "fixtures" / "catalogs" / "industrial_components_sample_catalog.csv").read_bytes()
    )
    report = score_bom_lines([lines[0]], [reference], ExactMatchEngine(catalog))
    assert report["unflagged_critical_mismatch_lines"] == 1
    assert report["critical_field_checks_correct"] == 3
    assert {"line": 1, "field": "quantity", "reason": "mismatch"} in report["comparison_errors"]
