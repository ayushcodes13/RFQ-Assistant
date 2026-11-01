"""Tests for the opt-in, synthetic-only end-to-end benchmark harness."""

import pytest

from scripts.benchmark_synthetic_workflow import _percentile, _run_trial


@pytest.mark.parametrize("file_format", ["csv", "xlsx", "pdf"])
def test_small_generated_document_runs_through_draft_export(file_format):
    result = _run_trial(line_count=10, attachment_count=1, primary_format=file_format)

    assert result["success"] is True
    assert result["requested_lines"] == 10
    assert result["extracted_lines"] == 10
    assert result["exact_matches"] == 10
    assert result["export_lines"] == 10
    assert result["export_is_draft"] is True
    assert result["failure_reason"] is None


def test_nearest_rank_percentile_uses_max_for_three_sample_p95():
    assert _percentile([30.0, 10.0, 20.0], 0.95) == 30.0
