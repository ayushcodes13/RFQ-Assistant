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
          max-width: 600px;
          box-shadow: 0 16px 40px rgba(0, 0, 0, 0.6);
          border: 1px solid var(--border-medium);
          position: relative;
          overflow: hidden;
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
          font-size: 1.2rem;
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
          gap: 1.5rem;
        }
        .section-title {
          font-size: 0.88rem;
          font-weight: 700;
          color: var(--text-primary);
          margin-bottom: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.5px;
        }
        .shortcut-table {
          display: flex;
          flex-direction: column;
          gap: 0.6rem;
          background: var(--bg-surface);
          padding: 1rem;
          border-radius: 8px;
          border: 1px solid var(--border-light);
        }
        .shortcut-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.85rem;
        }
        .key-combo {
          background: var(--bg-app);
          border: 1px solid var(--border-medium);
          padding: 0.25rem 0.65rem;
          border-radius: 6px;
          font-weight: 600;
          color: var(--accent-primary);
          box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
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
          gap: 0.6rem;
          line-height: 1.5;
        }
        .rules-list strong {
          color: var(--text-primary);
        }
        .modal-footer {
          display: flex;
          justify-content: flex-end;
          padding-top: 0.75rem;
        }
        .close-action-btn {
          background: var(--accent-gradient);
          color: #ffffff;
          border: 1px solid rgba(14, 165, 233, 0.4);
          padding: 0.55rem 1.25rem;
          border-radius: 8px;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          box-shadow: 0 0 12px rgba(14, 165, 233, 0.25);
          transition: all 0.2s ease;
        }
        .close-action-btn:hover {
          box-shadow: 0 0 18px rgba(14, 165, 233, 0.45);
          transform: translateY(-1px);
        }
        .font-mono { font-family: var(--font-mono); }
      `}</style>
    </div>
  );
}
