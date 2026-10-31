"use client";

import { useMemo, useState } from "react";
import { ArrowLeft, ArrowRight, FilePlus2, RefreshCw, Search, SlidersHorizontal } from "lucide-react";
import { RFQCase } from "@/types";
import { StatusBadge } from "@/components/ui/StatusBadge";

interface InboxViewProps {
  cases: RFQCase[];
  loading: boolean;
  error?: string | null;
  onSelectCase: (caseId: string) => void;
  onRefresh: () => void;
  onOpenNewRfq: () => void;
}

const PAGE_SIZE = 20;
const STATUS_FILTERS = [
  ["all", "All statuses"],
  ["NEEDS_REVIEW", "Needs review"],
  ["PROCESSING", "Processing"],
  ["READY_TO_EXPORT", "Ready to draft"],
  ["EXPORTED", "Draft prepared"],
  ["FAILED", "Failed"],
];

function dateLabel(value: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Date unavailable";
  return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", year: "numeric" }).format(date);
}

export function InboxView({ cases, loading, error, onSelectCase, onRefresh, onOpenNewRfq }: InboxViewProps) {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(0);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    return cases.filter((item) => {
      if (status !== "all" && item.status !== status) return false;
      if (!normalized) return true;
      return [item.title, item.customer_label, item.case_id, item.source_file?.file_name]
        .some((field) => field?.toLocaleLowerCase().includes(normalized));
    });
  }, [cases, query, status]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const visible = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="rfq-content">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="rfq-page-title">RFQ inbox</h1>
          <p className="rfq-subtitle">Find a request, open its source, and continue review.</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="rfq-secondary" onClick={onRefresh} disabled={loading}>
            <RefreshCw size={15} aria-hidden="true" />Refresh
          </button>
          <button type="button" className="rfq-primary" onClick={onOpenNewRfq}>
            <FilePlus2 size={16} aria-hidden="true" />New RFQ
          </button>
        </div>
      </div>

      {error && <div className="mt-5 flex items-center justify-between gap-4 rounded-md border border-[#f0c7c1] bg-[#fff7f5] px-4 py-3 text-[13px] text-[#84241f]" role="alert"><span>{error}</span><button type="button" className="shrink-0 font-medium underline underline-offset-2" onClick={onRefresh}>Retry</button></div>}

      <section className="mt-6" aria-label="RFQ list">
        <div className="flex flex-col gap-3 border-b border-[#dfe7e9] pb-3 sm:flex-row sm:items-center sm:justify-between">
          <label className="relative block w-full sm:max-w-[340px]">
            <span className="sr-only">Search RFQs</span>
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#667980]" aria-hidden="true" />
            <input className="h-9 w-full rounded-md border border-[#cbd6d9] bg-white pl-9 pr-3 text-[13px] text-[#1d2b30] placeholder:text-[#667980] focus:border-[#a83e1c] focus:outline-none" type="search" value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); }} placeholder="Search case or customer" />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <SlidersHorizontal size={15} className="text-[#667980]" aria-hidden="true" />
            <label className="sr-only" htmlFor="rfq-status-filter">Filter by status</label>
            <select id="rfq-status-filter" className="h-9 min-w-[156px] rounded-md border border-[#cbd6d9] bg-white px-3 text-[13px] text-[#2b3b40] focus:border-[#a83e1c] focus:outline-none" value={status} onChange={(event) => { setStatus(event.target.value); setPage(0); }}>
              {STATUS_FILTERS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        </div>

        <div className="flex items-center justify-between py-3 text-[12px] text-[#52656b]">
          <p aria-live="polite">{loading ? "Loading requests…" : `${filtered.length} ${filtered.length === 1 ? "request" : "requests"}${filtered.length !== cases.length ? ` of ${cases.length}` : ""}`}</p>
          {!loading && filtered.length > 0 && <p className="rfq-mono">{page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, filtered.length)} / {filtered.length}</p>}
        </div>

        <div className="border-t border-[#dfe7e9]">
          <div className="hidden grid-cols-[minmax(0,1fr)_minmax(110px,150px)_90px_132px] items-center gap-4 py-2 text-[12px] text-[#52656b] sm:grid">
            <span>Request</span><span>Review state</span><span className="text-right">Lines</span><span className="text-right">Received</span>
          </div>
          {loading ? (
            <div aria-label="Loading requests">{[0, 1, 2, 3].map((index) => <div key={index} className="flex min-h-[60px] items-center gap-4 border-b border-[#edf1f2] px-2"><span className="h-4 w-1/3 rounded bg-[#e9eff1]" /><span className="h-4 w-20 rounded bg-[#f1f5f6]" /></div>)}</div>
          ) : visible.length > 0 ? (
            visible.map((item) => (
              <button type="button" className="rfq-list-row w-full grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_minmax(110px,150px)_90px_132px]" key={item.case_id} onClick={() => onSelectCase(item.case_id)} aria-label={`Open ${item.title || item.case_id}`}>
                <span className="min-w-0">
                  <span className="block truncate text-[14px] font-medium text-[#1d2b30]">{item.title || item.case_id}</span>
                  <span className="mt-0.5 block truncate text-[12px] text-[#52656b]">{item.customer_label || "Customer not specified"}{item.source_file?.file_name ? ` · ${item.source_file.file_name}` : ""}</span>
                </span>
                <span className="hidden justify-self-start sm:inline-flex"><StatusBadge status={item.status} size="sm" /></span>
                <span className="hidden justify-self-end text-right text-[13px] tabular-nums text-[#2b3b40] sm:block">{item.line_count}</span>
                <span className="flex items-center gap-3 justify-self-end text-right text-[12px] text-[#52656b]">
                  <span className="sm:hidden"><StatusBadge status={item.status} size="sm" /></span>
                  <span className="hidden sm:inline">{dateLabel(item.created_at)}</span>
                  <ArrowRight size={15} className="text-[#667980]" aria-hidden="true" />
                </span>
                <span className="col-span-2 text-left text-[12px] text-[#52656b] sm:hidden">{item.line_count} {item.line_count === 1 ? "line" : "lines"} · {dateLabel(item.created_at)}{item.unresolved_count > 0 ? ` · ${item.unresolved_count} unresolved` : ""}</span>
              </button>
            ))
          ) : (
            <div className="border-b border-[#e1e8ea] bg-[#fafcfc] px-4 py-8">
              <p className="text-[14px] font-medium text-[#1d2b30]">{cases.length === 0 ? "No RFQs yet" : "No requests match these filters"}</p>
              <p className="mt-1 text-[13px] text-[#52656b]">{cases.length === 0 ? "Add a request from email text, CSV, XLSX, or a readable PDF." : "Try a different search or status."}</p>
              {cases.length === 0 ? <button type="button" className="rfq-primary mt-4" onClick={onOpenNewRfq}><FilePlus2 size={15} />Create first RFQ</button> : <button type="button" className="mt-3 inline-flex items-center gap-2 text-[13px] font-medium text-[#3d5056] hover:text-[#a83e1c]" onClick={() => { setQuery(""); setStatus("all"); setPage(0); }}><ArrowLeft size={14} />Clear filters</button>}
            </div>
          )}
        </div>

        {!loading && pageCount > 1 && (
          <div className="flex items-center justify-between border-b border-[#e1e8ea] py-3">
            <button type="button" className="rfq-secondary" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page === 0}><ArrowLeft size={14} />Previous</button>
            <span className="rfq-mono text-[12px] text-[#52656b]">{page + 1} / {pageCount}</span>
            <button type="button" className="rfq-secondary" onClick={() => setPage((value) => Math.min(pageCount - 1, value + 1))} disabled={page + 1 >= pageCount}>Next<ArrowRight size={14} /></button>
          </div>
        )}
      </section>
    </div>
  );
}
