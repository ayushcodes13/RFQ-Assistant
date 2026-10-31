"use client";

import { ArrowRight, FilePlus2, RefreshCw } from "lucide-react";
import { RFQCase } from "@/types";
import { StatusBadge } from "@/components/ui/StatusBadge";

interface OverviewViewProps {
  cases: RFQCase[];
  loading: boolean;
  error?: string | null;
  onOpenNewRfq: () => void;
  onOpenInbox: () => void;
  onSelectCase: (caseId: string) => void;
  onRefresh: () => void;
}

const stages = [
  { id: "NEEDS_REVIEW", label: "Needs review", color: "#a96c0b" },
  { id: "PROCESSING", label: "Processing", color: "#2e6685" },
  { id: "READY_TO_EXPORT", label: "Ready to draft", color: "#26704c" },
  { id: "EXPORTED", label: "Draft prepared", color: "#52656b" },
  { id: "FAILED", label: "Failed", color: "#a52e27" },
] as const;

function countStatus(cases: RFQCase[], status: string) {
  return cases.filter((item) => item.status === status).length;
}

function createdLabel(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" }).format(date);
}

function plural(value: number, singular: string, pluralWord = `${singular}s`) {
  return `${value} ${value === 1 ? singular : pluralWord}`;
}

export function OverviewView({
  cases,
  loading,
  error,
  onOpenNewRfq,
  onOpenInbox,
  onSelectCase,
  onRefresh,
}: OverviewViewProps) {
  const reviewCases = cases
    .filter((item) => item.status === "NEEDS_REVIEW" || item.status === "FAILED")
    .sort((a, b) => a.created_at.localeCompare(b.created_at));
  const queue = (reviewCases.length > 0 ? reviewCases : cases)
    .slice(0, 5);
  const openCount = cases.filter((item) => item.status !== "EXPORTED").length;
  const unresolvedLines = cases.reduce((total, item) => total + (item.status === "EXPORTED" ? 0 : item.unresolved_count), 0);
  const readyCount = countStatus(cases, "READY_TO_EXPORT");
  const maxStageCount = Math.max(1, ...stages.map((stage) => countStatus(cases, stage.id)));

  return (
    <div className="rfq-content">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="rfq-page-title">Overview</h1>
          <p className="rfq-subtitle">
            {loading
              ? "Loading your RFQ workload."
              : reviewCases.length > 0
                ? `${plural(reviewCases.length, "request")} ${reviewCases.length === 1 ? "needs" : "need"} attention before a draft can be prepared.`
                : cases.length > 0
                  ? "No requests are waiting for review. Here is your current workload."
                  : "Your quotation workload, ready when the first request arrives."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="rfq-secondary" onClick={onRefresh} disabled={loading}>
            <RefreshCw size={15} aria-hidden="true" />
            Refresh
          </button>
          <button type="button" className="rfq-primary" onClick={onOpenNewRfq}>
            <FilePlus2 size={16} aria-hidden="true" />
            New RFQ
          </button>
        </div>
      </div>

      {error && (
        <div className="mt-5 flex items-center justify-between gap-4 rounded-md border border-[#f0c7c1] bg-[#fff7f5] px-4 py-3 text-[13px] text-[#84241f]" role="alert">
          <span>{error}</span>
          <button type="button" className="shrink-0 font-medium underline underline-offset-2" onClick={onRefresh}>Retry</button>
        </div>
      )}

      <section aria-label="RFQ workload summary" className="rfq-panel mt-6 grid grid-cols-1 divide-y divide-[#e8edef] sm:grid-cols-3 sm:divide-x sm:divide-y-0">
        <Metric label="Open requests" value={loading ? "—" : openCount} note="Not yet exported" />
        <Metric label="Unresolved lines" value={loading ? "—" : unresolvedLines} note="Across all open requests" />
        <Metric label="Ready to draft" value={loading ? "—" : readyCount} note="Reviewed and eligible for worksheet" />
      </section>

      <div className="mt-6 grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
        <section className="min-w-0" aria-labelledby="attention-heading">
          <div className="mb-2 flex items-baseline justify-between gap-4">
            <div>
              <h2 id="attention-heading" className="rfq-section-title">{reviewCases.length > 0 ? "Needs attention" : "Recent requests"}</h2>
              <p className="mt-1 text-[13px] text-[#52656b]">
                {reviewCases.length > 0
                  ? "Open a request to check its source and resolve the flagged lines."
                  : "Your latest requests, with their current review state."}
              </p>
            </div>
            {cases.length > 0 && (
              <button type="button" className="inline-flex shrink-0 items-center gap-1 text-[13px] font-medium text-[#3d5056] hover:text-[#a83e1c]" onClick={onOpenInbox}>
                View inbox <ArrowRight size={14} aria-hidden="true" />
              </button>
            )}
          </div>

          <div className="mt-3 border-t border-[#e1e8ea]">
            {loading ? (
              <div className="space-y-0" aria-label="Loading requests">
                {[0, 1, 2].map((item) => <div key={item} className="flex min-h-[66px] items-center gap-4 border-b border-[#edf1f2] px-3"><span className="h-4 w-1/3 rounded bg-[#e9eff1]" /><span className="h-4 w-24 rounded bg-[#f1f5f6]" /></div>)}
              </div>
            ) : queue.length > 0 ? (
              queue.map((item) => (
                <button
                  type="button"
                  key={item.case_id}
                  className="rfq-list-row w-full grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_minmax(120px,180px)_auto]"
                  onClick={() => onSelectCase(item.case_id)}
                  aria-label={`Open ${item.title || item.case_id}`}
                >
                  <span className="flex min-w-0 items-center gap-3">
                    <span className="rfq-status-mark" style={{ color: item.status === "FAILED" ? "#a52e27" : "#a96c0b" }} />
                    <span className="min-w-0">
                      <span className="block truncate text-[14px] font-medium text-[#1d2b30]">{item.title || item.case_id}</span>
                      <span className="mt-0.5 block truncate text-[12px] text-[#52656b]">
                        {item.customer_label || "Customer not specified"} · {plural(item.line_count, "line")}
                      </span>
                    </span>
                  </span>
                  <span className="hidden justify-self-start sm:inline-flex"><StatusBadge status={item.status} size="sm" /></span>
                  <span className="flex items-center gap-3 justify-self-end text-right">
                    <span className="hidden text-[12px] tabular-nums text-[#52656b] md:inline">{createdLabel(item.created_at)}</span>
                    <ArrowRight size={15} className="text-[#667980]" aria-hidden="true" />
                  </span>
                </button>
              ))
            ) : (
              <div className="rounded-b-md border-b border-[#e1e8ea] bg-[#fafcfc] px-5 py-7">
                <p className="text-[14px] font-medium text-[#1d2b30]">No RFQs yet</p>
                <p className="mt-1 max-w-lg text-[13px] text-[#52656b]">Add a request from pasted email text, CSV, XLSX, or a native PDF. The original source stays available while you review each line.</p>
                <p className="mt-3 text-[12px] text-[#52656b]">Use <span className="font-medium text-[#3d5056]">New RFQ</span> above to get started.</p>
              </div>
            )}
          </div>
        </section>

        <section aria-labelledby="stage-heading" className="min-w-0">
          <div className="mb-2">
            <h2 id="stage-heading" className="rfq-section-title">By stage</h2>
            <p className="mt-1 text-[13px] text-[#52656b]">Current case count by workflow state.</p>
          </div>
          <div className="rfq-panel mt-3 p-4">
            {!loading && cases.length === 0 ? (
              <ol className="divide-y divide-[#e8edef]">
                {[
                  ["01", "Add a request", "Paste email text or upload a supported file."],
                  ["02", "Review each line", "Confirm quantities and exact catalog matches."],
                  ["03", "Prepare a draft", "Export a worksheet after every line is reviewed."],
                ].map(([number, title, detail]) => (
                  <li key={number} className="flex gap-3 py-3 first:pt-1 last:pb-1">
                    <span className="rfq-mono pt-0.5 text-[11px] text-[#a83e1c]">{number}</span>
                    <span>
                      <span className="block text-[13px] font-medium text-[#1d2b30]">{title}</span>
                      <span className="mt-0.5 block text-[12px] leading-[18px] text-[#52656b]">{detail}</span>
                    </span>
                  </li>
                ))}
              </ol>
            ) : (
            stages.map((stage, index) => {
              const count = countStatus(cases, stage.id);
              const width = count === 0 ? 0 : Math.max(8, Math.round((count / maxStageCount) * 100));
              return (
                <div key={stage.id} className={index === 0 ? "" : "mt-4"}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-3 text-[13px]">
                    <span className="min-w-0 truncate text-[#3d5056]">{stage.label}</span>
                    <span className="rfq-mono shrink-0 text-[13px] text-[#1d2b30]">{loading ? "—" : count}</span>
                  </div>
                  <div className="rfq-bar-track" role="img" aria-label={`${stage.label}: ${loading ? "loading" : count}`}>
                    <div className="rfq-bar-fill" style={{ width: loading ? "0%" : `${width}%`, background: stage.color }} />
                  </div>
                </div>
              );
            })
            )}
            <div className="mt-5 border-t border-[#e8edef] pt-3 text-[12px] leading-[18px] text-[#52656b]">
              Counts reflect saved cases in this local workspace. No sales, pricing, or availability estimates are shown.
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value, note }: { label: string; value: number | string; note: string }) {
  return (
    <div className="px-5 py-4 sm:px-6">
      <p className="text-[13px] text-[#52656b]">{label}</p>
      <p className="rfq-mono mt-1 text-[28px] leading-8 text-[#142126]">{value}</p>
      <p className="mt-1 text-[12px] text-[#52656b]">{note}</p>
    </div>
  );
}
