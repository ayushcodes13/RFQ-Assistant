"""Reproducible *synthetic-only* RFQ extraction and catalog scorecard.

Run: python -m scripts.evaluate_synthetic_demo

This is NOT a customer result, financial ROI claim, time-savings measurement
or a replacement for blind human review of authorized historical RFQs.
"""

import json
from tempfile import TemporaryDirectory
from pathlib import Path
from typing import Any, Dict, List, Sequence

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.ingestion.parsers.text_parser import TextParser
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.matching.engine import ExactMatchEngine
from rfq_assistant.matching.normalizer import normalize_manufacturer

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
    field_correct = {"mpn": 0, "manufacturer": 0, "quantity": 0, "unit": 0}
    match_checks = 0
    correct_matches = 0
    covered_source = 0
    unflagged_critical = 0
    expected_warnings_missing = []
    errors = []
    false_exact_lines = []

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
        for field, correct in comparisons.items():
            field_correct[field] += int(correct)
        mismatched = [field for field, ok in comparisons.items() if not ok]
        for field in mismatched:
            errors.append({"line": line_no, "field": field, "reason": "mismatch"})

        warning_codes = {w.code for w in actual.extraction_warnings}
        if mismatched and not warning_codes:
            unflagged_critical += 1

        match = matcher.match_line(actual.requested_mpn, actual.requested_manufacturer)
        match_checks += 1
        expected_status = expected.get("expected_match_status")
        expected_sku = expected.get("matched_sku")
        if (
            match.match_status.value == expected_status
            and match.selected_sku == expected_sku
        ):
            correct_matches += 1
        else:
            errors.append(
                {"line": line_no, "field": "catalog_match", "reason": "mismatch"}
            )
        if match.match_status.value == "EXACT_MATCH" and (
            expected_status != "EXACT_MATCH"
            or not comparisons["mpn"]
            or not comparisons["manufacturer"]
            or match.selected_sku != expected_sku
        ):
            false_exact_lines.append(line_no)

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

    field_accuracy = {
        field: {
            "correct": correct,
            "total": len(expected_lines),
            "accuracy": correct / len(expected_lines) if expected_lines else None,
        }
        for field, correct in field_correct.items()
    }
    expected_count = len(expected_numbers)
    detected_expected_count = len(expected_numbers & set(actual_by_number))
    for line_number, line in actual_by_number.items():
        if line_number in expected_numbers:
            continue
        match = matcher.match_line(line.requested_mpn, line.requested_manufacturer)
        if match.match_status.value == "EXACT_MATCH":
            false_exact_lines.append(line_number)
    exact_match_count = sum(
        matcher.match_line(
            line.requested_mpn, line.requested_manufacturer
        ).match_status.value
        == "EXACT_MATCH"
        for line in actual_lines
    )
    detected_line_count = len(actual_lines)
    return {
        "synthetic_fixture": filename,
        "evidence_type": "synthetic_ground_truth_not_customer_metrics",
        "expected_lines": len(expected_lines),
        "detected_lines": len(actual_lines),
        "line_recall": detected_expected_count / expected_count
        if expected_count
        else None,
        "line_precision": (
            detected_expected_count / detected_line_count
            if detected_line_count
            else None
        ),
        "field_accuracy": field_accuracy,
        "missing_expected_line_numbers": missing,
        "extra_detected_line_numbers": extra,
        "critical_field_checks_correct": correct_fields,
        "critical_field_checks_total": field_checks,
        "catalog_match_checks_correct": correct_matches,
        "catalog_match_checks_total": match_checks,
        "false_exact_match_count": len(false_exact_lines),
        "false_exact_match_line_numbers": sorted(false_exact_lines),
        "exact_match_count": exact_match_count,
        "exact_match_precision": (
            (exact_match_count - len(false_exact_lines)) / exact_match_count
            if exact_match_count
            else None
        ),
        "rows_with_source_locator": covered_source,
        "unflagged_critical_mismatch_lines": unflagged_critical,
        "expected_warnings_missing": expected_warnings_missing,
        "comparison_errors": errors,
    }


