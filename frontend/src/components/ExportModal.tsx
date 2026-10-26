"use client";

import React, { useEffect, useState } from "react";
import { RFQCase } from "@/types";
import { exportWorksheet, getEmailDraft, getExportDownloadUrl } from "@/services/api";

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

  useEffect(() => {
    if (isOpen) {
      getEmailDraft(caseData.case_id)
        .then((res) => setEmailDraft(res.draft))
        .catch(() => setEmailDraft("Failed to generate email draft."));
    }
  }, [isOpen, caseData.case_id]);

  if (!isOpen) return null;

  const hasUnresolved = caseData.unresolved_count > 0;

  const handleDownload = async () => {
    setErrorMsg(null);
    setExporting(true);
    try {
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
          <div className={`status-summary-card ${hasUnresolved ? "warning" : "success"}`}>
            <div className="status-summary-header">
              <span className="summary-icon">{hasUnresolved ? "⚠" : "✓"}</span>
              <span className="summary-title font-bold">
                {hasUnresolved
                  ? `${caseData.unresolved_count} Unresolved Line(s) Pending Review`
                  : "All Line Items Approved and Grounded"}
              </span>
            </div>
            <p className="summary-desc">
              {hasUnresolved
                ? "Some lines have missing quantities, unresolved brand collisions, or pending decisions. By default, final exports are blocked until all rows are verified."
                : "All items have verified manufacturer part numbers and approved quantities. Ready for quotation export."}
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
            disabled={exporting || (hasUnresolved && !allowPartial)}
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
          background: rgba(4, 6, 12, 0.8);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 100;
          backdrop-filter: blur(16px);
        }
        .modal-dialog {
          background: var(--bg-surface-elevated);
          border-radius: 12px;
          width: 90%;
          max-width: 680px;
          box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6);
          border: 1px solid var(--border-medium);
          max-height: 90vh;
          overflow-y: auto;
          position: relative;
        }
        .modal-dialog::before {
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 2px;
          background: var(--accent-gradient);
        }
        .modal-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          padding: 1.5rem 1.75rem;
          border-bottom: 1px solid var(--border-light);
          background: var(--bg-surface);
        }
        .modal-title {
          font-size: 1.25rem;
          font-weight: 700;
          color: var(--text-primary);
          letter-spacing: -0.01em;
        }
        .modal-subtitle {
          font-size: 0.82rem;
          color: var(--text-muted);
          margin-top: 0.25rem;
        }
        .close-btn {
          background: none;
          border: none;
          font-size: 1.2rem;
          cursor: pointer;
          color: var(--text-muted);
          transition: color 0.15s ease;
        }
        .close-btn:hover {
          color: var(--text-primary);
        }
        .modal-body {
          padding: 1.75rem;
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
        }
        .error-banner {
          background: rgba(239, 68, 68, 0.15);
          color: #F87171;
          border: 1px solid rgba(239, 68, 68, 0.3);
          padding: 0.75rem 1.25rem;
          border-radius: 8px;
          font-size: 0.85rem;
        }
        .status-summary-card {
          border-radius: 8px;
          padding: 1rem 1.25rem;
          border: 1px solid transparent;
        }
        .status-summary-card.warning {
          background: rgba(245, 158, 11, 0.1);
          border-color: rgba(245, 158, 11, 0.3);
          color: #FCD34D;
        }
        .status-summary-card.success {
          background: rgba(16, 185, 129, 0.1);
          border-color: rgba(16, 185, 129, 0.3);
          color: #34D399;
        }
        .status-summary-header {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.95rem;
          margin-bottom: 0.35rem;
        }
        .summary-desc {
          font-size: 0.82rem;
          line-height: 1.45;
          opacity: 0.9;
        }
        .options-grid {
          display: flex;
          flex-direction: column;
          gap: 1rem;
          background: var(--bg-surface);
          padding: 1.25rem;
          border-radius: 8px;
          border: 1px solid var(--border-light);
        }
        .form-label {
          font-size: 0.82rem;
          font-weight: 600;
          color: var(--text-secondary);
          margin-bottom: 0.45rem;
          display: block;
        }
        .radio-group {
          display: flex;
          gap: 1.5rem;
        }
        .radio-label {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.85rem;
          color: var(--text-primary);
          cursor: pointer;
        }
        .partial-box {
          border-top: 1px solid var(--border-light);
          padding-top: 0.85rem;
        }
        .checkbox-label {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          cursor: pointer;
        }
        .checkbox-text {
          font-size: 0.85rem;
          color: #F59E0B;
          font-weight: 600;
        }
        .checkbox-hint {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin-left: 1.4rem;
          margin-top: 0.2rem;
        }
        .download-btn {
          background: var(--accent-gradient);
          border: 1px solid rgba(14, 165, 233, 0.4);
          color: #ffffff;
          padding: 0.85rem;
          border-radius: 8px;
          font-size: 0.92rem;
          font-weight: 700;
          cursor: pointer;
          box-shadow: 0 0 12px rgba(14, 165, 233, 0.25);
          transition: all 0.2s ease;
        }
        .download-btn:hover:not(:disabled) {
          box-shadow: 0 0 18px rgba(14, 165, 233, 0.45);
          transform: translateY(-1px);
        }
        .download-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          box-shadow: none;
        }
        .email-draft-section {
          border: 1px solid var(--border-light);
          border-radius: 8px;
          overflow: hidden;
          background: var(--bg-surface);
        }
        .email-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          background: var(--bg-subtle);
          padding: 0.6rem 0.85rem;
          border-bottom: 1px solid var(--border-light);
        }
        .email-title {
          font-size: 0.78rem;
          font-weight: 600;
          color: var(--text-secondary);
        }
        .copy-btn {
          background: var(--bg-surface-elevated);
          border: 1px solid var(--border-medium);
          color: var(--text-primary);
          padding: 0.3rem 0.75rem;
          border-radius: 6px;
          font-size: 0.75rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .copy-btn:hover {
          background: var(--bg-surface);
          border-color: var(--accent-primary);
        }
        .email-textarea {
          width: 100%;
          padding: 0.85rem;
          border: none;
          font-size: 0.8rem;
          line-height: 1.45;
          resize: vertical;
          background: var(--bg-app);
          color: var(--text-primary);
        }
        .safety-footer-notice {
          font-size: 0.75rem;
          color: var(--text-muted);
          line-height: 1.45;
          padding: 0.65rem 0.85rem;
          background: var(--bg-surface);
          border: 1px solid var(--border-light);
          border-radius: 6px;
        }
        .safety-footer-notice strong {
          color: #F59E0B;
        }
        .font-mono { font-family: var(--font-mono); }
        .font-bold { font-weight: 700; }
      `}</style>
    </div>
  );
}
