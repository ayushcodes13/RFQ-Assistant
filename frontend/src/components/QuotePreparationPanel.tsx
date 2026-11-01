"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, FileText, LoaderCircle, ReceiptText, X } from "lucide-react";
import { createCaseQuoteDraft, getCaseQuoteDraft } from "@/services/api";
import { QuoteDraft, QuoteDraftSource, RFQCase } from "@/types";

function money(value?: string | null, currency?: string | null) {
  if (value == null) return "—";
  return currency ? `${currency} ${value}` : `${value} · currency missing`;
}

function sourceLocation(source: QuoteDraftSource) {
  const bbox = source.bbox?.length === 4 ? `document area ${source.bbox.map((value) => `${Math.round(value * 100)}%`).join(", ")}` : null;
  return [source.page != null ? `page ${source.page}` : null, source.sheet ? `sheet ${source.sheet}` : null, source.cell_range ? `cells ${source.cell_range}` : null, bbox].filter(Boolean).join(" · ") || "source excerpt";
}

function sourceHref(caseData: RFQCase, source: QuoteDraftSource) {
  if (source.file_id.startsWith("CATUP-")) {
    const proposalId = source.file_id.slice("CATUP-".length);
    return `/api/proxy/api/catalogs/updates/${encodeURIComponent(proposalId)}/source`;
  }
  const sourceDocument = caseData.source_documents?.find((document) => document.source_file.file_id === source.file_id);
  if (source.file_id.startsWith("RFQ-") || source.file_id === caseData.source_file?.file_id || sourceDocument) {
    const query = sourceDocument ? `?source_file_id=${encodeURIComponent(source.file_id)}` : "";
    const page = source.page == null ? "" : `#page=${source.page}`;
    return `/api/proxy/api/rfqs/${encodeURIComponent(caseData.case_id)}/source${query}${page}`;
  }
  return null;
}