def _score_text_fixture(
    filename: str,
    expected_items: List[Dict[str, Any]],
    root: Path,
    matcher: ExactMatchEngine,
) -> Dict[str, Any]:
    parsed = TextParser().parse(
        (root / "fixtures" / "rfq_samples" / filename).read_bytes(), filename
    )
    actual_by_number = {line.line_number: line for line in parsed.lines}
    missing = []
    field_checks = {"mpn": [0, 0], "manufacturer": [0, 0], "quantity": [0, 0]}
    expected_warnings_missing = []
    false_exact_lines = []
    catalog_match_checks = 0
    catalog_match_correct = 0
    unflagged_critical_lines = []
    comparison_errors = []

    for line_number, expected in enumerate(expected_items, start=1):
        actual = actual_by_number.get(line_number)
        if actual is None:
            missing.append(line_number)
            comparison_errors.append({"line": line_number, "reason": "missing"})
            continue
        warning_codes = {warning.code for warning in actual.extraction_warnings}
        mismatched = []
        for field, attribute, expected_field in (
            ("mpn", "requested_mpn", "mpn"),
            ("manufacturer", "requested_manufacturer", "oem"),
            ("quantity", "quantity", "qty"),
        ):
            if expected_field not in expected:
                continue
            field_checks[field][1] += 1
            actual_value = getattr(actual, attribute)
            expected_value = expected[expected_field]
            if field == "manufacturer":
                correct = normalize_manufacturer(
                    actual_value
                ) == normalize_manufacturer(expected_value)
            else:
                correct = actual_value == expected_value
            if correct:
                field_checks[field][0] += 1
            else:
                mismatched.append(field)
                comparison_errors.append(
                    {"line": line_number, "field": field, "reason": "mismatch"}
                )
        if mismatched and not warning_codes:
            unflagged_critical_lines.append(line_number)
        expected_warning = expected.get("expected_warning")
        if expected_warning and expected_warning not in warning_codes:
            expected_warnings_missing.append(line_number)
        if (
            "raw_desc" in expected
            and expected["raw_desc"].casefold() not in actual.raw_text.casefold()
        ):
            comparison_errors.append(
                {"line": line_number, "field": "raw_desc", "reason": "mismatch"}
            )

        match = matcher.match_line(actual.requested_mpn, actual.requested_manufacturer)
        catalog_match_checks += 1
        expected_match_status = (
            "NO_MATCH" if expected.get("expected_warning") else "EXACT_MATCH"
        )
        if match.match_status.value == expected_match_status:
            catalog_match_correct += 1
        if match.match_status.value == "EXACT_MATCH" and (
            expected_match_status != "EXACT_MATCH"
            or any(field in mismatched for field in ("mpn", "manufacturer"))
        ):
            false_exact_lines.append(line_number)

    field_accuracy = {
        field: {
            "correct": values[0],
            "total": values[1],
            "accuracy": values[0] / values[1] if values[1] else None,
        }
        for field, values in field_checks.items()
    }
    expected_count = len(expected_items)
    detected_expected = expected_count - len(missing)
    expected_numbers = set(range(1, expected_count + 1))
    extra = sorted(set(actual_by_number) - expected_numbers)
    for line_number in extra:
        comparison_errors.append({"line": line_number, "reason": "extra"})
        line = actual_by_number[line_number]
        if (
            matcher.match_line(
                line.requested_mpn, line.requested_manufacturer
            ).match_status.value
            == "EXACT_MATCH"
        ):
            false_exact_lines.append(line_number)
    return {
        "synthetic_fixture": filename,
        "evidence_type": "synthetic_ground_truth_not_customer_metrics",
        "expected_lines": expected_count,
        "detected_lines": len(parsed.lines),
        "line_recall": detected_expected / expected_count if expected_count else None,
        "line_precision": detected_expected / len(parsed.lines)
        if parsed.lines
        else None,
        "field_accuracy": field_accuracy,
        "catalog_match_checks_correct": catalog_match_correct,
        "catalog_match_checks_total": catalog_match_checks,
        "false_exact_match_count": len(false_exact_lines),
        "false_exact_match_line_numbers": false_exact_lines,
        "unflagged_critical_mismatch_lines": unflagged_critical_lines,
        "expected_warnings_missing": expected_warnings_missing,
        "missing_expected_line_numbers": missing,
        "extra_detected_line_numbers": extra,
        "comparison_errors": comparison_errors,
        "rows_with_source_locator": sum(
            line.source_locator.file_name == filename
            and line.source_locator.row_number is not None
            for line in parsed.lines
        ),
    }


