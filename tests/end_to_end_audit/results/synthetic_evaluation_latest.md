# Synthetic RFQ evaluation snapshot

**Run date:** 2026-11-01

**Code revision:** `b14fa52` (main through PR #98)

**Evidence type:** synthetic ground truth and adversarial fixtures only. This is not customer data or a general accuracy estimate.

## Results

| Fixture/check | Result |
|---|---:|
| 20-line industrial-control XLSX: detected / expected | 20 / 20 |
| Line precision / recall | 100% / 100% |
| MPN, manufacturer, quantity, unit field checks | 80 / 80 correct |
| Catalog decision agreement | 20 / 20 |
| Exact catalog matches | 19 |
| False exact matches / unflagged critical mismatches | 0 / 0 |
| Rows with source locators | 20 / 20 |
| Messy email lines detected / expected | 6 / 6 |
| Messy-email field checks (MPN, manufacturer, quantity) | 15 / 15 correct |
| Messy-email catalog checks / source locators | 6 / 6 / 6 |
| Cross-brand collision | XG-42 correctly flagged; no false exact match |
| Duplicate attachment detection | Passed |
| Quantity, manufacturer, revision, and part-number conflict checks | 4 / 4 passed |
| Overall fixture scorecard | Passed |

The 20 catalog decisions include 19 exact matches and one expected `NO_MATCH` row for `NONEXISTENT-PART-999`. All 20 decisions agree with the labeled fixture; the unmatched line is not counted as an exact match.

## Reproduction

From the repository root, run:

```bash
python -m scripts.evaluate_synthetic_demo
```

The machine-readable output for this snapshot is in [`synthetic_evaluation_latest.json`](synthetic_evaluation_latest.json). The evaluator reports synthetic line and field agreement, catalog decisions, source locators, false exact matches, warning coverage, duplicate attachment behavior, and source conflict checks.

## Limits

These results apply only to the labeled synthetic fixtures in this repository. They do not establish performance on arbitrary RFQs, scanned-document OCR, Luna-assisted extraction, customer catalogs, independent human annotations, review effort, elapsed customer workflow time, or production capacity. No customer accuracy, ROI, or time-saving claim follows from this run.
