"""Risk-based sample review must be deterministic and server-enforced."""

import csv
import io

import openpyxl
import pytest

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.schemas.enums import ReviewDecision
from rfq_assistant.schemas.models import CatalogItem, BatchReviewRequest, RFQLineItemUpdate


def _case(tmp_path, row_count=12):
    catalog = CatalogRepository()
    rows = []
    for index in range(row_count):
        mpn = f"AX-{index:04d}"
        manufacturer = "Example Controls"
        catalog.add_item(CatalogItem(
            internal_sku=f"SKU-{index:04d}",
            manufacturer=manufacturer,
            manufacturer_part_number=mpn,
            description=f"Synthetic relay {index}",
        ))
        rows.append([mpn, manufacturer, 2, f"Synthetic relay {index}", "EA"])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["MPN", "Manufacturer", "Qty", "Description", "UOM"])
    writer.writerows(rows)
    manager = CaseManager(catalog, storage=DocumentStorage(tmp_path / "files"))
    case = manager.create_case_from_upload(
        "synthetic.csv", output.getvalue().encode(), customer_label="Synthetic only"
    )
    return manager, case


def _versions(manager, case_id, line_ids=None):
    lines = manager.get_lines(case_id)
    selected = set(line_ids) if line_ids is not None else {line.line_id for line in lines}
    return {line.line_id: line.version for line in lines if line.line_id in selected}


def test_review_plan_selects_a_stable_per_case_randomized_sample_and_batches_rest(tmp_path):
    manager, case = _case(tmp_path)
    first = manager.get_review_plan(case.case_id)
    assert len(first.sample_line_ids) == 5
    assert first.exception_line_ids == []
    assert len(first.remaining_line_ids) == 7
    assert set(first.sample_rationale) == set(first.sample_line_ids)
    assert all("structured extraction" in reason for reason in first.sample_rationale.values())
    assert manager.get_review_plan(case.case_id).sample_line_ids == first.sample_line_ids
    assert not first.can_batch_approve

    manager.batch_review(case.case_id, BatchReviewRequest(
        line_ids=first.sample_line_ids,
        expected_versions=_versions(manager, case.case_id, first.sample_line_ids),
        decision=ReviewDecision.APPROVED,
        actor="Synthetic reviewer",
        notes="Source cross-check passed",
    ))
    after_sample = manager.get_review_plan(case.case_id)
    assert after_sample.sample_approved
    assert after_sample.can_batch_approve
    assert manager.approve_remaining_clean(
        case.case_id, "Synthetic reviewer", _versions(manager, case.case_id)
    ) == 7
    assert all(line.review_decision == ReviewDecision.APPROVED for line in manager.get_lines(case.case_id))
    assert len([event for event in manager.get_audit_trail(case.case_id) if event.action == "LINE_APPROVED"]) == 12


def test_review_sample_does_not_always_pick_the_same_middle_positions(tmp_path):
    manager, case = _case(tmp_path, row_count=50)
    plan = manager.get_review_plan(case.case_id)
    lines_by_id = {line.line_id: line for line in manager.get_lines(case.case_id)}
    sampled_rows = sorted(
        lines_by_id[line_id].source_locator.row_number for line_id in plan.sample_line_ids
    )
    assert sampled_rows != [7, 17, 27, 37, 47]


def test_clean_rows_cannot_be_batch_approved_before_sample(tmp_path):
    manager, case = _case(tmp_path)
    plan = manager.get_review_plan(case.case_id)
    with pytest.raises(ValueError, match="current review sample"):
        manager.batch_review(case.case_id, BatchReviewRequest(
            line_ids=[line.line_id for line in manager.get_lines(case.case_id)],
            expected_versions=_versions(manager, case.case_id),
            decision=ReviewDecision.APPROVED,
        ))
    with pytest.raises(ValueError, match="Approve every sampled row"):
        manager.approve_remaining_clean(
            case.case_id, "Synthetic reviewer", _versions(manager, case.case_id)
        )


def test_sample_correction_disables_batch_approval_for_the_case(tmp_path):
    manager, case = _case(tmp_path)
    plan = manager.get_review_plan(case.case_id)
    line = next(row for row in manager.get_lines(case.case_id) if row.line_id == plan.sample_line_ids[0])
    manager.update_line(case.case_id, line.line_id, RFQLineItemUpdate(expected_version=line.version,
        quantity=3,
        review_decision=ReviewDecision.APPROVED,
        actor="Synthetic reviewer",
    ))
    updated = manager.get_review_plan(case.case_id)
    assert updated.sample_correction_found
    assert not updated.can_batch_approve
    with pytest.raises(ValueError, match="needed correction"):
        manager.approve_remaining_clean(
            case.case_id, "Synthetic reviewer", _versions(manager, case.case_id)
        )


