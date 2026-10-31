"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { getSpreadsheetSourcePreview } from "@/services/api";
import { SpreadsheetSourcePreview } from "@/types";

interface SourcePreviewDialogProps {
  caseId: string;
  sheetName: string;
  rowNumber: number;
  targetCells: string[];
  onClose: () => void;
}

export function SourcePreviewDialog({
  caseId,
  sheetName,
  rowNumber,
  targetCells,
  onClose,
}: SourcePreviewDialogProps) {
  const [preview, setPreview] = useState<SpreadsheetSourcePreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const targetCellKey = targetCells.join(",");

  useEffect(() => {
    let current = true;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    getSpreadsheetSourcePreview(caseId, sheetName, rowNumber, targetCellKey.split(",").filter(Boolean))
      .then((result) => {
        if (current) setPreview(result);
      })
      .catch((reason: unknown) => {
        if (current) setError(reason instanceof Error ? reason.message : "Source preview failed.");
      });
    return () => {
      current = false;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [caseId, sheetName, rowNumber, targetCellKey, onClose]);

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-[#142126]/55 p-3 sm:p-6" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="source-preview-title"
        className="flex max-h-[88vh] w-full max-w-6xl flex-col overflow-hidden rounded-xl border border-[#d9d0c5] bg-[#fffdfa] shadow-2xl"
      >
        <header className="flex items-start justify-between gap-4 border-b border-[#e9e1d6] px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#8d482e]">Original workbook</p>
            <h2 id="source-preview-title" className="mt-1 text-lg font-semibold text-[#1d2b30]">
              {sheetName} · row {rowNumber}
            </h2>
            <p className="mt-1 text-sm text-[#52656b]">
              Highlighted cells are the recorded source for this line. Formula values are shown as stored and are not recalculated.
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close source preview" className="rounded-md p-2 text-[#52656b] hover:bg-[#f3eee6]">
            <X size={18} />
          </button>
        </header>

        {error ? (
          <div role="alert" className="m-5 rounded-lg border border-[#e2b5a5] bg-[#fff2ec] p-4 text-sm text-[#7c321b]">{error}</div>
        ) : !preview ? (
          <div role="status" className="p-6 text-sm text-[#52656b]">Loading source rows…</div>
        ) : (
          <div className="overflow-auto p-4">
            <div className="mb-3 flex flex-wrap gap-2 text-xs text-[#52656b]">
              <span className="rounded-full bg-[#f3eee6] px-2.5 py-1">Selected row: {preview.target_row}</span>
              {(preview.target_cells ?? []).map((cell) => (
                <span key={cell} className="rounded-full bg-[#f8e2d7] px-2.5 py-1 font-mono text-[#77391e]">Source cell: {cell}</span>
              ))}
            </div>
            <table className="min-w-full border-collapse text-left text-sm">
              <tbody>
                {(preview.rows ?? []).map((row) => (
                  <tr key={row.row_number} className={row.is_target ? "bg-[#fff2ec]" : "bg-white"}>
                    <th scope="row" className="sticky left-0 border border-[#e7e0d5] bg-[#f3eee6] px-3 py-2 text-xs font-semibold text-[#52656b]">
                      {row.row_number}{row.is_target ? " · line source" : ""}
                    </th>
                    {(row.cells ?? []).map((cell) => (
                      <td
                        key={cell.coordinate}
                        aria-label={`${cell.coordinate}${cell.is_formula ? ", formula" : ""}${cell.selected ? ", selected source cell" : ""}`}
                        className={`min-w-24 max-w-72 whitespace-pre-wrap break-words border px-3 py-2 align-top ${cell.selected ? "border-[#a83e1c] bg-[#f8e2d7] font-semibold text-[#552719] ring-1 ring-inset ring-[#a83e1c]" : "border-[#e7e0d5] text-[#33464c]"}`}
                      >
                        <span className="mb-1 block font-mono text-[10px] font-medium text-[#8a9698]">{cell.coordinate}</span>
                        {cell.value || <span className="text-[#aab2b2]">—</span>}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