def evaluate_synthetic_adversarial_fixtures(root: Path = ROOT) -> Dict[str, Any]:
    """Score annotated text edge cases and cross-source duplicate/conflict behavior."""
    ground_truth = json.loads(
        (root / "fixtures" / "ground_truth" / "annotations.json").read_text(
            encoding="utf-8"
        )
    )
    catalog = CatalogRepository()
    catalog.import_csv(
        (
            root / "fixtures" / "catalogs" / "industrial_components_sample_catalog.csv"
        ).read_bytes(),
        version="synthetic",
    )
    matcher = ExactMatchEngine(catalog)
    messy = _score_text_fixture(
        "messy_email_quote_request.txt",
        ground_truth["fixtures"]["messy_email_quote_request.txt"]["expected_items"],
        root,
        matcher,
    )

    collision_name = "cross_brand_collision.txt"
    collision_result = TextParser().parse(
        (root / "fixtures" / "rfq_samples" / collision_name).read_bytes(),
        collision_name,
    )
    expected_collision_mpns = set(
        ground_truth["fixtures"][collision_name]["expected_collision_mpns"]
    )
    observed_collisions = {
        line.requested_mpn
        for line in collision_result.lines
        if matcher.match_line(
            line.requested_mpn, line.requested_manufacturer
        ).match_status.value
        == "COLLISION"
    }
    false_exact_collisions = {
        line.requested_mpn
        for line in collision_result.lines
        if line.requested_mpn in expected_collision_mpns
        and matcher.match_line(
            line.requested_mpn, line.requested_manufacturer
        ).match_status.value
        == "EXACT_MATCH"
    }

    quantity_a = b"1. 4 units Schneider Electric LC1D09BD contactor"
    quantity_b = b"1. 7 units Schneider Electric LC1D09BD contactor"
    duplicate_text = b"1. 4 units Schneider Electric LC1D09BD contactor"
    manufacturer_a = b"4 pcs Schneider Electric LC1D09BD contactor"
    manufacturer_b = b"4 pcs Siemens LC1D09BD contactor"
    revision_a = b"4 pcs Schneider Electric LC1D09BD contactor Rev A"
    revision_b = b"4 pcs Schneider Electric LC1D09BD contactor Revision B"
    part_number_a = b"Schneider Electric LC1D09BD high performance motor contactor"
    part_number_b = b"Schneider Electric LC1D09BE high performance motor contactor"
    with TemporaryDirectory(prefix="rfq-synthetic-evaluation-") as temporary:
        manager = CaseManager(
            CatalogRepository(), storage=DocumentStorage(Path(temporary) / "sources")
        )
        duplicate_case = manager.create_case_from_uploads(
            [("duplicate-a.txt", duplicate_text), ("duplicate-b.txt", duplicate_text)]
        )
        quantity_case = manager.create_case_from_uploads(
            [("quantity-a.txt", quantity_a), ("quantity-b.txt", quantity_b)]
        )
        manufacturer_case = manager.create_case_from_uploads(
            [
                ("manufacturer-a.txt", manufacturer_a),
                ("manufacturer-b.txt", manufacturer_b),
            ]
        )
        revision_case = manager.create_case_from_uploads(
            [("revision-a.txt", revision_a), ("revision-b.txt", revision_b)]
        )
        part_number_case = manager.create_case_from_uploads(
            [("part-number-a.txt", part_number_a), ("part-number-b.txt", part_number_b)]
        )
        duplicate_detected = (
            [doc.processing_status for doc in duplicate_case.source_documents]
            == ["processed", "duplicate"]
            and len(manager.get_lines(duplicate_case.case_id)) == 1
            and any(
                warning.code == "DUPLICATE_SOURCE"
                for warning in duplicate_case.document_warnings
            )
        )
        quantity_lines = manager.get_lines(quantity_case.case_id)
        quantity_detected = bool(quantity_lines) and all(
            any(
                warning.code == "SOURCE_QUANTITY_CONFLICT"
                for warning in line.extraction_warnings
            )
            for line in quantity_lines
        )
        manufacturer_lines = manager.get_lines(manufacturer_case.case_id)
        manufacturer_detected = bool(manufacturer_lines) and all(
            any(
                warning.code == "SOURCE_MANUFACTURER_CONFLICT"
                for warning in line.extraction_warnings
            )
            for line in manufacturer_lines
        )
        revision_lines = manager.get_lines(revision_case.case_id)
        revision_detected = bool(revision_lines) and all(
            any(
                warning.code == "SOURCE_REVISION_CONFLICT"
                for warning in line.extraction_warnings
            )
            for line in revision_lines
        )
        part_number_lines = manager.get_lines(part_number_case.case_id)
        part_number_detected = bool(part_number_lines) and all(
            any(
                warning.code == "SOURCE_PART_NUMBER_CONFLICT"
                for warning in line.extraction_warnings
            )
            for line in part_number_lines
        )

    return {
        "evidence_type": "synthetic_adversarial_fixtures_not_customer_metrics",
        "messy_email": messy,
        "cross_brand_collision": {
            "expected_collision_mpns": sorted(expected_collision_mpns),
            "observed_collision_mpns": sorted(observed_collisions),
            "false_exact_collision_mpns": sorted(false_exact_collisions),
            "passed": expected_collision_mpns <= observed_collisions
            and not false_exact_collisions,
        },
        "duplicate_source_detection": {
            "expected": "identical second attachment is marked duplicate and does not duplicate line rows",
            "passed": duplicate_detected,
        },
        "quantity_conflict_detection": {
            "expected_warning": "SOURCE_QUANTITY_CONFLICT",
            "passed": quantity_detected,
        },
        "manufacturer_conflict_detection": {
            "expected_warning": "SOURCE_MANUFACTURER_CONFLICT",
            "passed": manufacturer_detected,
        },
        "revision_conflict_detection": {
            "expected_warning": "SOURCE_REVISION_CONFLICT",
            "passed": revision_detected,
        },
        "part_number_conflict_detection": {
            "expected_warning": "SOURCE_PART_NUMBER_CONFLICT",
            "passed": part_number_detected,
        },
    }


