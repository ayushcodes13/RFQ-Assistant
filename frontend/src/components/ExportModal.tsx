"use client";

import React, { useEffect, useState } from "react";
import { RFQCase } from "@/types";
import { exportWorksheet, getCase, getEmailDraft, getExportDownloadUrl } from "@/services/api";

interface ExportModalProps {
  isOpen: boolean;
  caseData: RFQCase;
  onClose: () => void;
}

export function ExportModal({ isOpen, caseData, onClose }: ExportModalProps) {
  const [allowPartial, setAllowPartial] = useState(false);
  const [format, setFormat] = useState<"xlsx" | "csv">("xlsx");
  const [exporting, setExporting] = useState(false);
  const [emailDraft, setEmailDraft] = useState<string>("");
  const [copiedEmail, setCopiedEmail] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [freshCase, setFreshCase] = useState<RFQCase | null>(null);
  const [statusLoading, setStatusLoading] = useState(false);
  const [statusError, setStatusError] = useState<string | null>(null);

  // Case props can be stale after inline review. Always refetch from the
  // backend on open; it owns the authoritative export eligibility.
  useEffect(() => {
    if (!isOpen) return;
    let active = true;
    setAllowPartial(false);
    setFreshCase(null);
    setStatusError(null);
    setStatusLoading(true);
    getCase(caseData.case_id)
      .then((value) => { if (active) setFreshCase(value); })
      .catch(() => { if (active) setStatusError("Cannot verify the latest review status. Close and reopen export."); })
      .finally(() => { if (active) setStatusLoading(false); });
    return () => { active = false; };
  }, [isOpen, caseData.case_id]);

  useEffect(() => {
    if (isOpen) {
      getEmailDraft(caseData.case_id)
        .then((res) => setEmailDraft(res.draft))
        .catch(() => setEmailDraft("Failed to generate email draft."));
    }
  }, [isOpen, caseData.case_id]);

  if (!isOpen) return null;

  const hasUnresolved = (freshCase?.unresolved_count ?? 0) > 0;
  const canExport = !!freshCase && !statusLoading && !statusError && (!hasUnresolved || allowPartial);

  const handleDownload = async () => {
    setErrorMsg(null);
    setExporting(true);
    try {
      // Race defense: verify current backend state again at the moment of export.
      const verified = await getCase(caseData.case_id);
      setFreshCase(verified);
      if (verified.unresolved_count > 0 && !allowPartial) {
        throw new Error("Review status changed. Resolve remaining lines or choose a partial draft.");
      }
      const manifest = await exportWorksheet(
        caseData.case_id,
        allowPartial,
        format,
        "Inside Sales"
      );
      // Trigger file download
      const downloadUrl = getExportDownloadUrl(caseData.case_id, manifest.export_id);
      window.open(downloadUrl, "_blank");
    } catch (err: any) {
      setErrorMsg(err.message || "Export validation failed.");
    } finally {
      setExporting(false);
    }
  };

  const handleCopyEmail = () => {
    navigator.clipboard.writeText(emailDraft);
    setCopiedEmail(true);
    setTimeout(() => setCopiedEmail(false), 2500);
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">Export Quotation Worksheet</h2>
            <p className="modal-subtitle">Case #{caseData.case_id} — {caseData.title}</p>
          </div>
          <button className="close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          {errorMsg && <div className="error-banner">⚠ {errorMsg}</div>}

          {/* Validation Status Summary */}
          <div className={`status-summary-card ${statusLoading || statusError || hasUnresolved ? "warning" : "success"}`}>
            <div className="status-summary-header">
              <span className="summary-icon">{hasUnresolved ? "⚠" : "✓"}</span>
              <span className="summary-title font-bold">
                {statusLoading ? "Checking latest review status..."
                  : statusError ? "Current review status unavailable"
                  : hasUnresolved ? `${freshCase?.unresolved_count ?? 0} Unresolved Line(s) Pending Review`
                  : "All Line Items Approved and Grounded"}
              </span>
            </div>
            <p className="summary-desc">
              {statusLoading ? "Checking the backend before enabling export."
                : statusError || !freshCase ? "Cannot safely export without a fresh case status."
                : hasUnresolved
                  ? "Some lines have missing quantities, brand collisions, critical warnings or pending review. Full validated exports are blocked."
                  : "The latest backend review state reports all line items approved and eligible for a draft worksheet."}
            </p>
          </div>

          {/* Format & Mode Selection */}
          <div className="options-grid">
            <div className="form-group">
              <label className="form-label">Worksheet Format:</label>
              <div className="radio-group">
                <label className="radio-label">
                  <input
                    type="radio"
                    name="export-fmt"
                    checked={format === "xlsx"}
                    onChange={() => setFormat("xlsx")}
                  />
                  <span>Excel Workbook (.xlsx)</span>
                </label>
                <label className="radio-label">
                  <input
                    type="radio"
                    name="export-fmt"
                    checked={format === "csv"}
                    onChange={() => setFormat("csv")}
                  />
                  <span>Comma-Separated Values (.csv)</span>
                </label>
              </div>
            </div>

            {hasUnresolved && (
              <div className="partial-box">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={allowPartial}
                    onChange={(e) => setAllowPartial(e.target.checked)}
                  />
                  <span className="checkbox-text font-bold">
                    Allow Partial Draft Export (Include unresolved lines with DRAFT banner)
                  </span>
                </label>
                <div className="checkbox-hint">
                  Required to export when lines remain unverified. Watermarked as internal draft.
                </div>
              </div>
            )}
          </div>

          <button
            className="download-btn"
            disabled={exporting || !canExport}
            onClick={handleDownload}
          >
            {exporting ? "Generating Worksheet..." : `Download Quote Preparation Worksheet (${format.toUpperCase()})`}
          </button>

          {/* Unsent Email Draft Box */}
          <div className="email-draft-section">
            <div className="email-header">
              <div className="email-title">
                ✉ Unsent Customer Clarification Draft (Staff Sends Manually):
              </div>
              <button className="copy-btn" onClick={handleCopyEmail}>
                {copiedEmail ? "✓ Copied to Clipboard!" : "Copy Draft Text"}
              </button>
            </div>
            <textarea
              className="email-textarea font-mono"
              rows={8}
              readOnly
              value={emailDraft}
            />
          </div>

          <div className="safety-footer-notice">
            ⚠ <strong>Safety Invariant:</strong> No automatic emails or purchase orders will ever be sent.
            Unit prices are blank unless authorized. Staff retains commercial ownership of quotations.
          </div>
        </div>
      </div>

      <style jsx>{`
        .modal-backdrop {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(15, 23, 42, 0.4);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 100;
        }
        .modal-dialog {
          background: #FFFFFF;
          border-radius: 8px;
          width: 90%;
          max-width: 640px;
          box-shadow: var(--shadow-lg);
          border: 1px solid var(--border-light);
          max-height: 90vh;
          overflow-y: auto;
        }
        .modal-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          padding: 1.25rem 1.5rem;
          border-bottom: 1px solid var(--border-light);
          background: #FFFFFF;
        }
        .modal-title {
          font-size: 1.15rem;
          font-weight: 600;
          color: var(--text-primary);
        }
        .modal-subtitle {
          font-size: 0.82rem;
          color: var(--text-muted);
          margin-top: 0.2rem;
        }
        .close-btn {
          background: none;
          border: none;
          font-size: 1.1rem;
          cursor: pointer;
          color: var(--text-muted);
        }
        .close-btn:hover {
          color: var(--text-primary);
        }
        .modal-body {
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
        }
        .error-banner {
          background: #FEF2F2;
          color: #991B1B;
          border: 1px solid #FECACA;
          padding: 0.65rem 1rem;
          border-radius: 6px;
          font-size: 0.85rem;
        }
        .status-summary-card {
          border-radius: 6px;
          padding: 0.85rem 1rem;
          border: 1px solid transparent;
        }
        .status-summary-card.warning {
          background: #FFFBEB;
          border-color: #FDE68A;
          color: #92400E;
        }
        .status-summary-card.success {
          background: #ECFDF5;
          border-color: #A7F3D0;
          color: #065F46;
        }
        .status-summary-header {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.92rem;
          margin-bottom: 0.25rem;
        }
        .summary-desc {
          font-size: 0.82rem;
          line-height: 1.4;
        }
        .options-grid {
          display: flex;
          flex-direction: column;
          gap: 0.85rem;
          background: #F8FAFC;
          padding: 1rem;
          border-radius: 6px;
          border: 1px solid var(--border-light);
        }
        .form-label {
          font-size: 0.82rem;
          font-weight: 600;
          color: var(--text-secondary);
          margin-bottom: 0.35rem;
          display: block;
        }
        .radio-group {
          display: flex;
          gap: 1.5rem;
        }
        .radio-label {
          display: flex;
          align-items: center;
          gap: 0.45rem;
          font-size: 0.85rem;
          color: var(--text-primary);
          cursor: pointer;
        }
        .partial-box {
          border-top: 1px solid var(--border-light);
          padding-top: 0.75rem;
        }
        .checkbox-label {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          cursor: pointer;
        }
        .checkbox-text {
          font-size: 0.85rem;
          color: #92400E;
          font-weight: 500;
        }
        .checkbox-hint {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin-left: 1.4rem;
          margin-top: 0.15rem;
        }
        .download-btn {
          background: var(--accent-primary);
          border: 1px solid var(--accent-primary);
          color: #FFFFFF;
          padding: 0.65rem 1rem;
          border-radius: 6px;
          font-size: 0.875rem;
          font-weight: 500;
          cursor: pointer;
          transition: background 0.15s ease;
        }
        .download-btn:hover:not(:disabled) {
          background: var(--accent-primary-hover);
        }
        .download-btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
        .email-draft-section {
          border: 1px solid var(--border-light);
          border-radius: 6px;
          overflow: hidden;
          background: #FFFFFF;
        }
        .email-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: #F8FAFC;
          padding: 0.5rem 0.75rem;
          border-bottom: 1px solid var(--border-light);
        }
        .email-title {
          font-size: 0.78rem;
          font-weight: 600;
          color: var(--text-secondary);
        }
        .copy-btn {
          background: #FFFFFF;
          border: 1px solid var(--border-medium);
          color: var(--text-secondary);
          padding: 0.25rem 0.6rem;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 500;
          cursor: pointer;
        }
        .copy-btn:hover {
          background: var(--bg-subtle);
          color: var(--text-primary);
        }
        .email-textarea {
          width: 100%;
          padding: 0.75rem;
          border: none;
          font-size: 0.8rem;
          line-height: 1.4;
          resize: vertical;
          background: #FAFAFA;
          color: var(--text-primary);
        }
        .safety-footer-notice {
          font-size: 0.75rem;
          color: var(--text-muted);
          line-height: 1.4;
          padding: 0.6rem 0.8rem;
          background: #F8FAFC;
          border: 1px solid var(--border-light);
          border-radius: 6px;
        }
        .safety-footer-notice strong {
          color: var(--text-secondary);
        }
        .font-mono { font-family: var(--font-mono); }
        .font-bold { font-weight: 600; }
      `}</style>
    </div>
  );
}
