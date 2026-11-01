"use client";

import { useEffect, useRef, useState } from "react";
import { Check, FileUp, LoaderCircle, RefreshCw, Send, X, Sparkles } from "lucide-react";
import {
  acceptCatalogUpdate,
  listCatalogUpdateProposals,
  rejectCatalogUpdate,
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
  if (proposal.change_type === "unchanged") return "Already in catalog";
  return "Needs clarification";
}

function CatalogChange({
  proposal,
  onReview,
  onRevise,
  busy,
}: {
  proposal: CatalogUpdateProposal;
  onReview: (proposalId: string, decision: "accept" | "reject") => void;
  onRevise: (proposalId: string, text: string) => void;
  busy: boolean;
}) {
  const [revision, setRevision] = useState("");
  const changedFields = proposal.changed_fields ?? {};
  const proposedValues = proposal.proposed_values ?? {};
  const blockingReasons = proposal.blocking_reasons ?? [];
  const sourceWarnings = proposal.source_warnings ?? [];
  const rows = Object.entries(changedFields).length
    ? Object.entries(changedFields)
    : Object.entries(proposedValues).map(([field, proposed]) => [field, { current: null, proposed }] as const);
  const canAccept = proposal.review_status === "pending" && blockingReasons.length === 0;

  return (
    <article className="border-b border-[#e8edef] py-5 last:border-0" aria-labelledby={`proposal-${proposal.proposal_id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <h3 id={`proposal-${proposal.proposal_id}`} className="text-[15px] font-semibold text-[#142126]">
              {displayValue(proposedValues.internal_sku || proposal.current_item?.internal_sku || proposedValues.manufacturer_part_number || proposal.current_item?.manufacturer_part_number)}
            </h3>
            <span className="text-[12px] text-[#52656b]">{proposalLabel(proposal)}</span>
            <span className="text-[12px] text-[#667980]">· {proposal.review_status}</span>
          </div>
          <p className="mt-1 text-[12px] text-[#52656b]">{proposal.source_name} · {proposal.source_locator.sheet_name ? `${proposal.source_locator.sheet_name}, ` : ""}{proposal.source_locator.row_number ? `row ${proposal.source_locator.row_number}` : proposal.source_locator.page_number ? `page ${proposal.source_locator.page_number}` : "source text"} · <a className="font-medium underline underline-offset-2" href={`/api/proxy/api/catalogs/updates/${encodeURIComponent(proposal.proposal_id)}/source`} target="_blank" rel="noreferrer">Open original source</a></p>
        </div>
        {proposal.review_status === "pending" && (
          <div className="flex shrink-0 items-center gap-2">
            <button type="button" className="rfq-secondary" disabled={busy} onClick={() => onReview(proposal.proposal_id, "reject")} aria-label={`Reject proposal ${proposal.proposal_id}`}><X size={15} aria-hidden="true" />Reject</button>
            <button type="button" className="rfq-primary" disabled={!canAccept || busy} onClick={() => onReview(proposal.proposal_id, "accept")} aria-label={`Accept proposal ${proposal.proposal_id}`}><Check size={15} aria-hidden="true" />Accept change</button>
          </div>
        )}
      </div>

      {rows.length > 0 && <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[430px] border-collapse text-left text-[13px]">
          <thead><tr className="text-[12px] font-medium text-[#52656b]"><th className="pb-2 pr-4">Field</th><th className="pb-2 pr-4">Current data</th><th className="pb-2">From this source</th></tr></thead>
          <tbody>{rows.map(([field, change]) => <tr key={field} className="border-t border-[#edf1f2]"><th scope="row" className="py-2 pr-4 font-medium text-[#35484e]">{field.replaceAll("_", " ")}</th><td className="py-2 pr-4 text-[#52656b]">{displayValue(change.current)}</td><td className="py-2 text-[#142126]">{displayValue(change.proposed)}</td></tr>)}</tbody>
        </table>
      </div>}

      {blockingReasons.length > 0 && <div className="mt-3 rounded-md bg-[#fff7f5] px-3 py-2 text-[13px] text-[#84241f]" role="status">
        <p className="font-medium">This change needs a little more information.</p>
        <ul className="mt-1 list-disc pl-5">{blockingReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      </div>}
      {sourceWarnings.map((warning) => <p key={warning} className="mt-2 text-[12px] text-[#815408]">{warning}</p>)}
      <blockquote className="mt-3 border-l-2 border-[#cbd6d9] pl-3 text-[13px] leading-5 text-[#52656b]">“{proposal.evidence_quote}”</blockquote>
      {proposal.review_status === "rejected" && <div className="mt-4 rounded-md bg-[#f3f7f8] p-3">
        <p className="text-[13px] font-medium text-[#26373d]">Want to revise this information?</p>
        <p className="mt-1 text-[12px] text-[#52656b]">Describe the correction in ordinary words. The existing catalog entry stays as it is until you accept a new proposal.</p>
        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <label className="sr-only" htmlFor={`revision-${proposal.proposal_id}`}>Describe a correction</label>
          <input id={`revision-${proposal.proposal_id}`} className="h-9 min-w-0 flex-1 rounded-md border border-[#cbd6d9] bg-white px-3 text-[13px]" value={revision} onChange={(event) => setRevision(event.target.value)} placeholder="For example: the stock figure should be 18, not 8" />
          <button type="button" className="rfq-secondary" disabled={!revision.trim() || busy} onClick={() => onRevise(proposal.proposal_id, revision.trim())}><RefreshCw size={14} aria-hidden="true" />Create revised proposal</button>
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
      setNotice(`${created.length} ${created.length === 1 ? "proposal is" : "proposals are"} ready for review. Your active catalog has not changed.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The source could not be processed.");
    } finally {
      setLoading(false);
    }
  };

  const review = async (proposalId: string, decision: "accept" | "reject") => {
    setBusyId(proposalId);
    setError(null);
    try {
      const changed = decision === "accept" ? await acceptCatalogUpdate(proposalId) : await rejectCatalogUpdate(proposalId);
      setProposals((items) => items.map((item) => item.proposal_id === proposalId ? changed : item));
      setNotice(decision === "accept" ? "Change accepted. The active catalog was updated and this change was recorded." : "Change rejected. The active catalog was left unchanged.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The proposal could not be reviewed.");
    } finally {
      setBusyId(null);
    }
  };

  const pending = proposals.filter((proposal) => proposal.review_status === "pending");
  const history = proposals.filter((proposal) => proposal.review_status !== "pending");

  return (
    <div className="rfq-content">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div><h1 className="rfq-page-title">Update distributor data</h1><p className="rfq-subtitle">Add new catalog facts or share what has changed. Review each proposed update before it reaches the active data.</p></div>
        <button type="button" className="rfq-secondary" onClick={() => void refresh()}><RefreshCw size={14} aria-hidden="true" />Refresh</button>
      </div>

      <section className="mt-6 max-w-[1000px]" aria-labelledby="update-source-heading">
        <h2 id="update-source-heading" className="text-[15px] font-semibold text-[#142126]">What would you like to add or change?</h2>
        <p className="mt-1 text-[13px] text-[#52656b]">Paste a distributor note to ask the configured GPT-6 Luna model for a reviewable proposal, or upload a structured catalog file for deterministic extraction. Each source is reviewed separately.</p>
        <label className="sr-only" htmlFor="catalog-update-text">Paste distributor information</label>
        <textarea ref={textAreaRef} id="catalog-update-text" className="mt-4 min-h-[132px] w-full resize-y rounded-md border border-[#cbd6d9] bg-white p-3 text-[14px] leading-6 text-[#1d2b30] placeholder:text-[#667980] focus:border-[#a83e1c] focus:outline-none" value={text} onChange={(event) => setText(event.target.value)} placeholder={'Example: We received 18 more Siemens 6ES7134-6GD01-0XB0 modules. Stock is now 18.'} />
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input ref={fileInput} type="file" accept=".txt,.eml,.csv,.xls,.xlsx,.pdf" className="sr-only" onChange={(event) => setFile(event.target.files?.[0] || null)} aria-label="Choose distributor source file" />
          <button type="button" className="rfq-secondary" onClick={() => fileInput.current?.click()}><FileUp size={15} aria-hidden="true" />{file ? file.name : "Attach a file"}</button>
          {file && <button type="button" className="text-[13px] text-[#52656b] underline" onClick={() => { setFile(null); if (fileInput.current) fileInput.current.value = ""; }}>Remove file</button>}
          <button type="button" className="rfq-primary ml-auto" disabled={loading || (!file && !text.trim())} onClick={() => void stage()}>{loading ? <><LoaderCircle size={15} className="animate-spin" aria-hidden="true" />Reading source…</> : file ? <><Send size={14} aria-hidden="true" />Review file changes</> : <><Sparkles size={14} aria-hidden="true" />Ask GPT-6 Luna</>}</button>
        </div>
        <p className="mt-2 text-[12px] text-[#667980]">Supported files: text/email, CSV, Excel, and readable PDF. The original source is retained locally. If GPT-6 Luna is not configured, note proposals cannot be processed. AI output is only a proposal; accepting it is a separate action that updates the catalog.</p>
      </section>

      {error && <div className="mt-5 max-w-[1000px] rounded-md border border-[#f0c7c1] bg-[#fff7f5] px-4 py-3 text-[13px] text-[#84241f]" role="alert">{error}</div>}
      {notice && <div className="mt-5 max-w-[1000px] rounded-md bg-[#e9f6ee] px-4 py-3 text-[13px] text-[#194f37]" role="status">{notice}</div>}

      <section className="mt-8 max-w-[1000px]" aria-labelledby="pending-heading">
        <div className="flex items-baseline justify-between gap-3 border-b border-[#dfe7e9] pb-2"><h2 id="pending-heading" className="rfq-section-title">Changes to review</h2><span className="rfq-mono text-[12px] text-[#52656b]">{pending.length} pending</span></div>
        {pending.length === 0 ? <p className="py-5 text-[13px] text-[#52656b]">No distributor changes are waiting for a decision.</p> : pending.map((proposal) => <CatalogChange key={proposal.proposal_id} proposal={proposal} busy={busyId === proposal.proposal_id} onReview={review} onRevise={(id, revisionText) => void stage(id, revisionText)} />)}
      </section>

      {history.length > 0 && <section className="mt-8 max-w-[1000px]" aria-labelledby="history-heading"><h2 id="history-heading" className="rfq-section-title border-b border-[#dfe7e9] pb-2">Decision history</h2>{history.map((proposal) => <CatalogChange key={proposal.proposal_id} proposal={proposal} busy={busyId === proposal.proposal_id} onReview={review} onRevise={(id, revisionText) => void stage(id, revisionText)} />)}</section>}
    </div>
  );
}
