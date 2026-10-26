"use client";

import React from "react";

interface ShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ShortcutsModal({ isOpen, onClose }: ShortcutsModalProps) {
  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">Keyboard Shortcuts & Operator Agreement</h2>
            <p className="modal-subtitle">RFQ Assistant v0.1 — Industrial Inside-Sales Workbench</p>
          </div>
          <button className="close-btn" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="modal-body">
          <section className="section">
            <h3 className="section-title">⌨ Keyboard Navigation</h3>
            <div className="shortcut-table">
              <div className="shortcut-row">
                <span className="key-combo font-mono">Tab / Shift+Tab</span>
                <span className="key-desc">Navigate through editable quantity and part fields</span>
              </div>
              <div className="shortcut-row">
                <span className="key-combo font-mono">Enter</span>
                <span className="key-desc">Commit cell edit and save changes</span>
              </div>
              <div className="shortcut-row">
                <span className="key-combo font-mono">Esc</span>
                <span className="key-desc">Close dialogs and modals</span>
              </div>
              <div className="shortcut-row">
                <span className="key-combo font-mono">Click Row</span>
                <span className="key-desc">Synchronizes and highlights exact source document locator</span>
              </div>
            </div>
          </section>

          <section className="section">
            <h3 className="section-title">🛡 Safety Invariants & Engineering Working Rules</h3>
            <ul className="rules-list">
              <li>
                <strong>No Automatic Quotation Dispatch:</strong> Generated worksheets and email replies are
                strictly labeled as drafts for staff review. No email is ever sent automatically.
              </li>
              <li>
                <strong>No Fabricated Part Numbers or Substitutions:</strong> Exact matching requires normalized
                part number AND manufacturer agreement. A text similarity score is not engineering evidence.
              </li>
              <li>
                <strong>Unresolved Fields Block Final Export:</strong> Missing quantities, brand collisions, and
                unknown items require explicit human review or selection of partial draft export.
              </li>
              <li>
                <strong>Immutable Audit Trail:</strong> Every cell modification, approval, and export is recorded
                with timestamps and operator attribution.
              </li>
            </ul>
          </section>

          <div className="modal-footer">
            <button className="close-action-btn" onClick={onClose}>
              Got it, close
            </button>
          </div>
        </div>
      </div>

      <style jsx>{`
        .modal-backdrop {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(15, 23, 42, 0.6);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 100;
          backdrop-filter: blur(2px);
        }
        .modal-dialog {
          background: #ffffff;
          border-radius: 10px;
          width: 90%;
          max-width: 600px;
          box-shadow: var(--shadow-lg);
          border: 1px solid var(--border-medium);
        }
        .modal-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          padding: 1.25rem 1.5rem;
          border-bottom: 1px solid var(--border-light);
        }
        .modal-title {
          font-size: 1.15rem;
          font-weight: 700;
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
        .modal-body {
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
        }
        .section-title {
          font-size: 0.9rem;
          font-weight: 700;
          color: var(--text-primary);
          margin-bottom: 0.65rem;
        }
        .shortcut-table {
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
          background: var(--bg-subtle);
          padding: 0.75rem;
          border-radius: 6px;
          border: 1px solid var(--border-light);
        }
        .shortcut-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.82rem;
        }
        .key-combo {
          background: #ffffff;
          border: 1px solid var(--border-medium);
          padding: 0.15rem 0.5rem;
          border-radius: 4px;
          font-weight: 600;
          color: var(--text-primary);
        }
        .key-desc {
          color: var(--text-secondary);
        }
        .rules-list {
          padding-left: 1.25rem;
          font-size: 0.82rem;
          color: var(--text-secondary);
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
          line-height: 1.4;
        }
        .rules-list strong {
          color: var(--text-primary);
        }
        .modal-footer {
          display: flex;
          justify-content: flex-end;
          padding-top: 0.5rem;
        }
        .close-action-btn {
          background: var(--accent-primary);
          color: #ffffff;
          border: none;
          padding: 0.45rem 1rem;
          border-radius: 6px;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
        }
        .font-mono { font-family: var(--font-mono); }
      `}</style>
    </div>
  );
}
