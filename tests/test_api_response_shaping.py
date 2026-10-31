"""Response minimization and safe upload-error contract regressions."""

import importlib
import io
import zipfile
from types import SimpleNamespace

from fastapi.testclient import TestClient

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.storage import DocumentStorage
from rfq_assistant.matching.catalog import CatalogRepository


def test_case_list_omits_raw_text_while_case_detail_keeps_it(monkeypatch, tmp_path):
    api = importlib.import_module("rfq_assistant.api.app")
    manager = CaseManager(
        CatalogRepository(), storage=DocumentStorage(tmp_path / "uploads")
    )
    source_text = (
        "Synthetic request: 2 EA Schneider LC1D09BD; "
        "contact synthetic.contact@example.invalid"
    )
    case = manager.create_case_from_text(source_text, customer_label="Synthetic only")
    monkeypatch.setattr(api, "case_manager", manager)

    client = TestClient(api.app)
    list_response = client.get("/api/rfqs")
    detail_response = client.get(f"/api/rfqs/{case.case_id}")

    assert list_response.status_code == 200
    assert "raw_text" not in list_response.json()[0]
    assert detail_response.status_code == 200
    assert detail_response.json()["raw_text"] == source_text


def test_malformed_workbook_returns_generic_error_and_logs_exception(
    monkeypatch, tmp_path, caplog
):
    api = importlib.import_module("rfq_assistant.api.app")
    manager = CaseManager(
        CatalogRepository(), storage=DocumentStorage(tmp_path / "uploads")
    )
    monkeypatch.setattr(api, "case_manager", manager)
    monkeypatch.setattr(api, "ASYNC_INGEST_ENABLED", False)
    monkeypatch.setattr(
        api.clamav_scanner,
        "scan_bytes",
        lambda *_args, **_kwargs: SimpleNamespace(is_clean=True, threat_name=None),
    )
    malformed_archive = io.BytesIO()
    with zipfile.ZipFile(malformed_archive, "w") as archive:
        archive.writestr("not-a-workbook.txt", "synthetic malformed workbook")

    caplog.set_level("ERROR", logger=api.log.name)
    response = TestClient(api.app).post(
        "/api/rfqs",
        files={
            "file": (
                "malformed.xlsx",
                malformed_archive.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Unable to process this RFQ. Verify the file and try again."
    }
    assert "There is no item named '[Content_Types].xml' in the archive" in caplog.text
