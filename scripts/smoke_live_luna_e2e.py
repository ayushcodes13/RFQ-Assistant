"""Run one synthetic Luna-backed RFQ through human review and draft export.

Requires RFQ_LLM_ENABLED=true plus the Luna endpoint and key in environment
variables. No upload, credential, or model response text is printed or retained.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.exports.generator import ExportGenerator
from rfq_assistant.ingestion.ai_extraction import GroundedLLMExtractor
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository
from rfq_assistant.schemas.enums import ReviewDecision
from rfq_assistant.schemas.models import (
    CatalogItem,
    ExportRequest,
    RFQLineItemUpdate,
)

LIVE_SMOKE_SOURCE_TEXT = (
    # Fabrikam is intentionally outside the deterministic parser's OEM
    # aliases, so this source must reach the configured Luna fallback.
    # Every proposed value is still directly supported by the text.
    "Please quote FC-4821 from Fabrikam Controls, 12 units, an auxiliary contact block."
)


def main() -> int:
    extractor = GroundedLLMExtractor.from_environment()
    if extractor is None:
        print("e2e=not_run reason=luna_adapter_not_configured")
        return 2

    catalog = CatalogRepository()
    catalog.add_item(
        CatalogItem(
            internal_sku="SYN-FC-4821",
            manufacturer="Fabrikam Controls",
            manufacturer_part_number="FC-4821",
            description="Synthetic auxiliary contact block",
        )
    )
    try:
        with tempfile.TemporaryDirectory(prefix="rfq-luna-e2e-") as temporary_root:
            root = Path(temporary_root)
            manager = CaseManager(
                catalog=catalog,
                storage=DocumentStorage(root / "uploads"),
                llm_extractor=extractor,
            )
            case = manager.create_case_from_text(
                LIVE_SMOKE_SOURCE_TEXT,
                title="SYNTHETIC Luna full-flow check",
            )
            lines = manager.get_lines(case.case_id)
            if len(lines) != 1:
                print(f"e2e=failed stage=extraction line_count={len(lines)}")
                return 1

            line = lines[0]
            exact_match = (
                line.requested_manufacturer == "Fabrikam Controls"
                and line.requested_mpn == "FC-4821"
                and line.quantity == 12
                and line.match_status.value == "EXACT_MATCH"
                and line.selected_catalog_sku == "SYN-FC-4821"
            )
            review_plan = manager.get_review_plan(case.case_id)
            individual_review_required = (
                line.line_id in review_plan.exception_line_ids
                and line.line_id not in review_plan.sample_line_ids
            )
            if not exact_match or not individual_review_required:
                warning_codes = sorted(
                    {warning.code for warning in line.extraction_warnings}
                )
                print(
                    "e2e=review_required "
                    f"exact_match={exact_match} individual_review={individual_review_required} "
                    f"warning_codes={','.join(warning_codes) or 'none'}"
                )
                return 1

            manager.update_line(
                case.case_id,
                line.line_id,
                RFQLineItemUpdate(
                    expected_version=line.version,
                    review_decision=ReviewDecision.APPROVED,
                    actor="Synthetic reviewer",
                ),
            )
            reviewed_lines = manager.get_lines(case.case_id)
            manifest = ExportGenerator(
                catalog,
                root / "exports",
            ).generate_export(
                case,
                reviewed_lines,
                ExportRequest(
                    case_id=case.case_id,
                    actor="Synthetic reviewer",
                    format="csv",
                ),
            )
            passed = (
                reviewed_lines[0].review_decision == ReviewDecision.APPROVED
                and manifest.is_draft
                and individual_review_required
                and case.llm_call_count >= 1
                and case.llm_review_call_count >= 1
            )
            print(
                f"e2e={'pass' if passed else 'failed'} "
                f"line_count={len(reviewed_lines)} exact_catalog_match={exact_match} "
                f"individual_review={individual_review_required} reviewer_approved="
                f"{reviewed_lines[0].review_decision == ReviewDecision.APPROVED} "
                f"draft_export={manifest.is_draft} "
                f"llm_calls={case.llm_call_count} "
                f"validation_calls={case.llm_review_call_count} "
                "tokens="
                f"{'known' if case.llm_input_tokens is not None and case.llm_output_tokens is not None else 'unavailable'}"
            )
            return 0 if passed else 1
    finally:
        extractor.close()


if __name__ == "__main__":
    sys.exit(main())
