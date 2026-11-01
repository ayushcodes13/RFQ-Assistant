"""Legacy .xls must fail closed where RFQ/customer data may be protected."""
import pytest

from rfq_assistant.ingestion.xls_conversion import LegacyXLSConversionError, convert_legacy_xls


@pytest.mark.parametrize("env_name", ["REQUIRE_AUTH", "REQUIRE_ANTIVIRUS"])
def test_protected_deployment_refuses_unsandboxed_legacy_converter(monkeypatch, env_name):
    monkeypatch.delenv("REQUIRE_AUTH", raising=False)
    monkeypatch.delenv("REQUIRE_ANTIVIRUS", raising=False)
    monkeypatch.setenv(env_name, "true")
    with pytest.raises(LegacyXLSConversionError, match="disabled in protected"):
        convert_legacy_xls(b"synthetic old-format workbook", converter="/bin/true")


def test_protected_conversion_refuses_before_running_any_process(monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "yes")
    invoked = []
    monkeypatch.setattr("subprocess.run", lambda *a, **k: invoked.append(1))
    with pytest.raises(LegacyXLSConversionError):
        convert_legacy_xls(b"synthetic")
    assert invoked == []
