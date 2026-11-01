"use client";

import React, { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Download,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Search,
  Check,
  X as XIcon,
  Info,
} from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ProcessingProgress } from "@/components/ProcessingProgress";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { MotionWrapper } from "@/components/ui/MotionWrapper";
import { SourcePreviewDialog } from "@/components/SourcePreviewDialog";
import { PdfSourcePreviewDialog } from "@/components/PdfSourcePreviewDialog";
import {
  approveRemainingValidatedLines,
  batchReviewLines,
  getCaseLines,
  getReviewPlan,
  rematchLineItem,
  updateLineItem,
} from "@/services/api";
import {
  RFQCase,
  RFQLineItem,
  RFQLineItemUpdate,
  ReviewPlan,
  SourceLocator,
} from "@/types";

interface WorkbenchViewProps {
  caseData: RFQCase;
  onOpenExport: () => void;
  onCaseUpdated: () => Promise<void>;
}

type FilterType = "all" | "sample" | "exact" | "ambiguous" | "missing";

const filterConfig: { id: FilterType; label: string }[] = [
  { id: "all", label: "All lines" },
  { id: "sample", label: "Review sample" },
  { id: "exact", label: "Exact match" },
  { id: "ambiguous", label: "Needs review" },
  { id: "missing", label: "No match" },
];

function formatLocator(locator: SourceLocator): string {
  const parts = [locator.file_name];
  if (locator.sheet_name) parts.push(`sheet ${locator.sheet_name}`);
  if (locator.page_number != null) parts.push(`page ${locator.page_number}`);
  if (locator.page_bbox) {
    const [x0, y0, x1, y1] = locator.page_bbox;
    parts.push(
      `OCR area ${Math.round(x0 * 100)}%,${Math.round(y0 * 100)}%–${Math.round(x1 * 100)}%,${Math.round(y1 * 100)}%`,
    );
  }
  if (locator.ocr_confidence != null) {
    parts.push(`OCR ${Math.round(locator.ocr_confidence)}% confidence`);
  }
  const sourceCells = Object.entries(locator.field_source_cells ?? {});
  if (sourceCells.length > 0) {
    parts.push(`cells ${sourceCells.map(([field, cell]) => `${field} ${cell}`).join(", ")}`);
  }
  if (locator.row_number != null) parts.push(`row ${locator.row_number}`);
  return parts.join(" · ");
}

function fieldOriginLabel(origin: NonNullable<RFQLineItem["field_provenance"]>[string]["origin"]): string {
  switch (origin) {
    case "DETERMINISTIC":
      return "Read from document";
    case "OCR":
      return "Read with OCR";
    case "LUNA":
      return "AI proposed";
    case "HUMAN":
      return "Reviewer edited";
  }
}

function fieldValidationLabel(status: string): string {
  const labels: Record<string, string> = {
    unresolved: "Needs a value",
    source_grounded: "Source checked",
    grounded_model_proposal: "Proposal checked",
    ocr_needs_human_verification: "Check OCR against source",
    human_reviewed: "Reviewer checked",
  };
  return labels[status] ?? status.replaceAll("_", " ");
}

function hasBlockingIssue(line: RFQLineItem): boolean {
  if (
    line.quantity == null ||
    !Number.isFinite(line.quantity) ||
    line.quantity <= 0
  ) {
    return true;
  }
  if (!line.unit || !line.unit.trim()) return true;
  if (
    line.match_status !== "EXACT_MATCH" &&
    line.match_status !== "MANUAL_OVERRIDE"
  ) {
    return true;
  }
  if (!line.selected_catalog_sku) return true;
  if (
    line.extraction_warnings.some(
      (warning) => warning.severity.toLowerCase() === "error"
    )
  ) {
    return true;
  }
  return line.review_decision !== "APPROVED";
}

