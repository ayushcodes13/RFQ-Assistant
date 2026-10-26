"use client";

import React, { useState } from "react";
import { createCaseFromText, createCaseFromUpload } from "@/services/api";
import { RFQCase } from "@/types";

interface IngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCaseCreated: (createdCase: RFQCase) => void;
}

export function IngestModal({ isOpen, onClose, onCaseCreated }: IngestModalProps) {
  const [tab, setTab] = useState<"file" | "text">("file");
  const [file, setFile] = useState<File | null>(null);
  const [pastedText, setPastedText] = useState("");
  const [title, setTitle] = useState("");
  const [customer, setCustomer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMsg(null);
    setSubmitting(true);

    try {
      if (tab === "file") {
        if (!file) {
          setErrorMsg("Please select or drop a valid file (PDF, XLSX, CSV).");
          setSubmitting(false);
          return;
        }
        const created = await createCaseFromUpload(file, title || undefined, customer || undefined);
        onCaseCreated(created);
        onClose();
      } else {
        if (!pastedText.trim()) {
          setErrorMsg("Please enter or paste RFQ text.");
          setSubmitting(false);
          return;
        }
        const created = await createCaseFromText(pastedText, title || undefined, customer || undefined);
        onCaseCreated(created);
        onClose();
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to process quotation request.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">New RFQ Intake</h2>
            <p className="modal-subtitle">
              Upload customer request files or paste email message text for deterministic line extraction.
            </p>
          </div>
          <button className="close-btn" onClick={onClose} aria-label="Close modal">
            ✕
          </button>
        </div>

        <div className="tab-switcher">
          <button
            type="button"
            className={`tab-btn ${tab === "file" ? "active" : ""}`}
            onClick={() => setTab("file")}
          >
            📄 Upload File (PDF / XLSX / CSV)
          </button>
          <button
            type="button"
            className={`tab-btn ${tab === "text" ? "active" : ""}`}
            onClick={() => setTab("text")}
          >
            ✉ Paste Email / Parts List
          </button>
        </div>

        {errorMsg && <div className="error-banner">⚠ {errorMsg}</div>}

        <form onSubmit={handleSubmit} className="modal-body">
          <div className="form-row">
            <div className="form-group flex-2">
              <label className="form-label">Case Title / Reference (optional)</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Line 3 Maintenance Spares"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>
            <div className="form-group flex-1">
              <label className="form-label">Customer Name / Account (optional)</label>
              <input
                type="text"
                className="form-input"
                placeholder="e.g. Apex Manufacturing"
                value={customer}
                onChange={(e) => setCustomer(e.target.value)}
              />
            </div>
          </div>

          {tab === "file" ? (
            <div
              className="dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
            >
              <input
                type="file"
                id="rfq-file-input"
                className="file-input-hidden"
                accept=".xlsx,.csv,.pdf,.txt"
                onChange={(e) => e.target.files && setFile(e.target.files[0])}
              />
              <label htmlFor="rfq-file-input" className="dropzone-label">
                <div className="dropzone-icon">📁</div>
                <div className="dropzone-text">
                  {file ? (
                    <span className="file-selected">
                      Selected: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
                    </span>
                  ) : (
                    <>
                      <strong>Click to browse</strong> or drag & drop customer file here
                    </>
                  )}
                </div>
                <div className="dropzone-hint">
                  Supports Excel (.xlsx), CSV, Native PDF, and Text files. Max 10 MB.
                </div>
              </label>
            </div>
          ) : (
            <div className="form-group">
              <label className="form-label">Pasted RFQ Message Body</label>
              <textarea
                className="form-textarea"
                rows={8}
                placeholder="Paste customer email inquiry here... e.g.&#10;1. 10 pcs Schneider Electric LC1D09BD&#10;2. 4 units Siemens 6ES7223-1BL32-0XB0"
                value={pastedText}
                onChange={(e) => setPastedText(e.target.value)}
              />
            </div>
          )}

          <div className="security-notice">
            🔒 <strong>Safety & Privacy:</strong> Input text and files are treated strictly as data.
            Macros and embedded scripts are rejected. We never invent part numbers, stock, or lead times.
          </div>

          <div className="modal-footer">
            <button type="button" className="cancel-btn" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="submit-btn" disabled={submitting}>
              {submitting ? "Extracting line items..." : "Extract & Match Lines →"}
            </button>
          </div>
        </form>
      </div>

      <style jsx>{`
        .modal-backdrop {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
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
          overflow: hidden;
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
          font-size: 0.85rem;
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
        .tab-switcher {
          display: flex;
          background: #F8FAFC;
          border-bottom: 1px solid var(--border-light);
          padding: 0 1.5rem;
        }
        .tab-btn {
          background: none;
          border: none;
          padding: 0.75rem 1.25rem;
          font-size: 0.875rem;
          font-weight: 500;
          color: var(--text-secondary);
          cursor: pointer;
          border-bottom: 2px solid transparent;
        }
        .tab-btn:hover {
          color: var(--text-primary);
        }
        .tab-btn.active {
          color: var(--accent-primary);
          border-bottom-color: var(--accent-primary);
          background: #FFFFFF;
          font-weight: 600;
        }
        .modal-body {
          padding: 1.5rem;
        }
        .error-banner {
          background: #FEF2F2;
          color: #991B1B;
          border: 1px solid #FECACA;
          padding: 0.65rem 1rem;
          margin: 1rem 1.5rem 0 1.5rem;
          border-radius: 6px;
          font-size: 0.85rem;
        }
        .form-row {
          display: flex;
          gap: 1rem;
          margin-bottom: 1.25rem;
        }
        .flex-2 { flex: 2; }
        .flex-1 { flex: 1; }
        .form-group {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }
        .form-label {
          font-size: 0.82rem;
          font-weight: 600;
          color: var(--text-secondary);
        }
        .form-input {
          padding: 0.5rem 0.75rem;
          border: 1px solid var(--border-medium);
          background: #FFFFFF;
          color: var(--text-primary);
          border-radius: 6px;
          font-size: 0.875rem;
        }
        .form-textarea {
          padding: 0.75rem;
          border: 1px solid var(--border-medium);
          background: #FFFFFF;
          color: var(--text-primary);
          border-radius: 6px;
          font-size: 0.875rem;
          font-family: var(--font-mono);
          resize: vertical;
          line-height: 1.45;
        }
        .form-input:focus, .form-textarea:focus {
          outline: none;
          border-color: var(--accent-primary);
        }
        .dropzone {
          border: 2px dashed var(--border-medium);
          border-radius: 6px;
          background: #F8FAFC;
          padding: 2.25rem 1.5rem;
          text-align: center;
          cursor: pointer;
          transition: border-color 0.15s ease;
          margin-bottom: 1.25rem;
        }
        .dropzone:hover {
          border-color: var(--accent-primary);
        }
        .file-input-hidden {
          display: none;
        }
        .dropzone-label {
          cursor: pointer;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.4rem;
        }
        .dropzone-icon {
          font-size: 2rem;
        }
        .dropzone-text {
          font-size: 0.9rem;
          color: var(--text-primary);
          font-weight: 500;
        }
        .dropzone-hint {
          font-size: 0.78rem;
          color: var(--text-muted);
        }
        .file-selected {
          color: var(--accent-primary);
          font-weight: 500;
        }
        .security-notice {
          background: #F8FAFC;
          border: 1px solid var(--border-light);
          padding: 0.65rem 0.85rem;
          border-radius: 6px;
          font-size: 0.78rem;
          color: var(--text-muted);
          line-height: 1.4;
          margin-top: 1rem;
        }
        .security-notice strong {
          color: var(--text-secondary);
        }
        .modal-footer {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 0.75rem;
          margin-top: 1.5rem;
        }
        .cancel-btn {
          background: #FFFFFF;
          border: 1px solid var(--border-medium);
          color: var(--text-secondary);
          padding: 0.5rem 1rem;
          border-radius: 6px;
          font-size: 0.875rem;
          font-weight: 500;
          cursor: pointer;
        }
        .cancel-btn:hover {
          background: var(--bg-subtle);
          color: var(--text-primary);
        }
        .submit-btn {
          background: var(--accent-primary);
          border: 1px solid var(--accent-primary);
          color: #FFFFFF;
          padding: 0.5rem 1.25rem;
          border-radius: 6px;
          font-size: 0.875rem;
          font-weight: 500;
          cursor: pointer;
          transition: background 0.15s ease;
        }
        .submit-btn:hover:not(:disabled) {
          background: var(--accent-primary-hover);
        }
        .submit-btn:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
}
