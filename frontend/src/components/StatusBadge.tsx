"use client";

import React from "react";
import { CaseStatus, MatchStatus, ReviewDecision } from "@/types";

interface StatusBadgeProps {
  type: "case" | "match" | "review";
  value: CaseStatus | MatchStatus | ReviewDecision | string;
}

export function StatusBadge({ type, value }: StatusBadgeProps) {
  let label = String(value);
  let bg = "var(--bg-subtle)";
  let text = "var(--text-secondary)";
  let border = "var(--border-medium)";

  if (type === "case") {
    switch (value) {
      case "NEW":
        label = "New";
        bg = "var(--status-info-bg)";
        text = "var(--status-info-text)";
        border = "var(--status-info-border)";
        break;
      case "PROCESSING":
        label = "Processing";
        bg = "var(--status-warning-bg)";
        text = "var(--status-warning-text)";
        border = "var(--status-warning-border)";
        break;
      case "NEEDS_REVIEW":
        label = "Needs Review";
        bg = "var(--status-warning-bg)";
        text = "var(--status-warning-text)";
        border = "var(--status-warning-border)";
        break;
      case "READY_TO_EXPORT":
        label = "Ready to Export";
        bg = "var(--status-success-bg)";
        text = "var(--status-success-text)";
        border = "var(--status-success-border)";
        break;
      case "EXPORTED":
        label = "Exported";
        bg = "var(--bg-subtle)";
        text = "var(--text-secondary)";
        border = "var(--border-medium)";
        break;
      case "FAILED":
        label = "Failed";
        bg = "var(--status-error-bg)";
        text = "var(--status-error-text)";
        border = "var(--status-error-border)";
        break;
    }
  } else if (type === "match") {
    switch (value) {
      case "EXACT_MATCH":
        label = "Exact Match";
        bg = "var(--status-success-bg)";
        text = "var(--status-success-text)";
        border = "var(--status-success-border)";
        break;
      case "COLLISION":
        label = "Brand Collision";
        bg = "var(--status-warning-bg)";
        text = "var(--status-warning-text)";
        border = "var(--status-warning-border)";
        break;
      case "NO_MATCH":
        label = "No Match";
        bg = "var(--status-error-bg)";
        text = "var(--status-error-text)";
        border = "var(--status-error-border)";
        break;
      case "MANUAL_OVERRIDE":
        label = "Manual SKU";
        bg = "var(--status-info-bg)";
        text = "var(--status-info-text)";
        border = "var(--status-info-border)";
        break;
    }
  } else if (type === "review") {
    switch (value) {
      case "APPROVED":
        label = "Approved";
        bg = "var(--status-success-bg)";
        text = "var(--status-success-text)";
        border = "var(--status-success-border)";
        break;
      case "NEEDS_CLARIFICATION":
        label = "Clarify";
        bg = "var(--status-warning-bg)";
        text = "var(--status-warning-text)";
        border = "var(--status-warning-border)";
        break;
      case "REJECTED":
        label = "Rejected";
        bg = "var(--status-error-bg)";
        text = "var(--status-error-text)";
        border = "var(--status-error-border)";
        break;
      case "PENDING":
        label = "Pending";
        bg = "var(--bg-subtle)";
        text = "var(--text-muted)";
        border = "var(--border-light)";
        break;
    }
  }

  return (
    <span className="badge">
      <span className="badge-text">{label}</span>

      <style jsx>{`
        .badge {
          display: inline-flex;
          align-items: center;
          background-color: ${bg};
          color: ${text};
          border: 1px solid ${border};
          padding: 0.15rem 0.5rem;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 500;
          white-space: nowrap;
          line-height: 1.3;
        }
      `}</style>
    </span>
  );
}
