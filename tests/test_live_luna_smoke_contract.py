"""The opt-in live smoke fixture must exercise the configured Luna fallback."""

from rfq_assistant.cases.manager import CaseManager
from rfq_assistant.ingestion.parsers.text_parser import TextParser
from scripts.smoke_live_luna_e2e import LIVE_SMOKE_SOURCE_TEXT


def test_live_luna_smoke_fixture_requires_model_assistance():
    parsed = TextParser().parse(
        LIVE_SMOKE_SOURCE_TEXT.encode("utf-8"), "synthetic_luna_smoke.txt"
    )

    assert len(parsed.lines) == 1
    assert parsed.lines[0].requested_mpn == "FC-4821"
    assert parsed.lines[0].requested_manufacturer is None
    assert parsed.lines[0].quantity == 12
    assert CaseManager._needs_llm_fallback(parsed)
