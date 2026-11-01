"use client";

import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Download,
  AlertTriangle,
  CheckCircle,
  FileDown,
} from "lucide-react";
import { exportWorksheet, getCase, resolveDownloadUrl } from "@/services/api";
import { ExportManifest, RFQCase } from "@/types";

interface ExportModalProps {
  isOpen: boolean;
  caseData: RFQCase;
  onClose: () => void;
}

export function ExportModal({
  isOpen,
  caseData,
  onClose,
}: ExportModalProps) {
  const [exporting, setExporting] = useState(false);
  const [allowPartial, setAllowPartial] = useState(false);
  const [manifest, setManifest] = useState<ExportManifest | null>(null);
  const [downloadUrl, setDownloadUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [freshCase, setFreshCase] = useState<RFQCase | null>(null);
  const [checkingStatus, setCheckingStatus] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  // Always fetch the authoritative case. Parent case props can be older
  // than edits from another tab, another reviewer, or the current workbench.
  useEffect(() => {
    if (!isOpen) return;
    let active = true;
    // This modal is keyed per open by the workspace parent. Initial state is
    // therefore fresh; async fetch completion performs the only state update.
    void getCase(caseData.case_id)
      .then((value) => { if (active) setFreshCase(value); })
      .catch(() => {
        if (active) setStatusError("Unable to check the latest case status. Close and reopen the export dialog.");
      })
      .finally(() => { if (active) setCheckingStatus(false); });
    return () => { active = false; };
  }, [isOpen, caseData.case_id]);

  useEffect(() => {
    if (!isOpen) return;
    const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const dialog = dialogRef.current;
    closeButtonRef.current?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !dialog) return;
      const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )).filter((element) => element.getAttribute("aria-hidden") !== "true");
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && (document.activeElement === first || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !dialog.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      if (previouslyFocused?.isConnected) previouslyFocused.focus();
    };
  }, [isOpen]);

  const handleExport = async () => {
    setExporting(true);
    setError(null);
    setDownloadUrl(null);
    setManifest(null);
    try {
      if (!freshCase || checkingStatus || statusError) {
        throw new Error("Current RFQ review status has not been verified. Reopen the dialog.");
      }
      // Recheck at click time too. The backend is always the final export gate.
      const verified = await getCase(caseData.case_id);
      setFreshCase(verified);
      if (verified.status === "PROCESSING" || verified.status === "FAILED") {
        throw new Error("RFQ processing has not completed successfully.");
      }
      // Keep the backend's specific, source-based blocker message as the
      // operator's actionable error (e.g. missing UOM or catalog collision).
      // The refreshed summary warns early, but does not replace this detail.
      const res = await exportWorksheet(caseData.case_id, allowPartial);
      setManifest(res);
      setDownloadUrl(resolveDownloadUrl(res.download_url));
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Export failed";
      setError(msg);
    } finally {
      setExporting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-[200] flex items-center justify-center p-4"
          style={{ backgroundColor: "rgba(42, 35, 24, 0.4)" }}
          onClick={onClose}
        >
          <motion.div
            ref={dialogRef}
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{
              duration: 0.35,
              ease: [0.16, 1, 0.3, 1],
            }}
            className="w-full max-w-md rounded-2xl overflow-hidden shadow-xl"
            style={{
              backgroundColor: "var(--color-cream-50)",
              border: "1px solid var(--color-sand-200)",
            }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="export-dialog-title"
            tabIndex={-1}
          >
            {/* Header */}
            <div
              className="flex items-center justify-between px-5 py-4 border-b"
              style={{ borderColor: "var(--color-sand-200)" }}
            >
              <h2
                id="export-dialog-title"
                className="text-lg font-bold flex items-center gap-2"
                style={{ color: "var(--color-brown-800)" }}
              >
                <FileDown size={20} />
                Export Draft
              </h2>
              <button
                ref={closeButtonRef}
                onClick={onClose}
                className="p-1.5 rounded-lg transition-colors duration-200"
                style={{ color: "var(--color-brown-300)" }}
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="px-5 py-5">
              {/* Draft warning */}
              <div
                className="flex items-start gap-3 p-4 rounded-xl border mb-4"
                style={{
                  backgroundColor: "var(--color-warning-50)",
                  borderColor: "var(--color-warning-100)",
                }}
              >
                <AlertTriangle
                  size={18}
                  className="flex-shrink-0 mt-0.5"
                  style={{ color: "var(--color-warning-600)" }}
                />
                <p
                  className="text-sm leading-relaxed"
                  style={{ color: "var(--color-warning-700)" }}
                >
                  This export is a{" "}
                  <strong className="font-semibold">DRAFT</strong>. It
                  requires independent review and approval before use as
                  a customer quotation.
                </p>
              </div>

              {/* Case info */}
              <div
                className="rounded-xl p-4 mb-4"
                style={{
                  backgroundColor: "var(--color-sand-50)",
                }}
              >
                <div className="grid grid-cols-2 gap-2 text-sm">
                  <div>
                    <span
                      className="text-xs font-semibold uppercase tracking-wider"
                      style={{ color: "var(--color-brown-400)" }}
                    >
                      Case
                    </span>
                    <p
                      className="font-medium truncate"
                      style={{ color: "var(--color-brown-700)" }}
                    >
                      {caseData.title || caseData.case_id.slice(0, 12)}
                    </p>
                  </div>
                  <div>
                    <span
                      className="text-xs font-semibold uppercase tracking-wider"
                      style={{ color: "var(--color-brown-400)" }}
                    >
                      Status
                    </span>
                    <p
                      className="font-medium"
                      style={{ color: "var(--color-brown-700)" }}
                    >
                      {checkingStatus ? "Checking…" : statusError ? "Unavailable" : freshCase?.status ?? "Not verified"}
                    </p>
                  </div>
                </div>
              </div>

              <p className="mb-3 text-xs" aria-live="polite" style={{ color: "var(--color-brown-600)" }}>
                {checkingStatus
                  ? "Checking the latest review status before export…"
                  : statusError || !freshCase
                  ? statusError ?? "Review status is not verified."
                  : freshCase.unresolved_count > 0
                  ? `${freshCase.unresolved_count} line(s) remain unresolved. A validated export will be blocked.`
                  : "Latest backend review state has been checked."}
              </p>

              {/* Partial export option */}
              <label
                className="flex items-start gap-2.5 p-3 rounded-lg border mb-4 cursor-pointer"
                style={{
                  borderColor: "var(--color-sand-200)",
                  backgroundColor: "var(--color-cream-100)",
                }}
              >
                <input
                  type="checkbox"
                  checked={allowPartial}
                  onChange={(e) => setAllowPartial(e.target.checked)}
                  className="mt-0.5"
                />
                <span className="text-xs leading-relaxed" style={{ color: "var(--color-brown-600)" }}>
                  <strong className="font-semibold">Allow partial draft export.</strong>{" "}
                  Unresolved lines stay in the worksheet and are clearly marked as
                  draft, instead of blocking the export. A human must still review
                  every line before sending anything to a customer.
                </span>
              </label>

              {/* Error */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex items-start gap-2 p-3 rounded-lg mb-4"
                    role="alert"
                    style={{
                      backgroundColor: "var(--color-error-50)",
                      color: "var(--color-error-700)",
                    }}
                  >
                    <X size={16} className="flex-shrink-0 mt-0.5" />
                    <p className="text-xs">{error}</p>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Download / Generate */}
              <AnimatePresence mode="wait">
                {downloadUrl ? (
                  <motion.div
                    key="ready"
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 8 }}
                    className="text-center py-4"
                  >
                    <CheckCircle
                      size={36}
                      className="mx-auto mb-3"
                      style={{ color: "var(--color-success-500)" }}
                    />
                    <p
                      className="text-sm font-semibold mb-3"
                      style={{ color: "var(--color-success-700)" }}
                    >
                      Export ready!
                    </p>
                    {manifest && (
                      <p
                        className="text-xs mb-3"
                        style={{ color: "var(--color-brown-500)" }}
                      >
                        {manifest.approved_lines} approved of{" "}
                        {manifest.total_lines} lines ·{" "}
                        {manifest.unresolved_lines_omitted} unresolved ·{" "}
                        {manifest.is_draft ? "DRAFT" : "final"}
                      </p>
                    )}
                    <a
                      href={downloadUrl}
                      download
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 hover:shadow-md"
                      style={{
                        backgroundColor: "var(--color-amber-400)",
                        color: "var(--color-brown-900)",
                      }}
                    >
                      <Download size={16} />
                      Download worksheet
                    </a>
                  </motion.div>
                ) : (
                  <motion.div
                    key="generate"
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="text-center"
                  >
                    <button
                      onClick={handleExport}
                      disabled={exporting || checkingStatus || !freshCase || !!statusError}
                      className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 hover:shadow-md active:scale-[0.97] disabled:opacity-40"
                      style={{
                        backgroundColor: "var(--color-amber-400)",
                        color: "var(--color-brown-900)",
                      }}
                    >
                      {exporting ? (
                        <>
                          <span className="animate-spin-slow inline-block">
                            ⏳
                          </span>
                          Generating…
                        </>
                      ) : (
                        <>
                          <FileDown size={16} />
                          Generate draft export
                        </>
                      )}
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            {/* Footer */}
            <div
              className="flex justify-end px-5 py-4 border-t"
              style={{ borderColor: "var(--color-sand-200)" }}
            >
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-sm font-medium border transition-all duration-200"
                style={{
                  color: "var(--color-brown-500)",
                  borderColor: "var(--color-sand-200)",
                  backgroundColor: "var(--color-cream-100)",
                }}
              >
                Close
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