def test_small_cases_sample_every_otherwise_clean_row(tmp_path):
    manager, case = _case(tmp_path, row_count=3)
    plan = manager.get_review_plan(case.case_id)
    assert len(plan.sample_line_ids) == 3
    assert plan.remaining_line_ids == []


def test_unrepresented_source_strata_remain_individual_review_exceptions(tmp_path):
    catalog = CatalogRepository()
    workbook = openpyxl.Workbook()
    workbook.remove(workbook.active)
    for sheet_number in range(6):
        sheet = workbook.create_sheet(f"Panel {sheet_number + 1}")
        sheet.append(["MPN", "Manufacturer", "Qty", "Description", "UOM"])
        for offset in range(2):
            index = sheet_number * 2 + offset
            mpn = f"AX-{index:04d}"
            catalog.add_item(CatalogItem(
                internal_sku=f"SKU-{index:04d}",
                manufacturer="Example Controls",
                manufacturer_part_number=mpn,
                description=f"Synthetic relay {index}",
            ))
            sheet.append([mpn, "Example Controls", 2, f"Synthetic relay {index}", "EA"])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()

    manager = CaseManager(catalog, storage=DocumentStorage(tmp_path / "files"))
    case = manager.create_case_from_upload("six-panels.xlsx", output.getvalue())
    lines_by_id = {line.line_id: line for line in manager.get_lines(case.case_id)}
    plan = manager.get_review_plan(case.case_id)

    sampled_sheets = {
        lines_by_id[line_id].source_locator.sheet_name
        for line_id in plan.sample_line_ids
    }
    exception_sheets = {
        lines_by_id[line_id].source_locator.sheet_name
        for line_id in plan.exception_line_ids
    }
    assert len(plan.sample_line_ids) == 5
    assert len(sampled_sheets) == 5
    assert len(exception_sheets) == 1
    assert plan.remaining_line_ids == [
        line_id
        for line_id, line in lines_by_id.items()
        if line.source_locator.sheet_name in sampled_sheets and line_id not in plan.sample_line_ids
    ]
    assert len(plan.remaining_line_ids) == 5
    assert all(
        line_id not in plan.remaining_line_ids
        for line_id in plan.exception_line_ids
    )


def test_exceptions_stay_outside_the_sample_and_batch_approval(tmp_path):
    catalog = CatalogRepository()
    rows = []
    for index in range(7):
        mpn = f"AX-{index:04d}"
        catalog.add_item(CatalogItem(
            internal_sku=f"SKU-{index:04d}",
            manufacturer="Example Controls",
            manufacturer_part_number=mpn,
            description=f"Synthetic relay {index}",
        ))
        rows.append([mpn, "Example Controls", 2, f"Synthetic relay {index}", "EA"])
    rows.extend([
        ["AX-0000", "Example Controls", "", "Missing quantity", "EA"],
        ["UNKNOWN-999", "Example Controls", 2, "No exact catalog entry", "EA"],
    ])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["MPN", "Manufacturer", "Qty", "Description", "UOM"])
    writer.writerows(rows)
    manager = CaseManager(catalog, storage=DocumentStorage(tmp_path / "files"))
    case = manager.create_case_from_upload("mixed.csv", output.getvalue().encode())

    plan = manager.get_review_plan(case.case_id)
    assert len(plan.exception_line_ids) == 2
    assert len(plan.sample_line_ids) == 5
    assert len(plan.remaining_line_ids) == 2
    manager.batch_review(case.case_id, BatchReviewRequest(
        line_ids=plan.sample_line_ids,
        expected_versions=_versions(manager, case.case_id, plan.sample_line_ids),
        decision=ReviewDecision.APPROVED,
        actor="Synthetic reviewer",
    ))
    assert manager.approve_remaining_clean(
        case.case_id, "Synthetic reviewer", _versions(manager, case.case_id)
    ) == 2
    still_unreviewed = [
        line for line in manager.get_lines(case.case_id)
        if line.line_id in plan.exception_line_ids and line.review_decision == ReviewDecision.PENDING
    ]
    assert len(still_unreviewed) == 2
