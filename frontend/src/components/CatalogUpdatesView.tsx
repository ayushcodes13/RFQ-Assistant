"use client";

import { useEffect, useRef, useState } from "react";
import { Check, FileUp, LoaderCircle, RefreshCw, Send, X, Sparkles } from "lucide-react";
import {
  listCatalogUpdateProposals,
  reviewCatalogUpdates,
  stageCatalogUpdate,
} from "@/services/api";
import { CatalogItem, CatalogUpdateProposal } from "@/types";

function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return String(value);
}

function proposalLabel(proposal: CatalogUpdateProposal): string {
  if (proposal.change_type === "new") return "New item";
  if (proposal.change_type === "changed") return "Changed information";
  if (proposal.change_type === "unchanged") return "No data change";
  return "Needs clarification";
}

function CatalogChange({
  proposal,
  onReview,
  onRevise,
  selectedDecision,
  busy,
}: {
  proposal: CatalogUpdateProposal;
  onReview: (proposalId: string, decision: "accept" | "reject") => void;
  selectedDecision?: "accept" | "reject";
  onRevise: (proposalId: string, text: string) => void;
  busy: boolean;
}) {
  const [revision, setRevision] = useState("");
  const changedFields = proposal.changed_fields ?? {};
  const proposedValues = proposal.proposed_values ?? {};
  const blockingReasons = proposal.blocking_reasons ?? [];
  const sourceWarnings = proposal.source_warnings ?? [];
  const currentValues = (proposal.current_item ?? {}) as unknown as Record<string, unknown>;
  const rows = Object.entries(changedFields).length
    ? Object.entries(changedFields)
    : Object.entries(proposedValues).map(([field, proposed]) => [field, { current: currentValues[field] ?? null, proposed }] as const);
  const unchanged = proposal.change_type === "unchanged";
  const canAccept = proposal.review_status === "pending" && blockingReasons.length === 0 && !unchanged;

  return (
    <article className="border-b border-[#e8edef] py-5 last:border-0" aria-labelledby={`proposal-${proposal.proposal_id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 id={`proposal-${proposal.proposal_id}`} className="text-[15px] font-semibold text-[#142126]">
              {displayValue(proposedValues.internal_sku || proposal.current_item?.internal_sku || proposedValues.manufacturer_part_number || proposal.current_item?.manufacturer_part_number)}
            </h3>
            <span className="text-[12px] text-[#52656b]">{proposalLabel(proposal)}</span>
            <span className="text-[12px] text-[#667980]">· {unchanged ? "no review needed" : proposal.review_status}</span>
          </div>
          <p className="mt-1 text-[12px] text-[#52656b]">{proposal.source_name} · {proposal.source_locator.sheet_name ? `${proposal.source_locator.sheet_name}, ` : ""}{proposal.source_locator.row_number ? `row ${proposal.source_locator.row_number}` : proposal.source_locator.page_number ? `page ${proposal.source_locator.page_number}` : "source text"} · <a className="font-medium underline underline-offset-2" href={`/api/proxy/api/catalogs/updates/${encodeURIComponent(proposal.proposal_id)}/source`} target="_blank" rel="noreferrer">Open original source</a></p>
        </div>
        {proposal.review_status === "pending" && !unchanged && (
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" className={selectedDecision === "reject" ? "rfq-primary" : "rfq-secondary"} disabled={busy} aria-pressed={selectedDecision === "reject"} onClick={() => onReview(proposal.proposal_id, "reject")} aria-label={`Mark proposal ${proposal.proposal_id} rejected`}><X size={15} aria-hidden="true" />{selectedDecision === "reject" ? "Marked to reject" : "Reject"}</button>
            <button type="button" className={selectedDecision === "accept" ? "rfq-primary" : "rfq-secondary"} disabled={!canAccept || busy} aria-pressed={selectedDecision === "accept"} onClick={() => onReview(proposal.proposal_id, "accept")} aria-label={`Mark proposal ${proposal.proposal_id} accepted`}><Check size={15} aria-hidden="true" />{selectedDecision === "accept" ? "Marked to accept" : "Accept change"}</button>
          </div>
        )}
      </div>

      {unchanged && <p className="mt-3 text-[13px] text-[#52656b]">This source matches the active catalog. No update is needed.</p>}
      {(proposal.clear_fields?.length ?? 0) > 0 && <p className="mt-3 rounded-md border border-[#ead8c6] bg-[#fbf5ee] px-3 py-2 text-[13px] text-[#6f452c]">This proposal clears the stored {proposal.clear_fields?.map((field) => field.replaceAll("_", " ")).join(" and ")}. The catalog changes only if you mark this to accept and click Review done.</p>}
      {rows.length > 0 && <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[430px] border-collapse text-left text-[13px]">
          <thead><tr className="text-[12px] font-medium text-[#52656b]"><th className="pb-2 pr-4">Field</th><th className="pb-2 pr-4">Current data</th><th className="pb-2">Proposed value</th></tr></thead>
          <tbody>{rows.map(([field, change]) => <tr key={field} className="border-t border-[#edf1f2]"><th scope="row" className="py-2 pr-4 font-medium text-[#35484e]">{field.replaceAll("_", " ")}</th><td className="py-2 pr-4 text-[#52656b]">{displayValue(change.current)}</td><td className="py-2 text-[#142126]">{proposal.clear_fields?.some((clearField) => clearField === field) ? "Clear stored value" : displayValue(change.proposed)}</td></tr>)}</tbody>
        </table>
      </div>}

      {blockingReasons.length > 0 && <div className="mt-3 rounded-md bg-[#fff7f5] px-3 py-2 text-[13px] text-[#84241f]" role="status">
        <p className="font-medium">This change needs a little more information.</p>
        <ul className="mt-1 list-disc pl-5">{blockingReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      </div>}
      {sourceWarnings.map((warning) => <p key={warning} className="mt-2 text-[12px] text-[#815408]">{warning}</p>)}
      <blockquote className="mt-3 border-l-2 border-[#cbd6d9] pl-3 text-[13px] leading-5 text-[#52656b]">“{proposal.evidence_quote}”</blockquote>
      {proposal.review_status === "rejected" && <div className="mt-4 max-w-[760px] rounded-md border border-[#dfe7e9] bg-[#f7f9f9] p-4">
        <p className="text-[13px] font-medium text-[#26373d]">You rejected this proposal. What should change?</p>
        <p className="mt-1 text-[12px] leading-5 text-[#52656b]">Tell GPT-6 Luna what was wrong, or add a corrected source above. It will prepare a new proposal for review. The active catalog stays unchanged until you mark the corrected proposal to accept and click Review done.</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor={`revision-${proposal.proposal_id}`}>Explain the correction for this catalog proposal</label>
          <textarea id={`revision-${proposal.proposal_id}`} className="min-h-[76px] min-w-0 flex-1 resize-y rounded-md border border-[#cbd6d9] bg-white px-3 py-2 text-[13px] leading-5" value={revision} onChange={(event) => setRevision(event.target.value)} placeholder="For example: the stock is 18, not 8. Keep the current price." />
          <button type="button" className="rfq-secondary self-end" disabled={!revision.trim() || busy} onClick={() => onRevise(proposal.proposal_id, revision.trim())}><Send size={14} aria-hidden="true" />Ask Luna to revise</button>
        </div>
      </div>}
    </article>
  );
}

export function CatalogUpdatesView({ initialItem, onInitialItemHandled }: { initialItem?: CatalogItem | null; onInitialItemHandled?: () => void }) {
  const [proposals, setProposals] = useState<CatalogUpdateProposal[]>([]);
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [decisions, setDecisions] = useState<Record<string, "accept" | "reject">>({});
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const textAreaRef = useRef<HTMLTextAreaElement>(null);

  const refresh = async () => {
    try {
      setProposals(await listCatalogUpdateProposals());
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Distributor changes could not be loaded.");
    }
  };

  useEffect(() => {
    let active = true;
    listCatalogUpdateProposals().then((items) => {
      if (active) setProposals(items);
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : "Distributor changes could not be loaded.");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!initialItem) return;
    const timer = window.setTimeout(() => {
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      const context = `Suggest a catalog update for this existing item. Do not invent facts; only propose changes supported by the instruction below.\n\nCurrent catalog record:\nInternal SKU: ${initialItem.internal_sku}\nManufacturer: ${initialItem.manufacturer}\nPart number: ${initialItem.manufacturer_part_number}\nDescription: ${initialItem.description || "(blank)"}\nList price: ${initialItem.list_price ?? "(blank)"} ${initialItem.currency || ""}\nStock on hand: ${initialItem.stock_qty ?? "(blank)"}\n\nRequested change: `;
      setText(context);
      textAreaRef.current?.focus();
      textAreaRef.current?.setSelectionRange(context.length, context.length);
      onInitialItemHandled?.();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [initialItem, onInitialItemHandled]);

  const stage = async (revisionOf?: string, revisionText?: string) => {
    if (!file && !(revisionText || text).trim()) return;
    const changeMarker = "Requested change:";
    const markerIndex = text.lastIndexOf(changeMarker);
    if (!revisionText && markerIndex >= 0 && !text.slice(markerIndex + changeMarker.length).trim()) {
      setError("Describe the change you want GPT-6 Luna to propose for this item first.");
      return;
    }
    if (!revisionText && file && text.trim()) {
      setError("Review one source at a time. Submit the note or the file separately so each proposal keeps clear source evidence.");
      return;
    }
    setLoading(true);
    setError(null);
    setNotice(null);
    try {
      const created = await stageCatalogUpdate({ text: revisionText || text, file: revisionText ? undefined : file || undefined, revisionOf });
      setProposals((current) => [...created, ...current]);
      setText("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      const actionableCount = created.filter((proposal) => proposal.change_type !== "unchanged").length;
      const unchangedCount = created.length - actionableCount;
      setNotice(actionableCount === 0
        ? `${unchangedCount} ${unchangedCount === 1 ? "source row matches" : "source rows match"} the active catalog. No update is needed.`
        : `${actionableCount} ${actionableCount === 1 ? "proposed change is" : "proposed changes are"} ready for review. Your active catalog has not changed.${unchangedCount ? ` ${unchangedCount} unchanged rows need no action.` : ""}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The source could not be processed.");
    } finally {
      setLoading(false);
    }
  };

  const chooseDecision = (proposalId: string, decision: "accept" | "reject") => {
    setDecisions((current) => { const next = { ...current }; if (next[proposalId] === decision) delete next[proposalId]; else next[proposalId] = decision; return next; });
  };

  const reviewDone = async () => {
    if (!pending.length || pending.some((proposal) => !decisions[proposal.proposal_id])) return;
    setBusyId("batch");
    setError(null);
    try {
      const reviewed = await reviewCatalogUpdates(pending.map((proposal) => ({
        proposal_id: proposal.proposal_id,
        expected_version: proposal.version,
        decision: decisions[proposal.proposal_id],
      })));
      const byId = new Map(reviewed.map((proposal) => [proposal.proposal_id, proposal]));
      setProposals((items) => items.map((item) => byId.get(item.proposal_id) || item));
      setDecisions({});
      const accepted = reviewed.filter((proposal) => proposal.review_status === "accepted").length;
      const rejected = reviewed.length - accepted;
      setNotice(`Review complete. ${accepted} ${accepted === 1 ? "change was" : "changes were"} applied${rejected ? `; ${rejected} ${rejected === 1 ? "was" : "were"} rejected and left out of active data` : ""}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The catalog review could not be committed.");
    } finally {
      setBusyId(null);
    }
  };

  const pending = proposals.filter((proposal) => proposal.review_status === "pending" && proposal.change_type !== "unchanged");
  const unchanged = proposals.filter((proposal) => proposal.change_type === "unchanged");
  const history = proposals.filter((proposal) => proposal.review_status !== "pending");

  return (
    <div className="rfq-content">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><h1 className="rfq-page-title">Update distributor data</h1><p className="rfq-subtitle">Add new catalog facts or share what has changed. Review each proposed update before it reaches the active data.</p></div>
        <button type="button" className="rfq-secondary" onClick={() => void refresh()}><RefreshCw size={14} aria-hidden="true" />Refresh</button>
      </div>

      <section className="mt-6 max-w-[1000px]" aria-labelledby="update-source-heading">
        <h2 id="update-source-heading" className="text-[15px] font-semibold text-[#142126]">Add distributor data</h2>
        <p className="mt-1 text-[13px] text-[#52656b]">Upload a distributor document to process it without writing a prompt, or paste a note if that is what you received. Each source becomes proposals; mark each one, then click Review done to apply accepted records together.</p>
        <label className="sr-only" htmlFor="catalog-update-text">Paste distributor information</label>
        <textarea ref={textAreaRef} id="catalog-update-text" className="mt-4 min-h-[132px] w-full resize-y rounded-md border border-[#cbd6d9] bg-white p-3 text-[14px] leading-6 text-[#1d2b30] placeholder:text-[#667980] focus:border-[#a83e1c] focus:outline-none" value={text} onChange={(event) => setText(event.target.value)} placeholder={'Example: We received 18 more Siemens 6ES7134-6GD01-0XB0 modules. Stock is now 18.'} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input ref={fileInput} type="file" accept=".txt,.eml,.csv,.xls,.xlsx,.pdf" className="sr-only" onChange={(event) => setFile(event.target.files?.[0] || null)} aria-label="Choose distributor source file" />
          <button type="button" className="rfq-secondary" onClick={() => fileInput.current?.click()}><FileUp size={15} aria-hidden="true" />{file ? file.name : "Attach a file"}</button>
          {file && <button type="button" className="text-[13px] text-[#52656b] underline" onClick={() => { setFile(null); if (fileInput.current) fileInput.current.value = ""; }}>Remove file</button>}
          <button type="button" className="rfq-primary ml-auto" disabled={loading || (!file && !text.trim())} onClick={() => void stage()}>{loading ? <><LoaderCircle size={15} className="animate-spin" aria-hidden="true" />Reading source…</> : file ? <><Send size={14} aria-hidden="true" />Review file changes</> : <><Sparkles size={14} aria-hidden="true" />Ask GPT-6 Luna</>}</button>
        </div>
        <p className="mt-2 text-[12px] text-[#667980]">Supported files: text/email, CSV, Excel, and readable PDF. The original source is retained locally. Free-form notes use GPT-6 Luna; structured sheets are read deterministically. Model output is a proposal, not a database change.</p>
      </section>

      {error && <div className="mt-5 max-w-[1000px] rounded-md border border-[#f0c7c1] bg-[#fff7f5] px-4 py-3 text-[13px] text-[#84241f]" role="alert">{error}</div>}
      {notice && <div className="mt-5 max-w-[1000px] rounded-md bg-[#e9f6ee] px-4 py-3 text-[13px] text-[#194f37]" role="status">{notice}</div>}

      <section className="mt-8 max-w-[1000px]" aria-labelledby="pending-heading">
        <div className="flex items-baseline justify-between gap-3 border-b border-[#dfe7e9] pb-2"><h2 id="pending-heading" className="rfq-section-title">Changes to review</h2><span className="rfq-mono text-[12px] text-[#52656b]">{pending.length} pending</span></div>
        {pending.length === 0 ? <p className="py-5 text-[13px] text-[#52656b]">No distributor changes are waiting for a decision.</p> : <>
          <p className="py-3 text-[13px] text-[#52656b]">Mark each proposed record to accept or reject. Nothing changes in active distributor data until you finish this review.</p>
          {pending.map((proposal) => <CatalogChange key={proposal.proposal_id} proposal={proposal} busy={busyId === "batch"} onReview={chooseDecision} selectedDecision={decisions[proposal.proposal_id]} onRevise={(id, revisionText) => void stage(id, revisionText)} />)}
          <div className="sticky bottom-3 z-10 mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[#cbd6d9] bg-white/95 p-4 shadow-lg backdrop-blur">
            <span className="text-[13px] text-[#35484e]">{Object.keys(decisions).length} of {pending.length} decisions marked</span>
            <button type="button" className="rfq-primary" disabled={busyId === "batch" || pending.some((proposal) => !decisions[proposal.proposal_id])} onClick={() => void reviewDone()}>{busyId === "batch" ? <><LoaderCircle size={15} className="animate-spin" aria-hidden="true" />Saving review…</> : "Review done"}</button>
          </div>
        </>}
      </section>

      {unchanged.length > 0 && <details className="mt-6 max-w-[1000px]" aria-label="Rows that already match the catalog">
        <summary className="cursor-pointer border-b border-[#dfe7e9] pb-2 text-[13px] font-medium text-[#52656b]">{unchanged.length} {unchanged.length === 1 ? "row already matches" : "rows already match"} · no decision needed</summary>
        {unchanged.map((proposal) => <CatalogChange key={proposal.proposal_id} proposal={proposal} busy={false} onReview={chooseDecision} selectedDecision={decisions[proposal.proposal_id]} onRevise={(id, revisionText) => void stage(id, revisionText)} />)}
      </details>}

      {history.length > 0 && <section className="mt-8 max-w-[1000px]" aria-labelledby="history-heading"><h2 id="history-heading" className="rfq-section-title border-b border-[#dfe7e9] pb-2">Decision history</h2>{history.map((proposal) => <CatalogChange key={proposal.proposal_id} proposal={proposal} busy={busyId === proposal.proposal_id} onReview={chooseDecision} selectedDecision={decisions[proposal.proposal_id]} onRevise={(id, revisionText) => void stage(id, revisionText)} />)}</section>}
    </div>
  );
}
