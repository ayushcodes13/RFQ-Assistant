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
            <div className="logo-subtitle">Industrial Quotation Workbench</div>
          </div>
        </div>

        <span className="demo-badge" title="No real customer data or outbound email access.">
          DEMO BENCHMARK — SYNTHETIC DATA
        </span>
      </div>

      <nav className="header-nav">
        <button
          className={`nav-btn ${currentTab === "inbox" ? "active" : ""}`}
          onClick={() => onTabChange("inbox")}
        >
          Cases Inbox
        </button>

        {activeCaseId && (
          <button
            className={`nav-btn ${currentTab === "workbench" ? "active" : ""}`}
            onClick={() => onTabChange("workbench")}
          >
            Review Workbench (#{activeCaseId.slice(0, 10)})
          </button>
        )}

        <button
          className={`nav-btn ${currentTab === "catalog" ? "active" : ""}`}
          onClick={() => onTabChange("catalog")}
        >
          Catalog Master
        </button>
      </nav>

      <div className="header-right">
        <button className="secondary-btn" onClick={onOpenShortcuts} title="Keyboard shortcuts & guide">
          ⌨ Shortcuts / Help
        </button>
        <button className="primary-btn" onClick={onOpenNewRfq}>
          + New RFQ
        </button>
        <div className="user-indicator" title="Logged in operator">
          <span className="user-dot"></span>
          Inside Sales Desk
        </div>
      </div>

      <style jsx>{`
        .header-container {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0 1.5rem;
          height: 64px;
          background: #ffffff;
          border-bottom: 1px solid var(--border-light);
          position: sticky;
          top: 0;
          z-index: 40;
        }
        .header-left {
          display: flex;
          align-items: center;
          gap: 1.25rem;
        }
        .logo-group {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          cursor: pointer;
        }
        .logo-icon {
          width: 36px;
          height: 36px;
          background: var(--accent-primary);
          color: #ffffff;
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 0.9rem;
          letter-spacing: -0.5px;
        }
        .logo-title {
          font-size: 1.05rem;
          font-weight: 700;
          color: var(--text-primary);
          line-height: 1.2;
        }
        .logo-subtitle {
          font-size: 0.75rem;
          color: var(--text-muted);
        }
        .demo-badge {
          background: var(--bg-subtle);
          color: var(--text-secondary);
          border: 1px solid var(--border-medium);
          padding: 0.2rem 0.55rem;
          border-radius: 4px;
          font-size: 0.72rem;
          font-weight: 600;
          letter-spacing: 0.3px;
        }
        .header-nav {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .nav-btn {
          background: none;
          border: none;
          padding: 0.45rem 0.85rem;
          border-radius: 6px;
          font-size: 0.88rem;
          font-weight: 500;
          color: var(--text-secondary);
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .nav-btn:hover {
          background: var(--bg-subtle);
          color: var(--text-primary);
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
        .secondary-btn {
          background: #ffffff;
          border: 1px solid var(--border-medium);
          color: var(--text-secondary);
          padding: 0.45rem 0.75rem;
          border-radius: 6px;
          font-size: 0.82rem;
          font-weight: 500;
          cursor: pointer;
        }
        .secondary-btn:hover {
          background: var(--bg-subtle);
          color: var(--text-primary);
        }
        .primary-btn {
          background: var(--accent-primary);
          border: 1px solid var(--accent-primary);
          color: #ffffff;
          padding: 0.45rem 0.9rem;
          border-radius: 6px;
          font-size: 0.85rem;
          font-weight: 600;
          cursor: pointer;
          transition: background 0.15s ease;
        }
        .primary-btn:hover {
          background: var(--accent-primary-hover);
        }
        .user-indicator {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.78rem;
          color: var(--text-muted);
          padding-left: 0.5rem;
          border-left: 1px solid var(--border-light);
        }
        .user-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #10B981;
        }
      `}</style>
    </header>
  );
}
