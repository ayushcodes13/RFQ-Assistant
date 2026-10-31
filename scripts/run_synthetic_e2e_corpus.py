"""Run a local 30-document API workflow corpus using synthetic data only.

The runner isolates uploads, exports, and SQLite state in a temporary folder.
It exercises intake -> extraction -> source retrieval -> exact catalog match ->
review -> CSV/XLSX export -> download -> audit for every successful document.
"""

from __future__ import annotations

import io
import hashlib
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from fpdf import FPDF
from openpyxl import Workbook

RUN_DIR = tempfile.TemporaryDirectory(prefix="rfq-synthetic-e2e-")
os.environ["RFQ_ASSISTANT_DB_PATH"] = str(Path(RUN_DIR.name) / "state.sqlite3")
os.environ["RFQ_LLM_ENABLED"] = "false"  # deterministic timing corpus; never sends source text to a model
os.environ["RFQ_ASYNC_INGEST_ENABLED"] = "false"  # exercise completion inline; queue behavior has dedicated tests
os.chdir(RUN_DIR.name)

from fastapi.testclient import TestClient  # noqa: E402
from rfq_assistant.api.app import app  # noqa: E402

PRODUCTS = [
    ("Schneider Electric", "LC1D09BD", "Contactor"),
    ("Siemens", "6ES7223-1BL32-0XB0", "Digital I/O module"),
]


