"""Enforce overall and safety-critical line coverage floors from coverage.py JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path


FLOORS = {
    "rfq_assistant/quotation/validate.py": 95.0,
    "rfq_assistant/matching/": 95.0,
    "rfq_assistant/exports/": 95.0,
    "rfq_assistant/persistence.py": 95.0,
}
OVERALL_FLOOR = 80.0


def line_coverage(summary: dict) -> float:
    statements = summary.get("num_statements", 0)
    if statements == 0:
        return 100.0
    return 100.0 * summary.get("covered_lines", 0) / statements


def main(report_path: str = "coverage.json") -> int:
    report = json.loads(Path(report_path).read_text())
    files = report.get("files", {})
    failures = []

    overall = line_coverage(report.get("totals", {}))
    print(f"Overall: {overall:.2f}% (required {OVERALL_FLOOR:.2f}%)")
    if overall < OVERALL_FLOOR:
        failures.append(f"overall coverage {overall:.2f}% is below {OVERALL_FLOOR:.2f}%")

    for path, floor in FLOORS.items():
        if path.endswith("/"):
            selected = [value["summary"] for name, value in files.items() if name.startswith(path)]
        else:
            selected = [value["summary"] for name, value in files.items() if name == path]
        if not selected:
            failures.append(f"coverage report does not contain {path}")
            print(f"{path}: missing (required {floor:.2f}%)")
            continue
        statements = sum(summary.get("num_statements", 0) for summary in selected)
        covered = sum(summary.get("covered_lines", 0) for summary in selected)
        percentage = 100.0 if statements == 0 else 100.0 * covered / statements
        print(f"{path}: {percentage:.2f}% (required {floor:.2f}%)")
        if percentage < floor:
            failures.append(f"{path} coverage {percentage:.2f}% is below {floor:.2f}%")

    if failures:
        print("Coverage gate failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("Coverage gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "coverage.json"))
