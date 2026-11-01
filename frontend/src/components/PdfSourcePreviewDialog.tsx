"use client";

import { useState } from "react";
import { X } from "lucide-react";
import { SourceLocator } from "@/types";
import { useSourceDrawer } from "@/components/useSourceDrawer";

interface PdfSourcePreviewDialogProps {
  caseId: string;
  locator: SourceLocator;
  onClose: () => void;
}

export function PdfSourcePreviewDialog({ caseId, locator, onClose }: PdfSourcePreviewDialogProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const { dialogRef, closeButtonRef } = useSourceDrawer(onClose);
  const pageNumber = locator.page_number ?? 1;
  const [x0, y0, x1, y1] = locator.page_bbox ?? [0, 0, 0, 0];
  const sourceQuery = locator.source_file_id ? `?source_file_id=${encodeURIComponent(locator.source_file_id)}` : "";
  const sourceUrl = `/api/proxy/api/rfqs/${encodeURIComponent(caseId)}/source/pages/${pageNumber}${sourceQuery}`;
  const originalUrl = `/api/proxy/api/rfqs/${encodeURIComponent(caseId)}/source${sourceQuery}#page=${pageNumber}`;

  return (
    <div className="fixed inset-0 z-[80] bg-[#142126]/30" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="pdf-source-title" className="fixed inset-y-0 right-0 flex w-full max-w-[min(560px,92vw)] flex-col overflow-hidden border-l border-[#d9d0c5] bg-[#fffdfa] shadow-2xl animate-in slide-in-from-right duration-200">
        <header className="flex items-start justify-between gap-4 border-b border-[#e9e1d6] px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#8d482e]">Source evidence · PDF</p>
            <h2 id="pdf-source-title" className="mt-1 text-lg font-semibold text-[#1d2b30]">{locator.file_name} · page {pageNumber}</h2>
            <p className="mt-1 text-sm text-[#52656b]">
              {locator.page_bbox
                ? `The highlighted OCR region is ${Math.round((x1 - x0) * 100)}% wide and ${Math.round((y1 - y0) * 100)}% high. Compare OCR-derived text with this page image.`
                : "Review the extracted line against this original page."}
              {locator.ocr_confidence != null && ` OCR confidence: ${Math.round(locator.ocr_confidence)}%.`}
            </p>
          </div>
          <button ref={closeButtonRef} type="button" onClick={onClose} aria-label="Close PDF source preview" className="rounded-md p-2 text-[#52656b] hover:bg-[#f3eee6]">
            <X size={18} />
          </button>
        </header>
        <div className="overflow-auto p-4">
          {imageFailed ? (
            <p role="alert" className="rounded-lg border border-[#e2b5a5] bg-[#fff2ec] p-4 text-sm text-[#7c321b]">This PDF page could not be rendered. Open the original document to inspect it.</p>
          ) : (
            <div className="flex justify-center">
              <div className="relative inline-block max-w-full overflow-hidden border border-[#d9d0c5] bg-white shadow-sm">
                {/* This protected, on-demand image must bypass Next's remote optimizer and its auth boundary. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={sourceUrl} alt={`${locator.file_name}, page ${pageNumber}`} onError={() => setImageFailed(true)} className="block max-h-[calc(100vh-230px)] max-w-full" />
                {locator.page_bbox && (
                  <div
                    aria-label="OCR source region"
                    className="pointer-events-none absolute border-[3px] border-[#a83e1c] bg-[#f8e2d7]/35 shadow-[0_0_0_9999px_rgba(20,33,38,0.06)]"
                    style={{ left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` }}
                  />
                )}
              </div>
            </div>
          )}
          {locator.text_snippet && <blockquote className="mt-4 rounded-lg border-l-2 border-[#a83e1c] bg-[#f8f4ed] px-3 py-2 text-sm text-[#33464c]">{locator.text_snippet}</blockquote>}
          <div className="mt-4 flex justify-end">
            <a href={originalUrl} target="_blank" rel="noreferrer" className="rfq-secondary inline-flex">Open original PDF</a>
          </div>
        </div>
      </section>
    </div>
  );
}