def evaluate_synthetic_demo(root: Path = ROOT) -> Dict[str, Any]:
    ground_truth = json.loads(
        (root / "fixtures" / "ground_truth" / "annotations.json").read_text(
            encoding="utf-8"
        )
    )
    expected = ground_truth["fixtures"][BOM_FILENAME]["lines"]
    catalog = CatalogRepository()
    catalog.import_csv(
        (
            root / "fixtures" / "catalogs" / "industrial_components_sample_catalog.csv"
        ).read_bytes(),
        version="synthetic",
    )
    parsed = SpreadsheetParser().parse(
        (root / "fixtures" / "rfq_samples" / BOM_FILENAME).read_bytes(),
        BOM_FILENAME,
    )
    report = score_bom_lines(parsed.lines, expected, ExactMatchEngine(catalog))
    adversarial = evaluate_synthetic_adversarial_fixtures(root)
    report["adversarial_fixtures"] = adversarial
    field_accuracy = report["field_accuracy"]
    report["scorecard_passed"] = (
        report["line_recall"] == 1.0
        and report["line_precision"] == 1.0
        and all(value["accuracy"] == 1.0 for value in field_accuracy.values())
        and report["catalog_match_checks_correct"]
        == report["catalog_match_checks_total"]
        and report["false_exact_match_count"] == 0
        and report["unflagged_critical_mismatch_lines"] == 0
        and not report["expected_warnings_missing"]
        and not report["comparison_errors"]
        and adversarial["messy_email"]["line_recall"] == 1.0
        and adversarial["messy_email"]["line_precision"] == 1.0
        and not adversarial["messy_email"]["false_exact_match_count"]
        and not adversarial["messy_email"]["unflagged_critical_mismatch_lines"]
        and not adversarial["messy_email"]["expected_warnings_missing"]
        and adversarial["cross_brand_collision"]["passed"]
        and all(
            check["passed"]
            for name, check in adversarial.items()
            if name.endswith("_detection")
        )
    )
    return report


def main():
    print(json.dumps(evaluate_synthetic_demo(), indent=2))


if __name__ == "__main__":
    main()
