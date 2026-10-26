"use client";

import React from "react";
import { CaseStatus, MatchStatus, ReviewDecision } from "@/types";

interface StatusBadgeProps {
  type: "case" | "match" | "review";
  value: CaseStatus | MatchStatus | ReviewDecision | string;
}

export function StatusBadge({ type, value }: StatusBadgeProps) {
  let label = String(value);
  let icon = "•";
  let bg = "var(--bg-subtle)";
  let text = "var(--text-secondary)";
  let border = "var(--border-medium)";

  if (type === "case") {
    switch (value) {
      case "NEW":
        label = "New";
        icon = "✦";
        bg = "var(--status-info-bg)";
        text = "var(--status-info-text)";
        border = "var(--status-info-border)";
        break;
      case "PROCESSING":
        label = "Processing";
        icon = "⏳";
        bg = "var(--status-warning-bg)";
        text = "var(--status-warning-text)";
        border = "var(--status-warning-border)";
        break;
      case "NEEDS_REVIEW":
        label = "Needs review";
        icon = "⚠";
        bg = "var(--status-warning-bg)";
        text = "var(--status-warning-text)";
        border = "var(--status-warning-border)";
        break;
      case "READY_TO_EXPORT":
        label = "Ready to export";
        icon = "✓";
        bg = "var(--status-success-bg)";
        text = "var(--status-success-text)";
        border = "var(--status-success-border)";
        break;
      case "EXPORTED":
        label = "Exported";
        icon = "📦";
        bg = "var(--bg-subtle)";
        text = "var(--text-secondary)";
        border = "var(--border-medium)";
        break;
      case "FAILED":
        label = "Failed";
        icon = "✕";
        bg = "var(--status-error-bg)";
        text = "var(--status-error-text)";
        border = "var(--status-error-border)";
        break;
    }
  } else if (type === "match") {
    switch (value) {
      case "EXACT_MATCH":
        label = "Exact SKU";
        icon = "✓";
        bg = "var(--status-success-bg)";
        text = "var(--status-success-text)";
        border = "var(--status-success-border)";
        break;
      case "COLLISION":
        label = "Brand collision";
        icon = "⚠";
        bg = "var(--status-warning-bg)";
        text = "var(--status-warning-text)";
        border = "var(--status-warning-border)";
        break;
      case "NO_MATCH":
        label = "No match";
        icon = "✕";
        bg = "var(--status-error-bg)";
        text = "var(--status-error-text)";
        border = "var(--status-error-border)";
        break;
      case "MANUAL_OVERRIDE":
        label = "Manual override";
        icon = "✎";
        bg = "var(--status-info-bg)";
        text = "var(--status-info-text)";
        border = "var(--status-info-border)";
        break;
    }
  } else if (type === "review") {
    switch (value) {
      case "APPROVED":
        label = "Approved";
        icon = "✓";
        bg = "var(--status-success-bg)";
        text = "var(--status-success-text)";
        border = "var(--status-success-border)";
        break;
      case "NEEDS_CLARIFICATION":
        label = "Clarify";
        icon = "?";
        bg = "var(--status-warning-bg)";
        text = "var(--status-warning-text)";
        border = "var(--status-warning-border)";
        break;
      case "REJECTED":
        label = "Rejected";
        icon = "✕";
        bg = "var(--status-error-bg)";
        text = "var(--status-error-text)";
        border = "var(--status-error-border)";
        break;
      case "PENDING":
        label = "Pending";
        icon = "○";
        bg = "var(--bg-subtle)";
        text = "var(--text-muted)";
        border = "var(--border-light)";
        break;
    }
  }

  return (
    <span className="badge">
      <span className="badge-icon">{icon}</span>
      <span className="badge-text">{label}</span>

      <style jsx>{`
        .badge {
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          background-color: ${bg};
          color: ${text};
          border: 1px solid ${border};
          padding: 0.22rem 0.65rem;
          border-radius: 6px;
          font-size: 0.73rem;
          font-weight: 600;
          letter-spacing: 0.02em;
          white-space: nowrap;
          line-height: 1.2;
          box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25);
          transition: all 0.15s ease;
        }
        .badge-icon {
          font-size: 0.75rem;
          line-height: 1;
        }
      `}</style>
    </span>
  );
}
