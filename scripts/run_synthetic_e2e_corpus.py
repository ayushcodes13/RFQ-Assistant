"""Run a local 30-document API workflow corpus using synthetic data only.

The runner isolates uploads, exports, and SQLite state in a temporary folder.
It exercises intake -> extraction -> source retrieval -> exact catalog match ->
review -> CSV/XLSX export -> download -> audit for every successful document.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "fixtures" / "rfq_samples"
RUN_DIR = tempfile.TemporaryDirectory(prefix="rfq-synthetic-e2e-")
os.environ["RFQ_ASSISTANT_DB_PATH"] = str(Path(RUN_DIR.name) / "state.sqlite3")
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
    return "formal_rfq_native.pdf", (SAMPLES / "formal_rfq_native.pdf").read_bytes(), None


def _check_document(client: TestClient, number: int, kind: str) -> dict[str, Any]:
    started = time.perf_counter()
    name, content, pasted_text = _document(kind, number)
    data = {"title": f"Synthetic RFQ {number:02d}", "customer_label": "Synthetic only"}
    if name:
        response = client.post(
            "/api/rfqs",
            data=data,
            files={"file": (name, content, "application/octet-stream")},
        )
    else:
        response = client.post("/api/rfqs", data={**data, "pasted_text": pasted_text})
    if response.status_code != 200:
        return {"number": number, "format": kind, "step": "intake", "status": response.status_code}

    case_id = response.json()["case_id"]
    lines_response = client.get(f"/api/rfqs/{case_id}/lines")
    if lines_response.status_code != 200:
        return {"number": number, "format": kind, "step": "lines", "status": lines_response.status_code}
    lines = lines_response.json()
    source = client.get(f"/api/rfqs/{case_id}/source")
    if not lines or source.status_code != 200:
        return {"number": number, "format": kind, "step": "source", "line_count": len(lines), "status": source.status_code}

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
        }

    review = client.post(
        f"/api/rfqs/{case_id}/review",
        json={"line_ids": [line["line_id"] for line in lines], "decision": "APPROVED", "actor": "Synthetic reviewer"},
    )
    if review.status_code != 200:
        return {"number": number, "format": kind, "step": "review", "status": review.status_code}

    export_format = "csv" if number % 2 else "xlsx"
    export = client.post(
        f"/api/rfqs/{case_id}/exports",
        json={"case_id": case_id, "actor": "Synthetic reviewer", "format": export_format},
    )
    if export.status_code != 200:
        return {"number": number, "format": kind, "step": "export", "status": export.status_code}
    manifest = export.json()
    download = client.get(manifest["download_url"])
    if download.status_code != 200 or len(download.content) < 100:
        return {"number": number, "format": kind, "step": "download", "status": download.status_code}
    audit = client.get(f"/api/rfqs/{case_id}/audit")
    if audit.status_code != 200 or not any(event["action"] == "EXPORTED" for event in audit.json()):
        return {"number": number, "format": kind, "step": "audit", "status": audit.status_code}
    return {
        "number": number,
        "format": kind,
        "lines": len(lines),
        "approved": manifest["approved_lines"],
        "download_bytes": len(download.content),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


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
            "successful_full_flows": len(results) - len(failures),
            "failures": failures,
            "elapsed_seconds": round(time.perf_counter() - started, 2),
            "median_document_ms": durations[len(durations) // 2] if durations else None,
            "max_document_ms": max(durations) if durations else None,
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
    return 1 if failures or len(concurrent_ids) != len(concurrent) or len(set(concurrent_ids)) != len(concurrent_ids) else 0


if __name__ == "__main__":
    raise SystemExit(main())