export function WorkbenchView({
  caseData,
  onOpenExport,
  onCaseUpdated,
}: WorkbenchViewProps) {
  const [lines, setLines] = useState<RFQLineItem[]>([]);
  const [reviewPlan, setReviewPlan] = useState<ReviewPlan | null>(null);
  const [reviewPlanBusy, setReviewPlanBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<FilterType>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [editingCell, setEditingCell] = useState<{
    lineId: string;
    field: string;
  } | null>(null);
  const [editValue, setEditValue] = useState("");
  const [selectedLine, setSelectedLine] = useState<RFQLineItem | null>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [rematchingLineId, setRematchingLineId] = useState<string | null>(null);
  const [showSourcePreview, setShowSourcePreview] = useState(false);
  const [showPdfSourcePreview, setShowPdfSourcePreview] = useState(false);
  const closeSourcePreview = useCallback(() => setShowSourcePreview(false), []);
  const closePdfSourcePreview = useCallback(() => setShowPdfSourcePreview(false), []);

  const fetchLines = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getCaseLines(caseData.case_id);
      setLines(data);
      setSelectedLine((current) =>
        current
          ? data.find((line) => line.line_id === current.line_id) ?? null
          : null
      );
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      console.error("Failed to load lines", msg);
    } finally {
      setLoading(false);
    }
  }, [caseData.case_id]);

  const refreshReviewPlan = useCallback(async () => {
    try {
      setReviewPlan(await getReviewPlan(caseData.case_id));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Could not load review plan";
      console.error(msg);
    }
  }, [caseData.case_id]);

  useEffect(() => {
    let cancelled = false;
    getCaseLines(caseData.case_id)
      .then((data) => {
        if (cancelled) return;
        setLines(data);
        setSelectedLine((current) =>
          current
            ? data.find((line) => line.line_id === current.line_id) ?? null
            : null
        );
      })
      .catch((e: unknown) => {
        const message = e instanceof Error ? e.message : "Unknown error";
        console.error("Failed to load lines", message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [caseData.case_id, caseData.status]);

  useEffect(() => {
    let cancelled = false;
    getReviewPlan(caseData.case_id)
      .then((plan) => {
        if (!cancelled) setReviewPlan(plan);
      })
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : "Could not load review plan";
        console.error(msg);
      });
    return () => {
      cancelled = true;
    };
  }, [caseData.case_id, caseData.status]);

  const filteredLines = lines.filter((l) => {
    // Filter by match/extraction state using backend enum values.
    if (filter === "sample" && !reviewPlan?.sample_line_ids.includes(l.line_id)) return false;
    if (filter === "exact" && l.match_status !== "EXACT_MATCH") return false;
    if (
      filter === "ambiguous" &&
      l.match_status !== "COLLISION" &&
      l.extraction_status !== "NEEDS_CORRECTION" &&
      l.extraction_warnings.length === 0
    )
      return false;
    if (
      filter === "missing" &&
      l.match_status !== "NO_MATCH" &&
      l.extraction_status !== "UNRESOLVED"
    )
      return false;

    // Filter by search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        (l.requested_mpn || "").toLowerCase().includes(q) ||
        (l.requested_manufacturer || "").toLowerCase().includes(q) ||
        (l.description || "").toLowerCase().includes(q) ||
        (l.raw_text || "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  const unresolvedCount = lines.filter(hasBlockingIssue).length;

  const handleStartEdit = (
    lineId: string,
    field: string,
    currentValue: string
  ) => {
    setEditingCell({ lineId, field });
    setEditValue(currentValue || "");
  };

  const handleSaveEdit = async () => {
    if (!editingCell) return;
    const line = lines.find((l) => l.line_id === editingCell.lineId);
    if (!line) return;

    const update: RFQLineItemUpdate = {
      actor: "Inside Sales",
      expected_version: line.version,
    };
    if (editingCell.field === "quantity") {
      const quantity = Number(editValue);
      if (!editValue.trim() || !Number.isFinite(quantity) || quantity <= 0) {
        alert("Quantity must be a positive number.");
        return;
      }
      update.quantity = quantity;
    } else if (editingCell.field === "unit") {
      update.unit = editValue.trim();
    } else if (editingCell.field === "requested_manufacturer") {
      update.requested_manufacturer = editValue.trim() || null;
    } else if (editingCell.field === "requested_mpn") {
      update.requested_mpn = editValue.trim() || null;
    } else {
      alert(`Unsupported field: ${editingCell.field}`);
      return;
    }

    try {
      const updated = await updateLineItem(
        caseData.case_id,
        editingCell.lineId,
        update
      );
      setLines((prev) =>
        prev.map((l) => (l.line_id === updated.line_id ? updated : l))
      );
      setEditingCell(null);
      await refreshReviewPlan();
      await onCaseUpdated();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Save failed";
      alert(`Save failed: ${msg}`);
    }
  };

  const handleCancelEdit = () => {
    setEditingCell(null);
    setEditValue("");
  };

  const handleApprove = async (lineId: string) => {
    const line = lines.find((item) => item.line_id === lineId);
    if (!line) return;
    try {
      await updateLineItem(caseData.case_id, lineId, {
        review_decision: "APPROVED",
        expected_version: line.version,
        actor: "Inside Sales",
      });
      await fetchLines();
      await refreshReviewPlan();
      await onCaseUpdated();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Approve failed";
      alert(`Approve failed: ${msg}`);
    }
  };

  const handleRematch = async (line: RFQLineItem) => {
    setRematchingLineId(line.line_id);
    try {
      const updated = await rematchLineItem(caseData.case_id, line.line_id, line.version);
      setLines((current) => current.map((item) => item.line_id === updated.line_id ? updated : item));
      setSelectedLine(updated);
      await refreshReviewPlan();
      await onCaseUpdated();
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "Catalog rematch failed";
      alert(`Catalog rematch failed: ${message}`);
    } finally {
      setRematchingLineId(null);
    }
  };

  const handleApproveSample = async () => {
    if (!reviewPlan?.sample_line_ids.length) return;
    setReviewPlanBusy(true);
    try {
      await batchReviewLines(caseData.case_id, {
        line_ids: reviewPlan.sample_line_ids,
        expected_versions: Object.fromEntries(
          lines
            .filter((line) => reviewPlan.sample_line_ids.includes(line.line_id))
            .map((line) => [line.line_id, line.version]),
        ),
        decision: "APPROVED",
        actor: "Inside Sales",
        notes: "Reviewer checked the risk-based sample against the original source.",
      });
      await fetchLines();
      await refreshReviewPlan();
      await onCaseUpdated();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Sample approval failed";
      alert(`Sample approval failed: ${msg}`);
    } finally {
      setReviewPlanBusy(false);
    }
  };

  const handleApproveRemaining = async () => {
    setReviewPlanBusy(true);
    try {
      await approveRemainingValidatedLines(
        caseData.case_id,
        Object.fromEntries(lines.map((line) => [line.line_id, line.version])),
      );
      await fetchLines();
      await refreshReviewPlan();
      await onCaseUpdated();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Batch approval failed";
      alert(`Batch approval failed: ${msg}`);
    } finally {
      setReviewPlanBusy(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleSaveEdit();
    if (e.key === "Escape") handleCancelEdit();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner message="Loading line items…" size="lg" />
      </div>
    );
  }

  return (
    <div className="rfq-content !pt-3">
      {/* Toolbar */}
      <MotionWrapper direction="up">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
          <div className="flex min-w-0 items-center gap-3 flex-wrap">
            <h1 className="rfq-page-title min-w-0 max-w-[min(72vw,680px)] truncate">
              {caseData.title || caseData.case_id.slice(0, 12)}
            </h1>
            <StatusBadge status={caseData.status} />
            <span
              className="text-xs font-medium"
              style={{ color: "var(--color-brown-400)" }}
            >
              {lines.length} lines · {unresolvedCount} need review
            </span>
          </div>
          <button
            onClick={onOpenExport}
            disabled={lines.length === 0}
            className="rfq-primary self-start disabled:opacity-50 sm:self-auto"
            style={{
              backgroundColor: "var(--color-amber-400)",
              color: "var(--color-brown-900)",
            }}
          >
            <Download size={16} />
            Export draft
          </button>
        </div>
      </MotionWrapper>

      {(caseData.document_warnings ?? []).length > 0 && (
        <div className="mb-4 space-y-2" aria-label="Document extraction warnings">
          {(caseData.document_warnings ?? []).map((warning, index) => (
            <div
              key={`${warning.code}-${index}`}
              role={warning.severity.toLowerCase() === "error" ? "alert" : "status"}
              className="flex items-start gap-2 rounded-lg border px-3 py-2 text-sm"
              style={{
                borderColor: warning.severity.toLowerCase() === "error" ? "var(--color-warning-100)" : "var(--color-sand-200)",
                backgroundColor: warning.severity.toLowerCase() === "error" ? "var(--color-warning-50)" : "var(--color-cream-100)",
                color: "var(--color-brown-800)",
              }}
            >
              <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
              <span>{warning.message}</span>
            </div>
          ))}
        </div>
      )}

      {(caseData.source_coverage ?? []).length > 0 && (() => {
        const coverage = caseData.source_coverage ?? [];
        const totals = coverage.reduce((sum, unit) => ({
          regions: sum.regions + unit.nonempty_regions,
          structured: sum.structured + unit.structured_regions,
          review: sum.review + unit.review_regions,
          filtered: sum.filtered + unit.filtered_regions,
          ocrFailures: sum.ocrFailures + unit.ocr_failures,
          hiddenRows: sum.hiddenRows + (unit.hidden_row_count ?? 0),
          hiddenColumns: sum.hiddenColumns + (unit.hidden_column_count ?? 0),
        }), { regions: 0, structured: 0, review: 0, filtered: 0, ocrFailures: 0, hiddenRows: 0, hiddenColumns: 0 });
        return (
          <details className="mb-4 rounded-lg border border-[#d7e1e3] bg-white px-3 py-2 text-sm text-[#3d5056]">
            <summary className="cursor-pointer font-medium">
              Source accounting · {totals.regions} non-empty regions across {coverage.length} source sections
              <span className="ml-2 font-normal text-[#687b81]">
                {totals.structured} parsed · {totals.review} sent to review · {totals.filtered} metadata filtered
                {totals.ocrFailures > 0 && ` · ${totals.ocrFailures} OCR failures`}
                {(totals.hiddenRows > 0 || totals.hiddenColumns > 0) && ` · ${totals.hiddenRows} hidden rows, ${totals.hiddenColumns} hidden columns`}
              </span>
            </summary>
            <ul className="mt-2 space-y-1 pl-5 text-xs text-[#52656b]">
              {coverage.map((unit) => (
                <li key={unit.unit_id}>
                  {unit.unit_id}: {unit.nonempty_regions} regions · {unit.structured_regions} parsed · {unit.review_regions} review · {unit.filtered_regions} filtered
                  {unit.coverage_basis === "structured_rows" ? " · deterministic row accounting" : " · heuristic region accounting"}
                  {unit.ocr_failures > 0 && ` · ${unit.ocr_failures} OCR failures`}
                  {unit.ocr_status && unit.ocr_status !== "not_needed" && ` · OCR ${unit.ocr_status}`}
                  {unit.ocr_duration_ms != null && ` · ${Math.round(unit.ocr_duration_ms)} ms`}
                  {unit.is_empty && " · no readable content"}
                  {unit.sheet_visibility === "hidden" && " · hidden sheet"}
                  {(unit.hidden_row_count ?? 0) > 0 && ` · ${unit.hidden_row_count} hidden rows`}
                  {(unit.hidden_column_count ?? 0) > 0 && ` · ${unit.hidden_column_count} hidden columns`}
                  {unit.header_row_number != null && ` · header row ${unit.header_row_number}`}
                  {unit.formula_backed_fields > 0 && ` · ${unit.formula_backed_fields} formula-backed fields`}
                  {unit.page_rotation_degrees != null && unit.page_rotation_degrees !== 0 && ` · rotated ${unit.page_rotation_degrees}°`}
                  {unit.truncated && " · processing stopped at a safety limit"}
                  {unit.processing_status !== "processed" && ` · ${unit.processing_status}`}
                  {unit.error_code && ` (${unit.error_code})`}
                </li>
              ))}
            </ul>
            <div className="mt-2 text-xs text-[#52656b]">
              Spreadsheet rows and cells are counted deterministically, but row classification may still need review. PDF, email, and text region counts are heuristic. These counts do not prove that every requested item was found; compare them with the original source.
            </div>
            <div className="mt-2 text-xs text-[#52656b]">
              {caseData.parse_cache_hit && <span>Deterministic extraction reused from the same source and parser profile. </span>}
              {caseData.llm_cache_hit && <span>Luna result reused for its pinned deployment version. </span>}
              {caseData.llm_call_count > 0 && (
                <span>
                  Luna · {caseData.llm_call_count} calls ({caseData.llm_repair_call_count} repair, {caseData.llm_review_call_count} validation)
                  {caseData.llm_input_tokens != null && ` · ${caseData.llm_input_tokens} input / ${caseData.llm_output_tokens ?? "unknown"} output tokens`}
                </span>
              )}
            </div>
          </details>
        );
      })()}

      {(caseData.status === "PROCESSING" || caseData.status === "FAILED") && (
        <div className="mb-4">
          <ProcessingProgress caseData={caseData} />
        </div>
      )}

      {reviewPlan && reviewPlan.sample_line_ids.length > 0 && (
        <section className="mb-5 rounded-xl border border-[#d9d0c5] bg-white px-4 py-4 shadow-sm" aria-labelledby="quick-review-title">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <h2 id="quick-review-title" className="text-sm font-semibold text-[#1d2b30]">
                Quick review · {reviewPlan.sample_line_ids.length} sample rows
              </h2>
              <p className="mt-1 text-sm text-[#52656b]">
                Check the marked rows against the original. {reviewPlan.exception_line_ids.length} exception rows still need individual review.
                Luna-proposed rows require individual source verification; only clean deterministic rows can enter the quick-review sample.
                The sample spans {new Set(Object.values(reviewPlan.sample_rationale ?? {})).size} source and extraction groups; it reduces routine review, but does not statistically prove every line is correct.
                {reviewPlan.remaining_line_ids.length > 0 && " After the sample is approved, you can approve the remaining clean rows together."}
                {reviewPlan.sample_correction_found && " A sampled row needed correction, so the remaining clean rows must be checked individually."}
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5" aria-label="Sampled line items">
                {reviewPlan.sample_line_ids.map((lineId) => {
                  const line = lines.find((item) => item.line_id === lineId);
                  return (
                    <span key={lineId} className="rounded-full bg-[#f3eee6] px-2.5 py-1 text-xs font-medium text-[#33464c]">
                      Line {line?.line_number ?? "?"}{line?.source_locator.sheet_name ? ` · ${line.source_locator.sheet_name}` : line?.source_locator.page_number ? ` · p. ${line.source_locator.page_number}` : ""}
                    </span>
                  );
                })}
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <a
                href={`/api/proxy/api/rfqs/${encodeURIComponent(caseData.case_id)}/source`}
                target="_blank"
                rel="noreferrer"
                className="rfq-secondary"
              >
                Open original
              </a>
              {!reviewPlan.sample_approved && (
                <button type="button" onClick={handleApproveSample} disabled={reviewPlanBusy} className="rfq-secondary disabled:opacity-50">
                  <Check size={15} /> I checked the sample
                </button>
              )}
              {reviewPlan.can_batch_approve && (
                <button type="button" onClick={handleApproveRemaining} disabled={reviewPlanBusy} className="rfq-primary disabled:opacity-50">
                  Approve remaining {reviewPlan.remaining_line_ids.length}
                </button>
              )}
            </div>
          </div>
        </section>
      )}

      {/* Filter bar + Search */}
      <MotionWrapper direction="up" delay={0.1}>
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 mb-4">
          <div className="flex items-center gap-1.5 flex-wrap">
            {filterConfig.map((f) => (
              <button
                key={f.id}
                type="button"
                aria-pressed={filter === f.id}
                onClick={() => setFilter(f.id)}
                className={`border-b-2 px-2.5 py-2 text-[13px] transition-colors ${filter === f.id ? "border-[#a83e1c] font-medium text-[#1d2b30]" : "border-transparent text-[#52656b] hover:text-[#142126]"}`}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="relative w-full sm:w-64">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2"
              style={{ color: "var(--color-brown-300)" }}
            />
            <input
              type="text"
              placeholder="Search lines…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 rounded-lg text-sm border outline-none transition-colors duration-200"
              style={{
                borderColor: "var(--color-sand-200)",
                backgroundColor: "var(--color-cream-100)",
                color: "var(--color-brown-800)",
              }}
              onFocus={(e) => {
                e.currentTarget.style.borderColor =
                  "var(--color-amber-300)";
              }}
              onBlur={(e) => {
                e.currentTarget.style.borderColor =
                  "var(--color-sand-200)";
              }}
            />
          </div>
        </div>
      </MotionWrapper>

      {/* Data table */}
      <MotionWrapper direction="up" delay={0.15}>
        <div
          className="rounded-xl border overflow-hidden"
          style={{
            borderColor: "var(--color-sand-200)",
            backgroundColor: "var(--color-cream-100)",
          }}
        >
          <div
            className="overflow-x-auto"
            role="region"
            aria-label="Line items"
            tabIndex={0}
          >
            <table className="w-full text-sm" style={{ minWidth: 720 }}>
              <thead>
                <tr
                  style={{
                    backgroundColor: "var(--color-sand-50)",
                    borderBottom: "1px solid var(--color-sand-200)",
                  }}
                >
                  {["#", "Qty", "UOM", "Manufacturer", "MPN", "Description", "Match", "Status", ""].map(
                    (h) => (
                      <th
                        key={h}
                        className="text-left px-3 sm:px-4 py-3 text-xs font-semibold uppercase tracking-wider whitespace-nowrap"
                        style={{ color: "var(--color-brown-400)" }}
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {filteredLines.map((line, idx) => {
                  const isSelected =
                    selectedLine?.line_id === line.line_id;

                  return (
                    <motion.tr
                      key={line.line_id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: idx * 0.02 }}
                      onClick={() => {
                        setSelectedLine(line);
                        setShowDetail(true);
                      }}
                      className="cursor-pointer transition-colors duration-150"
                      style={{
                        backgroundColor: isSelected
                          ? "var(--color-amber-50)"
                          : "transparent",
                        borderBottom:
                          "1px solid var(--color-sand-200)",
                      }}
                      onMouseEnter={(e) => {
                        if (!isSelected)
                          e.currentTarget.style.backgroundColor =
                            "var(--color-sand-50)";
                      }}
                      onMouseLeave={(e) => {
                        if (!isSelected)
                          e.currentTarget.style.backgroundColor =
                            "transparent";
                      }}
                    >
                      <td
                        className="px-3 sm:px-4 py-2.5 font-mono text-xs"
                        style={{ color: "var(--color-brown-300)" }}
                      >
                        <span className="inline-flex items-center gap-1.5">
                          {line.line_number}
                          {reviewPlan?.sample_line_ids.includes(line.line_id) && (
                            <span className="rounded bg-[#e9e0d3] px-1.5 py-0.5 text-[10px] font-medium text-[#5b4b3d]">sample</span>
                          )}
                          {line.extraction_warnings.some((warning) => warning.code === "LLM_PROPOSED_EXTRACTION") && (
                            <span className="rounded bg-[#e5eef0] px-1.5 py-0.5 text-[10px] font-medium text-[#33464c]">AI</span>
                          )}
                        </span>
                      </td>

                      {/* Qty */}
                      <td
                        className="px-3 sm:px-4 py-2.5 cursor-text"
                        onDoubleClick={() =>
                          handleStartEdit(
                            line.line_id,
                            "quantity",
                            String(line.quantity ?? "")
                          )
                        }
                      >
                        {editingCell?.lineId === line.line_id &&
                        editingCell.field === "quantity" ? (
                          <input
                            className="w-16 px-2 py-1 rounded text-sm border outline-none"
                            style={{
                              borderColor: "var(--color-amber-400)",
                              backgroundColor: "white",
                            }}
                            value={editValue}
                            onChange={(e) =>
                              setEditValue(e.target.value)
                            }
                            onKeyDown={handleKeyDown}
                            onBlur={handleSaveEdit}
                            autoFocus
                          />
                        ) : line.quantity != null ? (
                          <span
                            className="font-medium"
                            style={{
                              color: "var(--color-brown-700)",
                            }}
                          >
                            {line.quantity}
                          </span>
                        ) : (
                          <span
                            style={{
                              color: "var(--color-brown-300)",
                            }}
                          >
                            —
                          </span>
                        )}
                      </td>

                      {/* Unit of measure */}
                      <td className="px-3 sm:px-4 py-2.5 whitespace-nowrap">
                        {editingCell?.lineId === line.line_id &&
                        editingCell.field === "unit" ? (
                          <input
                            className="w-20 px-2 py-1 rounded text-sm border outline-none"
                            style={{
                              borderColor: "var(--color-amber-400)",
                              backgroundColor: "white",
                            }}
                            aria-label={`Unit of measure for line ${line.line_number}`}
                            value={editValue}
                            onChange={(e) => setEditValue(e.target.value)}
                            onKeyDown={handleKeyDown}
                            onBlur={handleSaveEdit}
                            onClick={(e) => e.stopPropagation()}
                            autoFocus
                          />
                        ) : (
                          <button
                            type="button"
                            aria-label={`${line.unit?.trim() ? "Edit" : "Set"} unit of measure for line ${line.line_number}`}
                            title="Edit unit of measure"
                            className="rounded px-1.5 py-1 text-left text-sm underline decoration-dotted underline-offset-2 hover:bg-[var(--color-sand-50)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--color-amber-500)]"
                            style={{
                              color: line.unit?.trim()
                                ? "var(--color-brown-700)"
                                : "var(--color-warning-700)",
                            }}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleStartEdit(line.line_id, "unit", line.unit ?? "");
                            }}
                          >
                            {line.unit?.trim() || "Missing"}
                          </button>
                        )}
                      </td>

                      {/* Manufacturer */}
                      <td
                        className="px-3 sm:px-4 py-2.5 cursor-text max-w-[120px]"
                        onDoubleClick={() =>
                          handleStartEdit(
                            line.line_id,
                            "requested_manufacturer",
                            line.requested_manufacturer ?? ""
                          )
                        }
                      >
                        {editingCell?.lineId === line.line_id &&
                        editingCell.field ===
                          "requested_manufacturer" ? (
                          <input
                            className="w-full px-2 py-1 rounded text-sm border outline-none"
                            style={{
                              borderColor: "var(--color-amber-400)",
                              backgroundColor: "white",
                            }}
                            value={editValue}
                            onChange={(e) =>
                              setEditValue(e.target.value)
                            }
                            onKeyDown={handleKeyDown}
                            onBlur={handleSaveEdit}
                            autoFocus
                          />
                        ) : line.requested_manufacturer ? (
                          <span
                            className="truncate block max-w-[120px]"
                            style={{
                              color: "var(--color-brown-700)",
                            }}
                            title={line.requested_manufacturer}
                          >
                            {line.requested_manufacturer}
                          </span>
                        ) : (
                          <span
                            style={{
                              color: "var(--color-brown-300)",
                            }}
                          >
                            —
                          </span>
                        )}
                      </td>

                      {/* MPN */}
                      <td
                        className="px-3 sm:px-4 py-2.5 cursor-text"
                        onDoubleClick={() =>
                          handleStartEdit(
                            line.line_id,
                            "requested_mpn",
                            line.requested_mpn ?? ""
                          )
                        }
                      >
                        {editingCell?.lineId === line.line_id &&
                        editingCell.field === "requested_mpn" ? (
                          <input
                            className="w-full px-2 py-1 rounded text-sm border outline-none font-mono"
                            style={{
                              borderColor: "var(--color-amber-400)",
                              backgroundColor: "white",
                            }}
                            value={editValue}
                            onChange={(e) =>
                              setEditValue(e.target.value)
                            }
                            onKeyDown={handleKeyDown}
                            onBlur={handleSaveEdit}
                            autoFocus
                          />
                        ) : line.requested_mpn ? (
                          <code
                            className="text-xs px-1.5 py-0.5 rounded font-mono"
                            style={{
                              backgroundColor:
                                "var(--color-sand-100)",
                              color: "var(--color-brown-700)",
                            }}
                          >
                            {line.requested_mpn}
                          </code>
                        ) : (
                          <span
                            style={{
                              color: "var(--color-brown-300)",
                            }}
                          >
                            —
                          </span>
                        )}
                      </td>

                      {/* Description */}
                      <td
                        className="px-3 sm:px-4 py-2.5 max-w-[180px]"
                        title={line.description || undefined}
                      >
                        <span
                          className="truncate block max-w-[180px] text-xs"
                          style={{ color: "var(--color-brown-500)" }}
                        >
                          {line.description || "—"}
                        </span>
                      </td>

                      {/* Match */}
                      <td className="px-3 sm:px-4 py-2.5 whitespace-nowrap">
                        {line.match_status === "EXACT_MATCH" && (
                          <span
                            className="inline-flex items-center gap-1 text-xs font-medium"
                            style={{
                              color: "var(--color-success-600)",
                            }}
                          >
                            <CheckCircle size={13} /> Exact
                          </span>
                        )}
                        {line.match_status === "COLLISION" && (
                          <span
                            className="inline-flex items-center gap-1 text-xs font-medium"
                            style={{
                              color: "var(--color-warning-600)",
                            }}
                          >
                            <AlertTriangle size={13} /> Ambiguous
                          </span>
                        )}
                        {line.match_status === "MANUAL_OVERRIDE" && (
                          <span
                            className="inline-flex items-center gap-1 text-xs font-medium"
                            style={{
                              color: "var(--color-info-600)",
                            }}
                          >
                            <CheckCircle size={13} /> Manual
                          </span>
                        )}
                        {line.match_status === "NO_MATCH" && (
                          <span
                            className="inline-flex items-center gap-1 text-xs font-medium"
                            style={{
                              color: "var(--color-brown-300)",
                            }}
                          >
                            <XCircle size={13} /> None
                          </span>
                        )}
                      </td>

                      {/* Status */}
                      <td className="px-3 sm:px-4 py-2.5">
                        <StatusBadge status={line.review_decision} size="sm" />
                      </td>

                      {/* Actions */}
                      <td className="px-3 sm:px-4 py-2.5">
                        {line.review_decision !== "APPROVED" && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleApprove(line.line_id);
                            }}
                            title="Approve"
                            aria-label={`Approve line ${line.line_number}`}
                            className="inline-flex items-center justify-center w-7 h-7 rounded-md border transition-all duration-200 active:scale-90"
                            style={{
                              backgroundColor:
                                "var(--color-success-50)",
                              borderColor:
                                "var(--color-success-100)",
                              color: "var(--color-success-600)",
                            }}
                          >
                            <Check size={14} />
                          </button>
                        )}
                      </td>
                    </motion.tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {filteredLines.length === 0 && (
            <div className="py-12 text-center">
              <p
                className="text-sm"
                style={{ color: "var(--color-brown-400)" }}
              >
                No lines match the current filter.
              </p>
            </div>
          )}
        </div>
      </MotionWrapper>

      {/* Detail Panel */}
      <AnimatePresence>
        {selectedLine && showDetail && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="mt-4 rounded-xl border p-4 sm:p-5"
            style={{
              backgroundColor: "var(--color-cream-100)",
              borderColor: "var(--color-sand-200)",
            }}
          >
            <div className="flex items-center justify-between mb-3">
              <h3
                className="text-sm font-semibold flex items-center gap-2"
                style={{ color: "var(--color-brown-700)" }}
              >
                <Info size={15} />
                Line detail
              </h3>
              <button
                onClick={() => setShowDetail(false)}
                className="p-1 rounded-md transition-colors"
                style={{ color: "var(--color-brown-300)" }}
              >
                <XIcon size={16} />
              </button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2 text-sm">
              <div>
                <dt
                  className="text-xs font-semibold uppercase tracking-wider mb-0.5"
                  style={{ color: "var(--color-brown-400)" }}
                >
                  Source
                </dt>
                <dd style={{ color: "var(--color-brown-700)" }}>
                  {formatLocator(selectedLine.source_locator)}
                  <div className="mt-2">
                    {caseData.source_file?.file_name.toLowerCase().endsWith(".xlsx") &&
                    selectedLine.source_locator.sheet_name && selectedLine.source_locator.row_number ? (
                      <button type="button" onClick={() => setShowSourcePreview(true)} className="rfq-secondary">
                        Open source row and cells
                      </button>
                    ) : caseData.source_file?.file_name.toLowerCase().endsWith(".pdf") && selectedLine.source_locator.page_number ? (
                      <button type="button" onClick={() => setShowPdfSourcePreview(true)} className="rfq-secondary">
                        View original page
                      </button>
                    ) : (
                      <a
                        href={`/api/proxy/api/rfqs/${encodeURIComponent(caseData.case_id)}/source${selectedLine.source_locator.page_number ? `#page=${selectedLine.source_locator.page_number}` : ""}`}
                        target="_blank"
                        rel="noreferrer"
                        className="rfq-secondary inline-flex"
                      >
                        Open original source{selectedLine.source_locator.page_number ? ` · page ${selectedLine.source_locator.page_number}` : ""}
                      </a>
                    )}
                  </div>
                </dd>
              </div>
              <div>
                <dt
                  className="text-xs font-semibold uppercase tracking-wider mb-0.5"
                  style={{ color: "var(--color-brown-400)" }}
                >
                  Review decision
                </dt>
                <dd>
                  <StatusBadge status={selectedLine.review_decision} size="sm" />
                </dd>
              </div>
              <div>
                <dt
                  className="text-xs font-semibold uppercase tracking-wider mb-0.5"
                  style={{ color: "var(--color-brown-400)" }}
                >
                  Extraction status
                </dt>
                <dd style={{ color: "var(--color-brown-700)" }}>
                  {selectedLine.extraction_status}
                </dd>
              </div>
              <div>
                <dt
                  className="text-xs font-semibold uppercase tracking-wider mb-0.5"
                  style={{ color: "var(--color-brown-400)" }}
                >
                  Match status
                </dt>
                <dd style={{ color: "var(--color-brown-700)" }}>
                  {selectedLine.match_status}
                </dd>
              </div>
              {selectedLine.catalog_rematch_required && (
                <div className="sm:col-span-2 rounded-lg border border-[#e8c887] bg-[#fff9eb] p-3" role="alert">
                  <p className="text-sm font-medium text-[#68460b]">The catalog has changed since this match.</p>
                  <p className="mt-1 text-xs text-[#765a27]">Refresh the match and review it again before preparing a validated worksheet.</p>
                  <button
                    type="button"
                    className="rfq-secondary mt-3"
                    disabled={rematchingLineId === selectedLine.line_id}
                    onClick={() => void handleRematch(selectedLine)}
                  >
                    {rematchingLineId === selectedLine.line_id ? "Refreshing match…" : "Refresh catalog match"}
                  </button>
                </div>
              )}
              <div className="sm:col-span-2">
                <dt
                  className="text-xs font-semibold uppercase tracking-wider mb-0.5"
                  style={{ color: "var(--color-brown-400)" }}
                >
                  Raw text
                </dt>
                <dd>
                  <code
                    className="text-xs block p-2 rounded-lg break-words whitespace-pre-wrap"
                    style={{
                      backgroundColor: "var(--color-sand-50)",
                      color: "var(--color-brown-600)",
                    }}
                  >
                    {selectedLine.raw_text || "—"}
                  </code>
                </dd>
              </div>
              {Object.keys(selectedLine.field_provenance ?? {}).length > 0 && (
                <div className="sm:col-span-2 rounded-lg border border-[var(--color-sand-200)] p-3">
                  <dt className="text-xs font-semibold uppercase tracking-wider mb-2 text-[var(--color-brown-400)]">
                    Field sources
                  </dt>
                  <dd className="space-y-2">
                    {Object.entries(selectedLine.field_provenance ?? {}).map(([field, provenance]) => (
                      <div key={field} className="grid grid-cols-[minmax(90px,0.7fr)_minmax(0,2fr)] gap-3 text-xs">
                        <span className="font-medium text-[var(--color-brown-600)]">{field.replaceAll("_", " ")}</span>
                        <span className="min-w-0 break-words text-[var(--color-brown-700)]">
                          <span className="font-medium">{fieldOriginLabel(provenance.origin)}</span>
                          {provenance.raw_value != null && <> · source “{provenance.raw_value}”</>}
                          {provenance.proposed_value != null && provenance.proposed_value !== provenance.raw_value && <> · extracted “{provenance.proposed_value}”</>}
                          <span className="text-[var(--color-brown-400)]"> · {fieldValidationLabel(provenance.validation_status)} · {provenance.review_status.toLowerCase().replaceAll("_", " ")}</span>
                          {provenance.source_locator.sheet_name && <> · {provenance.source_locator.sheet_name}</>}
                          {provenance.source_locator.row_number && <> row {provenance.source_locator.row_number}</>}
                          {provenance.source_locator.page_number && <> · page {provenance.source_locator.page_number}</>}
                          {provenance.evidence && <span className="mt-0.5 block text-[var(--color-brown-400)]">{provenance.evidence}</span>}
                        </span>
                      </div>
                    ))}
                  </dd>
                </div>
              )}
              {selectedLine.extraction_warnings.length > 0 && (
                <div className="sm:col-span-2">
                  <dt
                    className="text-xs font-semibold uppercase tracking-wider mb-0.5"
                    style={{ color: "var(--color-warning-600)" }}
                  >
                    Warnings
                  </dt>
                  <dd className="text-xs space-y-1">
                    {selectedLine.extraction_warnings.map((warning) => (
                      <p
                        key={`${warning.code}-${warning.message}`}
                        style={{ color: "var(--color-warning-700)" }}
                      >
                        <strong>{warning.code}</strong>: {warning.message}
                      </p>
                    ))}
                  </dd>
                </div>
              )}
              {selectedLine.selected_catalog_sku && (
                <div>
                  <dt
                    className="text-xs font-semibold uppercase tracking-wider mb-0.5"
                    style={{ color: "var(--color-brown-400)" }}
                  >
                    Selected catalog SKU
                  </dt>
                  <dd>
                    <code
                      className="text-xs px-1.5 py-0.5 rounded font-mono"
                      style={{
                        backgroundColor: "var(--color-success-50)",
                        color: "var(--color-success-700)",
                      }}
                    >
                      {selectedLine.selected_catalog_sku}
                    </code>
                  </dd>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {showSourcePreview && selectedLine?.source_locator.sheet_name && selectedLine.source_locator.row_number && (
        <SourcePreviewDialog
          caseId={caseData.case_id}
          sheetName={selectedLine.source_locator.sheet_name}
          rowNumber={selectedLine.source_locator.row_number}
          targetCells={Object.values(selectedLine.source_locator.field_source_cells ?? {})}
          onClose={closeSourcePreview}
        />
      )}
      {showPdfSourcePreview && selectedLine?.source_locator.page_number && (
        <PdfSourcePreviewDialog
          caseId={caseData.case_id}
          locator={selectedLine.source_locator}
          onClose={closePdfSourcePreview}
        />
      )}
    </div>
  );
}