export function QuotePreparationPanel({ caseData }: { caseData: RFQCase }) {
  const [draft, setDraft] = useState<QuoteDraft | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<{ line: number; source: QuoteDraftSource } | null>(null);
  const waitingForExtraction = caseData.status === "PROCESSING" || caseData.status === "NEW";
  const hasNoLines = caseData.line_count === 0;
  const cannotPrepare = waitingForExtraction || hasNoLines;

  useEffect(() => {
    let active = true;
    getCaseQuoteDraft(caseData.case_id).then((saved) => {
      if (active) setDraft(saved);
    }).catch((cause: unknown) => {
      const message = cause instanceof Error ? cause.message : "Quote draft could not be loaded.";
      if (active && !message.includes("404") && !message.toLowerCase().includes("quote draft not found")) setError(message);
    });
    return () => { active = false; };
  }, [caseData.case_id]);

  const prepare = async () => {
    setBusy(true);
    setError(null);
    try {
      setDraft(await createCaseQuoteDraft(caseData.case_id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Quote draft could not be prepared.");
    } finally {
      setBusy(false);
    }
  };

  const statusText = draft?.quote_proposal_status === "grounded"
    ? "Buyer and distributor evidence mapped"
    : draft?.quote_proposal_status === "failed"
      ? "Evidence mapping failed; human review required"
      : draft?.quote_proposal_status === "not_configured"
        ? "Catalog values only; Luna evidence mapping is not configured"
        : "No authoritative prices retrieved";

  return (
    <section className="mb-4 rounded-lg border border-[#d7e1e3] bg-white px-4 py-3" aria-labelledby="quote-preparation-heading">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="quote-preparation-heading" className="text-sm font-semibold text-[#1d2b30]">Quote preparation</h2>
          <p className="mt-0.5 text-xs text-[#52656b]">Build a source-linked draft for review. This does not approve or send a quotation.</p>
        </div>
        <button type="button" className="rfq-secondary" disabled={busy || cannotPrepare} onClick={() => void prepare()}>
          {busy ? <LoaderCircle size={15} className="animate-spin" aria-hidden="true" /> : <ReceiptText size={15} aria-hidden="true" />}
          {busy ? "Preparing draft…" : draft ? "Refresh quote draft" : "Prepare quote draft"}
        </button>
      </div>

      {cannotPrepare && <p className="mt-3 text-xs text-[#78500a]" role="status">{waitingForExtraction ? "Wait for extraction to finish before preparing a quote." : "Add or recover a request line before preparing a quote."}</p>}

      {error && <p className="mt-3 text-sm text-[#84241f]" role="alert">{error}</p>}
      {!draft && !busy && <p className="mt-3 text-xs text-[#667980]">No quote draft prepared yet. Extract and review the request first, then prepare a draft to see catalog prices and source evidence.</p>}
      {draft && <>
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 border-y border-[#edf1f2] py-2 text-xs text-[#52656b]">
          <span className="font-medium text-[#26373d]">{draft.quote_id}</span>
          <span className="flex items-center gap-1.5"><CheckCircle2 size={13} aria-hidden="true" />{statusText}</span>
          <span>{draft.lines.length} {draft.lines.length === 1 ? "line" : "lines"}</span>
          <span>Draft total: <strong className="font-semibold text-[#26373d]">{money(draft.total_amount, draft.currency)}</strong></span>
        </div>
        {(draft.validation_errors.length > 0 || draft.quote_proposal_warnings.length > 0) && <div className="mt-3 space-y-1 rounded-md bg-[#fff8eb] px-3 py-2 text-xs text-[#78500a]" role="status">
          {draft.validation_errors.map((item, index) => <p key={`validation-${index}`} className="flex gap-2"><AlertTriangle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />{item}</p>)}
          {draft.quote_proposal_warnings.map((item, index) => <p key={`warning-${index}`} className="flex gap-2"><AlertTriangle size={13} className="mt-0.5 shrink-0" aria-hidden="true" />{item}</p>)}
        </div>}
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse text-left text-[12px]">
            <thead><tr className="border-b border-[#dfe7e9] text-[#52656b]"><th className="py-2 pr-3 font-medium">Requested part</th><th className="py-2 pr-3 text-right font-medium">Qty requested</th><th className="py-2 pr-3 text-right font-medium">Catalog stock</th><th className="py-2 pr-3 text-right font-medium">Unit price</th><th className="py-2 pr-3 text-right font-medium">Line total</th><th className="py-2 pr-3 font-medium">Review</th><th className="py-2 font-medium">Evidence</th></tr></thead>
            <tbody>{draft.lines.map((line) => {
              const lineErrors = draft.validation_errors.filter((item) => item.startsWith(`Line ${line.line_no}:`));
              return <tr key={line.line_no} className="border-b border-[#edf1f2] align-top">
                <th scope="row" className="py-2 pr-3 font-medium text-[#1d2b30]">{line.requested_mpn}<span className="mt-0.5 block font-normal text-[#667980]">{line.requested_manufacturer || line.description || "Manufacturer or description not supplied"}</span></th>
                <td className="py-2 pr-3 text-right tabular-nums">{line.quantity == null ? "—" : `${line.quantity} ${line.unit}`}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{line.stock_qty == null ? "Not recorded" : line.stock_qty}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{money(line.unit_price, line.currency)}</td>
                <td className="py-2 pr-3 text-right tabular-nums">{money(line.line_total, line.currency)}</td>
                <td className="py-2 pr-3">{lineErrors.length ? <span className="text-[#84241f]">Needs review</span> : line.requires_human_review ? <span className="text-[#78500a]">Operator review</span> : <span className="text-[#52656b]">Ready for review</span>}</td>
                <td className="py-2">{(() => {
                  const visibleSources = line.sources.filter((source) => !(caseData.source_type === "EMAIL_TEXT" && !source.file_id.startsWith("CAT")));
                  return visibleSources.length ? <div className="flex flex-wrap gap-x-2 gap-y-1">{visibleSources.map((source, index) => <button key={`${source.file_id}-${index}`} type="button" className="inline-flex items-center gap-1 text-left font-medium text-[#344b53] underline underline-offset-2" onClick={() => setSelectedSource({ line: line.line_no, source })} aria-label={`Show evidence for line ${line.line_no}, ${sourceLocation(source)}`}><FileText size={12} aria-hidden="true" />{source.file_id.startsWith("CAT") ? "Catalog" : "Buyer"} · {sourceLocation(source)}</button>)}</div> : caseData.source_type === "EMAIL_TEXT" ? <span className="text-[#667980]">Pasted request text</span> : <span className="text-[#667980]">No source reference</span>;
                })()}</td>
              </tr>;
            })}</tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] leading-4 text-[#667980]">Prices come from the current catalog. A missing quantity, price, exact match, or source stays unresolved; totals are calculated with Decimal only when every line has the required values.</p>
      </>}

      {selectedSource && <div className="fixed inset-0 z-[80]" role="presentation">
        <button type="button" className="absolute inset-0 bg-black/30" onClick={() => setSelectedSource(null)} aria-label="Close evidence drawer" />
        <aside className="absolute inset-y-0 right-0 flex w-full max-w-[440px] flex-col border-l border-[#d7e1e3] bg-white shadow-xl" role="dialog" aria-modal="true" aria-labelledby="quote-evidence-title">
          <div className="flex items-start justify-between gap-4 border-b border-[#e4eaec] px-5 py-4"><div><h3 id="quote-evidence-title" className="text-base font-semibold text-[#1d2b30]">Source evidence</h3><p className="mt-1 text-xs text-[#52656b]">Line {selectedSource.line} · {sourceLocation(selectedSource.source)}</p></div><button type="button" className="rounded p-1 text-[#52656b] hover:bg-[#f2f5f6]" onClick={() => setSelectedSource(null)} aria-label="Close evidence drawer"><X size={18} /></button></div>
          <div className="flex-1 overflow-y-auto px-5 py-4"><p className="text-xs font-medium text-[#52656b]">{selectedSource.source.file_id.startsWith("CATUP-") ? "Accepted distributor update" : selectedSource.source.file_id.startsWith("CAT-") ? "Active distributor catalog" : "Buyer request"}</p><blockquote className="mt-3 border-l-2 border-[#a83e1c] pl-3 text-sm leading-6 text-[#26373d]">{selectedSource.source.text_excerpt || "No text excerpt was stored for this source."}</blockquote>
            {sourceHref(caseData, selectedSource.source) ? <a className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-[#344b53] underline underline-offset-2" href={sourceHref(caseData, selectedSource.source)!} target="_blank" rel="noreferrer"><FileText size={15} aria-hidden="true" />Open original source{selectedSource.source.page != null ? ` · page ${selectedSource.source.page}` : ""}</a> : <p className="mt-5 text-xs text-[#667980]">This catalog citation is a stored catalog record excerpt and does not have a separate source document to open.</p>}
            {selectedSource.source.bbox?.length === 4 ? <p className="mt-5 text-xs leading-5 text-[#667980]">Parser-recorded document area: {selectedSource.source.bbox.map((value) => `${Math.round(value * 100)}%`).join(", ")}. The original file opens above; the page viewer does not draw this quote-level box yet.</p> : <p className="mt-5 text-xs leading-5 text-[#667980]">The quote draft stores page, sheet, or cell location when available. No bounding box was recorded for this source.</p>}
          </div>
        </aside>
      </div>}
    </section>
  );
}
