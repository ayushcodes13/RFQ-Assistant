"use client";

import { useEffect, useState } from "react";
import { X } from "lucide-react";
import { SourceLocator } from "@/types";

interface PdfSourcePreviewDialogProps {
  caseId: string;
  locator: SourceLocator;
  onClose: () => void;
}

export function PdfSourcePreviewDialog({ caseId, locator, onClose }: PdfSourcePreviewDialogProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const pageNumber = locator.page_number ?? 1;
  const [x0, y0, x1, y1] = locator.page_bbox ?? [0, 0, 0, 0];
  const sourceUrl = `/api/proxy/api/rfqs/${encodeURIComponent(caseId)}/source/pages/${pageNumber}`;
  const originalUrl = `/api/proxy/api/rfqs/${encodeURIComponent(caseId)}/source#page=${pageNumber}`;

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-[80] flex items-center justify-center bg-[#142126]/55 p-3 sm:p-6" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose();
    }}>
      <section role="dialog" aria-modal="true" aria-labelledby="pdf-source-title" className="flex max-h-[88vh] w-full max-w-5xl flex-col overflow-hidden rounded-xl border border-[#d9d0c5] bg-[#fffdfa] shadow-2xl">
        <header className="flex items-start justify-between gap-4 border-b border-[#e9e1d6] px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#8d482e]">Original PDF</p>
            <h2 id="pdf-source-title" className="mt-1 text-lg font-semibold text-[#1d2b30]">Page {pageNumber}</h2>
            <p className="mt-1 text-sm text-[#52656b]">
              {locator.page_bbox
                ? `The highlighted OCR region is ${Math.round((x1 - x0) * 100)}% wide and ${Math.round((y1 - y0) * 100)}% high. Compare OCR-derived text with this page image.`
                : "Review the extracted line against this original page."}
              {locator.ocr_confidence != null && ` OCR confidence: ${Math.round(locator.ocr_confidence)}%.`}
            </p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close PDF source preview" className="rounded-md p-2 text-[#52656b] hover:bg-[#f3eee6]">
            <X size={18} />
          </button>
        </header>
        <div className="overflow-auto p-4 sm:p-6">
          {imageFailed ? (
            <p role="alert" className="rounded-lg border border-[#e2b5a5] bg-[#fff2ec] p-4 text-sm text-[#7c321b]">This PDF page could not be rendered. Open the original document to inspect it.</p>
          ) : (
            <div className="flex justify-center">
              <div className="relative inline-block max-w-full overflow-hidden border border-[#d9d0c5] bg-white shadow-sm">
                {/* This protected, on-demand image must bypass Next's remote optimizer and its auth boundary. */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={sourceUrl} alt={`${locator.file_name}, page ${pageNumber}`} onError={() => setImageFailed(true)} className="block max-h-[68vh] max-w-full" />
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
          <div className="mt-4 flex justify-end">
            <a href={originalUrl} target="_blank" rel="noreferrer" className="rfq-secondary inline-flex">Open original PDF</a>
          </div>
        </div>
      </section>
    </div>
  );
}
