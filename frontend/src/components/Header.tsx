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
          padding: 0 1.75rem;
          height: 68px;
          background: var(--bg-glass);
          backdrop-filter: blur(16px);
          -webkit-backdrop-filter: blur(16px);
          border-bottom: 1px solid var(--border-light);
          position: sticky;
          top: 0;
          z-index: 50;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
        }
        .header-left {
          display: flex;
          align-items: center;
          gap: 1.5rem;
        }
        .logo-group {
          display: flex;
          align-items: center;
          gap: 0.85rem;
          cursor: pointer;
        }
        .logo-icon {
          width: 38px;
          height: 38px;
          background: var(--accent-gradient);
          color: #ffffff;
          border-radius: 9px;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 800;
          font-size: 0.88rem;
          letter-spacing: -0.5px;
          box-shadow: 0 0 16px rgba(2, 132, 199, 0.4);
          border: 1px solid rgba(255, 255, 255, 0.15);
        }
        .logo-title {
          font-size: 1.1rem;
          font-weight: 700;
          color: var(--text-primary);
          line-height: 1.2;
          font-family: var(--font-heading);
          letter-spacing: -0.02em;
        }
        .logo-subtitle {
          font-size: 0.72rem;
          color: var(--text-muted);
          font-weight: 500;
          letter-spacing: 0.02em;
        }
        .demo-badge {
          background: rgba(2, 132, 199, 0.1);
          color: #38BDF8;
          border: 1px solid rgba(56, 189, 248, 0.25);
          padding: 0.25rem 0.65rem;
          border-radius: 6px;
          font-size: 0.7rem;
          font-weight: 600;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
        }
        .header-nav {
          display: flex;
          align-items: center;
          gap: 0.35rem;
          background: rgba(0, 0, 0, 0.25);
          padding: 0.3rem;
          border-radius: 10px;
          border: 1px solid var(--border-light);
        }
        .nav-btn {
          background: transparent;
          border: none;
          padding: 0.45rem 1rem;
          border-radius: 7px;
          font-size: 0.875rem;
          font-weight: 500;
          color: var(--text-muted);
          cursor: pointer;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .nav-btn:hover {
          color: var(--text-primary);
          background: rgba(255, 255, 255, 0.05);
        }
        .nav-btn.active {
          background: var(--bg-surface-elevated);
          color: #38BDF8;
          font-weight: 600;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
          border: 1px solid rgba(56, 189, 248, 0.2);
        }
        .header-right {
          display: flex;
          align-items: center;
          gap: 0.85rem;
        }
        .user-indicator {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          font-size: 0.8rem;
          font-weight: 500;
          color: var(--text-secondary);
          padding: 0.35rem 0.75rem;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid var(--border-light);
          border-radius: 8px;
        }
        .user-dot {
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: #10B981;
          box-shadow: 0 0 10px rgba(16, 185, 129, 0.7);
          animation: beaconGlow 2s infinite ease-in-out;
        }
      `}</style>
    </header>
  );
}
