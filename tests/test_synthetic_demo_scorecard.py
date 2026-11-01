"""Tests for synthetic benchmark integrity; no real buyer metrics are implied."""

import json

from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.matching.engine import ExactMatchEngine
from scripts.evaluate_synthetic_demo import (
    BOM_FILENAME,
    ROOT,
    evaluate_synthetic_demo,
    evaluate_synthetic_adversarial_fixtures,
    score_bom_lines,
)


def test_synthetic_demo_scorecard_has_complete_annotated_line_coverage():
    report = evaluate_synthetic_demo()
    assert report["evidence_type"] == "synthetic_ground_truth_not_customer_metrics"
    assert report["scorecard_passed"] is True
    assert report["expected_lines"] == 20
    assert report["detected_lines"] == 20
    assert report["missing_expected_line_numbers"] == []
    assert report["extra_detected_line_numbers"] == []
    assert report["critical_field_checks_total"] == 80
    assert report["catalog_match_checks_total"] == 20
    assert report["rows_with_source_locator"] == 20
    assert report["expected_warnings_missing"] == []
    assert report["line_recall"] == 1.0
    assert report["line_precision"] == 1.0
    assert report["field_accuracy"]["mpn"] == {
        "correct": 20,
        "total": 20,
        "accuracy": 1.0,
    }
    assert report["field_accuracy"]["manufacturer"]["accuracy"] == 1.0
    assert report["field_accuracy"]["quantity"]["accuracy"] == 1.0
    assert report["field_accuracy"]["unit"]["accuracy"] == 1.0
    assert report["false_exact_match_count"] == 0
    assert report["exact_match_precision"] == 1.0
    adversarial = report["adversarial_fixtures"]
    assert adversarial["messy_email"]["line_recall"] == 1.0
    assert adversarial["messy_email"]["line_precision"] == 1.0
    assert adversarial["messy_email"]["expected_warnings_missing"] == []
    assert adversarial["cross_brand_collision"]["passed"] is True
    assert adversarial["duplicate_source_detection"]["passed"] is True
    assert adversarial["quantity_conflict_detection"]["passed"] is True
    assert adversarial["manufacturer_conflict_detection"]["passed"] is True
    json.dumps(report)  # Machine-readable and reproducible.


def test_scorecard_detects_unflagged_quantity_error_in_synthetic_annotation():
    fixture = ROOT / "fixtures" / "rfq_samples" / BOM_FILENAME
    lines = SpreadsheetParser().parse(fixture.read_bytes(), BOM_FILENAME).lines
    reference = {
        "line_number": 1,
        "mpn": "LC1D09BD",
        "oem": "Schneider Electric",
        "qty": 999,
        "uom": "EA",
        "matched_sku": "SKU-SCH-001",
        "expected_match_status": "EXACT_MATCH",
    }
    catalog = CatalogRepository()
    catalog.import_csv(
        (
            ROOT / "fixtures" / "catalogs" / "industrial_components_sample_catalog.csv"
        ).read_bytes()
    )
    report = score_bom_lines([lines[0]], [reference], ExactMatchEngine(catalog))
    assert report["unflagged_critical_mismatch_lines"] == 1
    assert report["critical_field_checks_correct"] == 3
    assert {"line": 1, "field": "quantity", "reason": "mismatch"} in report[
        "comparison_errors"
    ]


def test_scorecard_detects_false_exact_match_against_expected_unknown_part():
    fixture = ROOT / "fixtures" / "rfq_samples" / BOM_FILENAME
    line = SpreadsheetParser().parse(fixture.read_bytes(), BOM_FILENAME).lines[0]
    reference = {
        "line_number": 1,
        "mpn": "UNLISTED-999",
        "oem": "Schneider Electric",
        "qty": 10,
        "uom": "EA",
        "matched_sku": None,
        "expected_match_status": "NO_MATCH",
    }
    catalog = CatalogRepository()
    catalog.import_csv(
        (
            ROOT / "fixtures" / "catalogs" / "industrial_components_sample_catalog.csv"
        ).read_bytes()
    )

    report = score_bom_lines([line], [reference], ExactMatchEngine(catalog))

    assert report["false_exact_match_count"] == 1
    assert report["false_exact_match_line_numbers"] == [1]
    assert report["exact_match_precision"] == 0.0
    assert report["unflagged_critical_mismatch_lines"] == 1


def test_adversarial_evaluator_is_explicitly_synthetic_and_reports_conflict_checks():
    report = evaluate_synthetic_adversarial_fixtures()

    assert (
        report["evidence_type"] == "synthetic_adversarial_fixtures_not_customer_metrics"
    )
    assert report["messy_email"]["field_accuracy"]["quantity"]["accuracy"] == 1.0
    assert report["cross_brand_collision"]["false_exact_collision_mpns"] == []
    assert report["duplicate_source_detection"]["passed"] is True
    assert (
        report["quantity_conflict_detection"]["expected_warning"]
        == "SOURCE_QUANTITY_CONFLICT"
    )
    assert (
        report["manufacturer_conflict_detection"]["expected_warning"]
        == "SOURCE_MANUFACTURER_CONFLICT"
    )
