"use client";

import React from "react";

interface HeaderProps {
  currentTab: "inbox" | "workbench" | "catalog";
  onTabChange: (tab: "inbox" | "workbench" | "catalog") => void;
  onOpenNewRfq: () => void;
  onOpenShortcuts: () => void;
  activeCaseId?: string | null;
}

export function Header({
  currentTab,
  onTabChange,
  onOpenNewRfq,
  onOpenShortcuts,
  activeCaseId,
}: HeaderProps) {
  return (
    <header className="header-container">
      <div className="header-left">
        <div className="logo-group" onClick={() => onTabChange("inbox")}>
          <div className="logo-icon">RFQ</div>
          <div>
            <div className="logo-title">RFQ Assistant</div>
            <div className="logo-subtitle">Quotation Workbench</div>
          </div>
        </div>
      </div>

      <nav className="header-nav">
        <button
          className={`nav-btn ${currentTab === "inbox" ? "active" : ""}`}
          onClick={() => onTabChange("inbox")}
        >
          All Inquiries
        </button>

        {activeCaseId && (
          <button
            className={`nav-btn ${currentTab === "workbench" ? "active" : ""}`}
            onClick={() => onTabChange("workbench")}
          >
            Review Worksheet
          </button>
        )}

        <button
          className={`nav-btn ${currentTab === "catalog" ? "active" : ""}`}
          onClick={() => onTabChange("catalog")}
        >
          Item Catalog
        </button>
      </nav>

      <div className="header-right">
        <button className="btn-secondary" onClick={onOpenShortcuts} title="Keyboard shortcuts & guide">
          Help & Rules
        </button>
        <button className="btn-primary" onClick={onOpenNewRfq}>
          + New Quote Request
        </button>
      </div>

      <style jsx>{`
        .header-container {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 1.5rem;
          height: 60px;
          background: #FFFFFF;
          border-bottom: 1px solid var(--border-light);
          position: sticky;
          top: 0;
          z-index: 40;
        }
        .header-left {
          display: flex;
          align-items: center;
          gap: 1.5rem;
        }
        .logo-group {
          display: flex;
          align-items: center;
          gap: 0.65rem;
          cursor: pointer;
        }
        .logo-icon {
          width: 32px;
          height: 32px;
          background: var(--accent-primary);
          color: #FFFFFF;
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 0.78rem;
          letter-spacing: -0.5px;
        }
        .logo-title {
          font-size: 0.95rem;
          font-weight: 600;
          color: var(--text-primary);
          line-height: 1.2;
        }
        .logo-subtitle {
          font-size: 0.72rem;
          color: var(--text-muted);
        }
        .header-nav {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .nav-btn {
          background: transparent;
          border: none;
          padding: 0.45rem 0.85rem;
          border-radius: 6px;
          font-size: 0.875rem;
          font-weight: 500;
          color: var(--text-secondary);
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .nav-btn:hover {
          color: var(--text-primary);
          background: var(--bg-subtle);
        }
        .nav-btn.active {
          background: var(--accent-subtle);
          color: var(--accent-primary);
          font-weight: 600;
        }
        .header-right {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }
      `}</style>
    </header>
  );
}
