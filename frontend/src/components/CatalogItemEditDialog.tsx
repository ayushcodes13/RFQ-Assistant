"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { X } from "lucide-react";
import { CatalogItem } from "@/types";
import { stageCatalogUpdate } from "@/services/api";

interface CatalogItemEditDialogProps {
  item: CatalogItem;
  onClose: () => void;
  onProposalCreated: () => void;
  onAskAI: (item: CatalogItem) => void;
}

function csvCell(value: string | number | null): string {
  const text = value == null ? "" : String(value);
  return `"${text.replaceAll('"', '""')}"`;
}

function normalizedPrice(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed < 0) throw new Error("List price must be a non-negative number or blank.");
  return parsed;
}

function normalizedStock(value: string): number | null {
  if (!value.trim()) return null;
  const parsed = Number(value);
  if (!Number.isInteger(parsed) || parsed < 0) throw new Error("Stock must be a non-negative whole number or blank.");
  return parsed;
}

export function CatalogItemEditDialog({ item, onClose, onProposalCreated, onAskAI }: CatalogItemEditDialogProps) {
  const [manufacturer, setManufacturer] = useState(item.manufacturer);
  const [mpn, setMpn] = useState(item.manufacturer_part_number);
  const [description, setDescription] = useState(item.description ?? "");
  const [price, setPrice] = useState(item.list_price == null ? "" : String(item.list_price));
  const [currency, setCurrency] = useState(item.currency ?? "");
  const [stock, setStock] = useState(item.stock_qty == null ? "" : String(item.stock_qty));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [busy, onClose]);

  const createProposal = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const cleanManufacturer = manufacturer.trim();
      const cleanMpn = mpn.trim();
      if (!cleanManufacturer || !cleanMpn) throw new Error("Manufacturer and part number are required.");
      const listPrice = normalizedPrice(price);
      const stockQty = normalizedStock(stock);
      const cleanCurrency = currency.trim().toUpperCase();
      if (item.list_price != null && listPrice == null) throw new Error("Removing an existing price is not supported yet. Enter the corrected price instead.");
      if (item.stock_qty != null && stockQty == null) throw new Error("Removing an existing stock value is not supported yet. Enter the corrected quantity instead.");
      if (item.description && !description.trim()) throw new Error("Removing an existing description is not supported yet. Enter the corrected description instead.");
      if (item.currency && !cleanCurrency) throw new Error("Removing an existing currency is not supported yet. Enter the corrected currency instead.");
      if (listPrice !== null && listPrice !== (item.list_price ?? null) && !/^[A-Z]{3}$/.test(cleanCurrency)) {
        throw new Error("Enter a three-letter currency code when a list price is set.");
      }
      if (
        cleanManufacturer === item.manufacturer && cleanMpn === item.manufacturer_part_number &&
        description.trim() === (item.description ?? "") && listPrice === (item.list_price ?? null) &&
        (cleanCurrency || null) === (item.currency ?? null) && stockQty === (item.stock_qty ?? null)
      ) throw new Error("No changes to propose. Update at least one field first.");

      const headers = ["internal_sku", "manufacturer", "manufacturer_part_number", "description", "list_price", "currency", "stock_qty"];
      const values = [item.internal_sku, cleanManufacturer, cleanMpn, description.trim(), listPrice, cleanCurrency || null, stockQty];
      const csv = `${headers.join(",")}\r\n${values.map(csvCell).join(",")}\r\n`;
      const safeSku = item.internal_sku.replace(/[^a-zA-Z0-9_-]/g, "_");
      const file = new File([csv], `manual-catalog-edit-${safeSku}.csv`, { type: "text/csv" });
      const proposals = await stageCatalogUpdate({ file });
      if (proposals.length !== 1) throw new Error("The edit did not create exactly one reviewable catalog proposal.");
      const blockingReasons = proposals[0].blocking_reasons ?? [];
      if (blockingReasons.length > 0) {
        throw new Error(blockingReasons.join(" "));
      }
      onProposalCreated();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "The catalog change could not be staged.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-[#142126]/35 p-4" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onClose(); }}>
      <section role="dialog" aria-modal="true" aria-labelledby="catalog-edit-title" className="max-h-[min(90vh,820px)] w-full max-w-2xl overflow-auto rounded-lg border border-[#d9e2e4] bg-[#fffdfa] shadow-2xl">
        <header className="flex items-start justify-between gap-4 border-b border-[#e5ebec] px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#8d482e]">Catalog item</p>
            <h2 id="catalog-edit-title" className="mt-1 text-lg font-semibold text-[#142126]">Edit item</h2>
            <p className="mt-1 font-mono text-xs text-[#52656b]">{item.internal_sku}</p>
          </div>
          <button ref={closeRef} type="button" aria-label="Close edit catalog item" className="rounded-md p-2 text-[#52656b] hover:bg-[#f3eee6]" onClick={onClose} disabled={busy}><X size={18} /></button>
        </header>

        <form onSubmit={createProposal} className="space-y-4 px-5 py-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-[13px] font-medium text-[#35484e]">Manufacturer
              <input className="mt-1 h-10 w-full rounded-md border border-[#cbd6d9] bg-white px-3 font-normal" value={manufacturer} onChange={(event) => setManufacturer(event.target.value)} required />
            </label>
            <label className="block text-[13px] font-medium text-[#35484e]">Part number
              <input className="mt-1 h-10 w-full rounded-md border border-[#cbd6d9] bg-white px-3 font-mono font-normal" value={mpn} onChange={(event) => setMpn(event.target.value)} required />
            </label>
            <label className="block text-[13px] font-medium text-[#35484e] sm:col-span-2">Description
              <textarea className="mt-1 min-h-20 w-full rounded-md border border-[#cbd6d9] bg-white px-3 py-2 font-normal" value={description} onChange={(event) => setDescription(event.target.value)} />
            </label>
            <label className="block text-[13px] font-medium text-[#35484e]">List price
              <input className="mt-1 h-10 w-full rounded-md border border-[#cbd6d9] bg-white px-3 font-normal" inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} />
            </label>
            <label className="block text-[13px] font-medium text-[#35484e]">Currency
              <input className="mt-1 h-10 w-full rounded-md border border-[#cbd6d9] bg-white px-3 uppercase font-normal" maxLength={3} value={currency} onChange={(event) => setCurrency(event.target.value)} />
            </label>
            <label className="block text-[13px] font-medium text-[#35484e]">Stock on hand
              <input className="mt-1 h-10 w-full rounded-md border border-[#cbd6d9] bg-white px-3 font-normal" inputMode="numeric" value={stock} onChange={(event) => setStock(event.target.value)} />
            </label>
          </div>

          <p className="rounded-md bg-[#f3f7f8] px-3 py-2 text-[12px] leading-5 text-[#52656b]">Your entry creates a source-backed change proposal. The active catalog stays as it is until you accept that proposal in Update data. Existing description, price, and stock values cannot be cleared here yet.</p>
          {error && <p role="alert" className="rounded-md border border-[#f0c7c1] bg-[#fff7f5] px-3 py-2 text-[13px] text-[#84241f]">{error}</p>}

          <div className="flex flex-col-reverse justify-between gap-2 border-t border-[#e5ebec] pt-4 sm:flex-row sm:items-center">
            <button type="button" className="rfq-secondary" onClick={() => onAskAI(item)} disabled={busy}>Ask AI to propose an edit</button>
            <div className="flex justify-end gap-2">
              <button type="button" className="rfq-secondary" onClick={onClose} disabled={busy}>Cancel</button>
              <button type="submit" className="rfq-primary" disabled={busy}>{busy ? "Preparing proposal…" : "Create change proposal"}</button>
            </div>
          </div>
        </form>
      </section>
    </div>
  );
}