def _document(kind: str, number: int) -> tuple[str | None, bytes | None, str | None]:
    rows = [
        (PRODUCTS[(number + index) % len(PRODUCTS)], index + 2)
        for index in range(2)
    ]
    if kind == "text":
        text = "\n".join(
            f"{index}. {quantity} pcs of {manufacturer} {mpn} {description}"
            for index, ((manufacturer, mpn, description), quantity) in enumerate(rows, 1)
        )
        return None, None, text
    if kind == "csv":
        content = "Part Number,Manufacturer,Qty,Description,UOM\n" + "".join(
            f"{mpn},{manufacturer},{quantity},{description},EA\n"
            for (manufacturer, mpn, description), quantity in rows
        )
        return f"synthetic-{number}.csv", content.encode(), None
    if kind == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "BOM"
        sheet.append(["Part Number", "Manufacturer", "Qty", "Description", "UOM"])
        for (manufacturer, mpn, description), quantity in rows:
            sheet.append([mpn, manufacturer, quantity, description, "EA"])
        buffer = io.BytesIO()
        workbook.save(buffer)
        return f"synthetic-{number}.xlsx", buffer.getvalue(), None
    if kind == "pdf":
        # Generate distinct native-text PDF layouts instead of timing the same
        # fixture seven times. Scanned/OCR behavior is measured separately.
        orientation = "landscape" if number % 2 else "portrait"
        split_pages = number % 3 == 0
        layout_id = number % 4 + 1
        pdf = FPDF(orientation="L" if orientation == "landscape" else "P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, f"SYNTHETIC RFQ {number:02d} - LAYOUT {layout_id}", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", size=10)
        formats = [
            "Qty: {qty} EA | Manufacturer: {manufacturer} | MPN: {mpn} | {description}",
            "{qty} EA - {manufacturer} - {mpn} - {description}",
            "Please quote {qty} EA {manufacturer} part {mpn} - {description}",
            "Manufacturer: {manufacturer}  Part: {mpn}  Qty: {qty} EA  {description}",
        ]
        row_format = formats[layout_id - 1]
        for index, ((manufacturer, mpn, description), quantity) in enumerate(rows):
            if split_pages and index == 1:
                pdf.add_page()
                pdf.set_font("Helvetica", "B", 10)
                pdf.cell(0, 8, "Line | OEM / Brand | Description | Part Number | Qty | UOM", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", size=10)
            row = row_format.format(qty=quantity, manufacturer=manufacturer, mpn=mpn, description=description)
            pdf.set_x(10)
            pdf.multi_cell(pdf.epw, 8, row)
        return f"synthetic-{number}.pdf", bytes(pdf.output()), None
    raise ValueError(f"Unsupported synthetic corpus format: {kind}")


def _timed_request(timings: dict[str, float], stage: str, request):
    started = time.perf_counter()
    response = request()
    timings[stage] = round((time.perf_counter() - started) * 1000, 1)
    return response


def _check_document(client: TestClient, number: int, kind: str) -> dict[str, Any]:
    started = time.perf_counter()
    timings: dict[str, float] = {}
    build_started = time.perf_counter()
    name, content, pasted_text = _document(kind, number)
    source_hash = hashlib.sha256(content).hexdigest() if content is not None else None
    timings["fixture_build"] = round((time.perf_counter() - build_started) * 1000, 1)
    data = {"title": f"Synthetic RFQ {number:02d}", "customer_label": "Synthetic only"}
    if name:
        response = _timed_request(
            timings, "intake", lambda: client.post(
                "/api/rfqs",
                data=data,
                files={"file": (name, content, "application/octet-stream")},
            ),
        )
    else:
        response = _timed_request(
            timings, "intake", lambda: client.post("/api/rfqs", data={**data, "pasted_text": pasted_text})
        )
    if response.status_code != 200:
        return {"number": number, "format": kind, "step": "intake", "status": response.status_code, "stage_latency_ms": timings}

    case_id = response.json()["case_id"]
    lines_response = _timed_request(timings, "lines", lambda: client.get(f"/api/rfqs/{case_id}/lines"))
    if lines_response.status_code != 200:
        return {"number": number, "format": kind, "step": "lines", "status": lines_response.status_code, "stage_latency_ms": timings}
    lines = lines_response.json()
    source = _timed_request(timings, "source", lambda: client.get(f"/api/rfqs/{case_id}/source"))
    if not lines or source.status_code != 200:
        return {"number": number, "format": kind, "step": "source", "line_count": len(lines), "status": source.status_code, "stage_latency_ms": timings}

    invalid = [
        line
        for line in lines
        if line["match_status"] != "EXACT_MATCH"
        or not line["selected_catalog_sku"]
        or not line["quantity"]
        or not line["source_locator"].get("file_name")
    ]
    if invalid:
        return {
            "number": number,
            "format": kind,
            "step": "extracted-line-validation",
            "invalid_count": len(invalid),
            "invalid_mpns": [line.get("requested_mpn") for line in invalid],
            "stage_latency_ms": timings,
        }

    plan_response = _timed_request(
        timings, "review_plan", lambda: client.get(f"/api/rfqs/{case_id}/review-plan")
    )
    if plan_response.status_code != 200:
        return {"number": number, "format": kind, "step": "review-plan", "status": plan_response.status_code, "stage_latency_ms": timings}
    plan = plan_response.json()
    if plan["sample_line_ids"]:
        review = _timed_request(
            timings, "sample_review", lambda: client.post(
                f"/api/rfqs/{case_id}/review",
                json={"line_ids": plan["sample_line_ids"], "decision": "APPROVED", "actor": "Synthetic reviewer"},
            ),
        )
        if review.status_code != 200:
            return {"number": number, "format": kind, "step": "sample-review", "status": review.status_code, "stage_latency_ms": timings}
    plan = _timed_request(
        timings, "review_plan_after_sample", lambda: client.get(f"/api/rfqs/{case_id}/review-plan")
    ).json()
    if plan["can_batch_approve"]:
        batch_result = _timed_request(
            timings, "batch_approve_remaining", lambda: client.post(
                f"/api/rfqs/{case_id}/review-plan/approve-remaining", json={}
            ),
        )
        if batch_result.status_code != 200:
            return {"number": number, "format": kind, "step": "batch-approve", "status": batch_result.status_code, "stage_latency_ms": timings}
    for line_id in plan["exception_line_ids"]:
        response = _timed_request(
            timings, "exception_review", lambda line_id=line_id: client.patch(
                f"/api/rfqs/{case_id}/lines/{line_id}",
                json={"review_decision": "APPROVED", "actor": "Synthetic reviewer"},
            ),
        )
        if response.status_code != 200:
            return {"number": number, "format": kind, "step": "exception-review", "status": response.status_code, "stage_latency_ms": timings}
    approval_check = client.get(f"/api/rfqs/{case_id}/lines").json()
    if any(line["review_decision"] != "APPROVED" for line in approval_check):
        return {"number": number, "format": kind, "step": "review-incomplete", "stage_latency_ms": timings}

    export_format = "csv" if number % 2 else "xlsx"
    export = _timed_request(
        timings, "export_generation", lambda: client.post(
            f"/api/rfqs/{case_id}/exports",
            json={"case_id": case_id, "actor": "Synthetic reviewer", "format": export_format},
        ),
    )
    if export.status_code != 200:
        return {"number": number, "format": kind, "step": "export", "status": export.status_code, "stage_latency_ms": timings}
    manifest = export.json()
    download = _timed_request(timings, "download", lambda: client.get(manifest["download_url"]))
    if download.status_code != 200 or len(download.content) < 100:
        return {"number": number, "format": kind, "step": "download", "status": download.status_code, "stage_latency_ms": timings}
    audit = _timed_request(timings, "audit", lambda: client.get(f"/api/rfqs/{case_id}/audit"))
    if audit.status_code != 200 or not any(event["action"] == "EXPORTED" for event in audit.json()):
        return {"number": number, "format": kind, "step": "audit", "status": audit.status_code, "stage_latency_ms": timings}
    result = {
        "number": number,
        "format": kind,
        "lines": len(lines),
        "approved": manifest["approved_lines"],
        "download_bytes": len(download.content),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
        "stage_latency_ms": timings,
    }
    if kind == "pdf":
        result["source_sha256"] = source_hash
        result["pdf_layout"] = {
            "variant": number % 4 + 1,
            "orientation": "landscape" if number % 2 else "portrait",
            "split_across_pages": number % 3 == 0,
        }
    return result


def _concurrent_create(number: int) -> tuple[int, str | None]:
    with TestClient(app) as client:
        response = client.post(
            "/api/rfqs",
            data={
                "title": f"Synthetic concurrent case {number}",
                "pasted_text": "1. 3 pcs of Schneider Electric LC1D09BD contactor",
            },
        )
        return response.status_code, response.json().get("case_id") if response.status_code == 200 else None


def main() -> int:
    formats = ["text"] * 8 + ["csv"] * 8 + ["xlsx"] * 7 + ["pdf"] * 7
    with TestClient(app) as client:
        started = time.perf_counter()
        results = [_check_document(client, number, kind) for number, kind in enumerate(formats, 1)]
    failures = [result for result in results if "step" in result]
    durations = sorted(result["elapsed_ms"] for result in results if "elapsed_ms" in result)

    stage_values: dict[str, dict[str, list[float]]] = {}
    for result in results:
        for stage, elapsed_ms in result.get("stage_latency_ms", {}).items():
            stage_values.setdefault(result["format"], {}).setdefault(stage, []).append(elapsed_ms)

    stage_latency_summary = {}
    for kind, stages in stage_values.items():
        stage_latency_summary[kind] = {}
        for stage, values in stages.items():
            ordered = sorted(values)
            p95_index = max(0, int(len(ordered) * 0.95 + 0.999) - 1)
            stage_latency_summary[kind][stage] = {
                "count": len(ordered),
                "median_ms": ordered[len(ordered) // 2],
                "p95_ms": ordered[p95_index],
                "max_ms": max(ordered),
            }

    pdf_source_hashes = {result["source_sha256"] for result in results if result.get("source_sha256")}
    pdf_layout_variants = {result["pdf_layout"]["variant"] for result in results if result.get("pdf_layout")}
    pdf_diversity_passed = len(pdf_source_hashes) == formats.count("pdf") and len(pdf_layout_variants) == 4

    concurrency_started = time.perf_counter()
    concurrent_request_count = 128
    concurrent_worker_count = 16
    with ThreadPoolExecutor(max_workers=concurrent_worker_count) as pool:
        concurrent = list(pool.map(_concurrent_create, range(1, concurrent_request_count + 1)))
    concurrent_ids = [case_id for status, case_id in concurrent if status == 200 and case_id]
    report = {
        "evidence_type": "synthetic_local_integration_test_not_customer_metrics",
        "serial_corpus": {
            "documents": len(formats),
            "formats": {kind: formats.count(kind) for kind in sorted(set(formats))},
            "pdf_unique_sources": len(pdf_source_hashes),
            "pdf_layout_variants": len(pdf_layout_variants),
            "pdf_diversity_passed": pdf_diversity_passed,
            "pdf_layouts": sorted(
                {json.dumps(r["pdf_layout"], sort_keys=True) for r in results if r.get("pdf_layout")}
            ),
            "successful_full_flows": len(results) - len(failures),
            "failures": failures,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "median_document_ms": durations[len(durations) // 2] if durations else None,
            "max_document_ms": max(durations) if durations else None,
            "stage_latency_ms_by_format": stage_latency_summary,
        },
        "concurrent_create_burst": {
            "requests": concurrent_request_count,
            "workers": concurrent_worker_count,
            "successful": len(concurrent_ids),
            "unique_case_ids": len(set(concurrent_ids)),
            "elapsed_seconds": round(time.perf_counter() - concurrency_started, 2),
        },
    }
    print(json.dumps(report, indent=2))
    return 1 if failures or not pdf_diversity_passed or len(concurrent_ids) != len(concurrent) or len(set(concurrent_ids)) != len(concurrent_ids) else 0


if __name__ == "__main__":
    raise SystemExit(main())
