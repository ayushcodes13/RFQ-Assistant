"use client";

import { useEffect, useMemo, useState } from "react";
import { Database, Pencil, RefreshCw, Search, Sparkles } from "lucide-react";
import { CatalogItem } from "@/types";
import { listCatalog } from "@/services/api";
import { CatalogItemEditDialog } from "@/components/CatalogItemEditDialog";

function formatPrice(item: CatalogItem): string {
  if (item.list_price === null || item.list_price === undefined) return "—";
  if (!item.currency) return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(item.list_price);
  try {
    return new Intl.NumberFormat(undefined, { style: "currency", currency: item.currency, maximumFractionDigits: 2 }).format(item.list_price);
  } catch {
    return `${item.currency} ${item.list_price}`;
  }
}

export function CatalogView({ onOpenUpdates, onAskAI }: { onOpenUpdates?: () => void; onAskAI?: (item: CatalogItem) => void }) {
  const [items, setItems] = useState<CatalogItem[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editingItem, setEditingItem] = useState<CatalogItem | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listCatalog());
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Catalog could not be loaded.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let active = true;
    listCatalog().then((data) => {
      if (active) setItems(data);
    }).catch((cause: unknown) => {
      if (active) setError(cause instanceof Error ? cause.message : "Catalog could not be loaded.");
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => { active = false; };
  }, []);

  const visibleItems = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return items;
    return items.filter((item) => [item.internal_sku, item.manufacturer, item.manufacturer_part_number, item.description]
      .some((value) => value?.toLocaleLowerCase().includes(normalized)));
  }, [items, query]);

  return (
    <div className="rfq-content">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="rfq-page-title">Catalog</h1>
          <p className="rfq-subtitle">Search the distributor-approved item data used for exact part matching.</p>
        </div>
        <div className="flex items-center gap-2">
          <button type="button" className="rfq-secondary" onClick={() => void load()} disabled={loading}><RefreshCw size={14} aria-hidden="true" />Refresh</button>
          {onOpenUpdates && <button type="button" className="rfq-primary" onClick={onOpenUpdates}>Update data</button>}
        </div>
      </div>

      {notice && <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#cddfd4] bg-[#f0f7f2] px-4 py-3 text-[13px] text-[#23553a]" role="status">
        <span>{notice}</span>
        {onOpenUpdates && <button type="button" className="font-medium underline underline-offset-2" onClick={onOpenUpdates}>Review proposal</button>}
      </div>}

      {error && <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-md border border-[#f0c7c1] bg-[#fff7f5] px-4 py-3 text-[13px] text-[#84241f]" role="alert"><span>{error}</span><button type="button" className="font-medium underline underline-offset-2" onClick={() => void load()}>Try again</button></div>}

      <section className="mt-6" aria-label="Distributor catalog">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#dfe7e9] pb-3">
          <label className="relative block w-full sm:max-w-[360px]">
            <span className="sr-only">Search the catalog</span>
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#667980]" aria-hidden="true" />
            <input className="h-9 w-full rounded-md border border-[#cbd6d9] bg-white pl-9 pr-3 text-[13px] text-[#1d2b30] placeholder:text-[#667980] focus:border-[#a83e1c] focus:outline-none" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search SKU, manufacturer, or part number" />
          </label>
          <p className="text-[12px] text-[#52656b]" aria-live="polite">{loading ? "Loading catalog…" : `${visibleItems.length} ${visibleItems.length === 1 ? "item" : "items"}${query && visibleItems.length !== items.length ? ` of ${items.length}` : ""}`}</p>
        </div>

        {!loading && !error && visibleItems.length === 0 ? (
          <div className="flex min-h-[190px] flex-col items-center justify-center border-b border-[#dfe7e9] px-4 py-8 text-center">
            <Database size={22} className="text-[#667980]" aria-hidden="true" />
            <p className="mt-3 text-[14px] font-medium text-[#1d2b30]">{items.length ? "No catalog items match" : "No distributor items yet"}</p>
            <p className="mt-1 max-w-[420px] text-[13px] text-[#52656b]">{items.length ? "Try a different part number or manufacturer." : "Add a source in Update data. Proposed changes stay separate until you accept them."}</p>
            {!items.length && onOpenUpdates && <button type="button" className="rfq-secondary mt-4" onClick={onOpenUpdates}>Open Update data</button>}
          </div>
        ) : (
          <>
          <div className="mt-3 grid gap-3 sm:hidden" aria-label="Catalog items">
            {loading ? [0, 1, 2].map((row) => <div key={row} className="h-28 animate-pulse rounded-md border border-[#dfe7e9] bg-[#f7f9f9]" />) : visibleItems.map((item) => <article key={item.internal_sku} className="rounded-md border border-[#dfe7e9] bg-white p-3">
              <div className="flex items-start justify-between gap-3"><div className="min-w-0"><p className="rfq-mono text-[11px] text-[#667980]">{item.internal_sku}</p><h2 className="mt-1 break-words font-mono text-[14px] font-semibold text-[#1d2b30]">{item.manufacturer_part_number}</h2><p className="mt-1 text-[12px] text-[#52656b]">{item.manufacturer}</p></div><span className="shrink-0 text-right text-[12px] tabular-nums text-[#52656b]">Stock<br /><strong className="text-[14px] text-[#26373d]">{item.stock_qty ?? "—"}</strong></span></div>
              <p className="mt-2 text-[13px] leading-5 text-[#52656b]">{item.description || "No description"}</p>
              <div className="mt-3 flex items-center justify-between gap-2 border-t border-[#edf1f2] pt-3"><span className="text-[12px] text-[#52656b]">List price <strong className="ml-1 text-[#26373d]">{formatPrice(item)}</strong></span><div className="flex gap-2"><button type="button" className="rfq-secondary !px-2 !py-1.5" onClick={() => {setNotice(null); setEditingItem(item);}} aria-label={`Edit ${item.internal_sku}`}><Pencil size={14} aria-hidden="true" /><span>Edit</span></button>{onAskAI && <button type="button" className="rfq-secondary !px-2 !py-1.5" onClick={() => onAskAI(item)} aria-label={`Ask AI to update ${item.internal_sku}`}><Sparkles size={14} aria-hidden="true" /><span>Ask AI</span></button>}</div></div>
            </article>)}
          </div>
          <div className="mt-1 hidden overflow-x-auto sm:block">
            <table className="w-full min-w-[920px] border-collapse text-left text-[13px]">
              <thead><tr className="border-b border-[#dfe7e9] text-[12px] font-medium text-[#52656b]"><th scope="col" className="py-3 pr-4">Internal SKU</th><th scope="col" className="py-3 pr-4">Manufacturer</th><th scope="col" className="py-3 pr-4">Part number</th><th scope="col" className="py-3 pr-4">Description</th><th scope="col" className="py-3 pr-4 text-right">List price</th><th scope="col" className="py-3 pr-4 text-right">Stock</th><th scope="col" className="py-3 text-right">Actions</th></tr></thead>
              <tbody>
                {loading ? [0, 1, 2, 3].map((row) => <tr key={row} className="border-b border-[#edf1f2]"><td colSpan={7} className="py-4"><span className="block h-4 max-w-[500px] animate-pulse rounded bg-[#f1f5f6]" /></td></tr>) : visibleItems.map((item) => <tr key={item.internal_sku} className="border-b border-[#edf1f2] hover:bg-[#fafcfc]"><th scope="row" className="py-3 pr-4 font-medium text-[#26373d]">{item.internal_sku}</th><td className="py-3 pr-4 text-[#35484e]">{item.manufacturer}</td><td className="rfq-mono py-3 pr-4 text-[12px] text-[#26373d]">{item.manufacturer_part_number}</td><td className="max-w-[360px] py-3 pr-4 text-[#52656b]">{item.description || "—"}</td><td className="py-3 pr-4 text-right tabular-nums text-[#26373d]">{formatPrice(item)}</td><td className="py-3 pr-4 text-right tabular-nums text-[#26373d]">{item.stock_qty ?? "—"}</td><td className="py-3 text-right"><div className="flex justify-end gap-1"><button type="button" className="rfq-secondary !px-2 !py-1" onClick={() => {setNotice(null); setEditingItem(item);}} aria-label={`Edit ${item.internal_sku}`}><Pencil size={14} aria-hidden="true" /><span>Edit</span></button>{onAskAI && <button type="button" className="rfq-secondary !px-2 !py-1" onClick={() => onAskAI(item)} aria-label={`Ask AI to update ${item.internal_sku}`}><Sparkles size={14} aria-hidden="true" /><span>Ask AI</span></button>}</div></td></tr>)}
              </tbody>
            </table>
          </div>
          </>
        )}
      </section>
      {editingItem && <CatalogItemEditDialog item={editingItem} onClose={() => setEditingItem(null)} onAskAI={(item) => {setEditingItem(null); onAskAI?.(item);}} onProposalCreated={() => {setEditingItem(null); setNotice("Change proposal created. The active catalog will stay unchanged until you accept it in Update data.");}} />}
    </div>
  );
}
