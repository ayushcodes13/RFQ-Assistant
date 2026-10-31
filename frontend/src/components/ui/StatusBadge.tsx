"use client";

import React from "react";
import { motion } from "framer-motion";
import {
  CheckCircle,
  Clock,
  AlertTriangle,
  XCircle,
  Eye,
  Package,
  CircleDot,
  HelpCircle,
  Sparkles,
  Loader2,
} from "lucide-react";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md";
}

type StatusConfig = {
  label: string;
  icon: React.ReactNode;
  bg: string;
  text: string;
  border: string;
};

const iconSm = 12;
const iconMd = 14;

function getConfig(status: string, iconSize: number): StatusConfig {
  // Backend enums are upper-case (APPROVED, NEEDS_REVIEW); UI config keys are
  // lower-case. Normalise once so both spellings render the same badge.
  const key = status.toLowerCase();
  const configs: Record<string, StatusConfig> = {
    new: {
      label: "New",
      icon: <Sparkles size={iconSize} />,
      bg: "var(--color-info-50)",
      text: "var(--color-info-700)",
      border: "var(--color-info-100)",
    },
    processing: {
      label: "Processing",
      icon: <Loader2 size={iconSize} className="animate-spin-slow" />,
      bg: "var(--color-info-50)",
      text: "var(--color-info-700)",
      border: "var(--color-info-100)",
    },
    needs_review: {
      label: "Needs review",
      icon: <Eye size={iconSize} />,
      bg: "var(--color-warning-50)",
      text: "var(--color-warning-700)",
      border: "var(--color-warning-100)",
    },
    ready_to_export: {
      label: "Ready",
      icon: <CheckCircle size={iconSize} />,
      bg: "var(--color-success-50)",
      text: "var(--color-success-700)",
      border: "var(--color-success-100)",
    },
    exported: {
      label: "Exported",
      icon: <Package size={iconSize} />,
      bg: "var(--color-success-50)",
      text: "var(--color-success-700)",
      border: "var(--color-success-100)",
    },
    failed: {
      label: "Failed",
      icon: <XCircle size={iconSize} />,
      bg: "var(--color-error-50)",
      text: "var(--color-error-700)",
      border: "var(--color-error-100)",
    },
    pending: {
      label: "Pending",
      icon: <CircleDot size={iconSize} />,
      bg: "var(--color-info-50)",
      text: "var(--color-info-700)",
      border: "var(--color-info-100)",
    },
    unreviewed: {
      label: "Unreviewed",
      icon: <CircleDot size={iconSize} />,
      bg: "var(--color-info-50)",
      text: "var(--color-info-700)",
      border: "var(--color-info-100)",
    },
    approved: {
      label: "Approved",
      icon: <CheckCircle size={iconSize} />,
      bg: "var(--color-success-50)",
      text: "var(--color-success-700)",
      border: "var(--color-success-100)",
    },
    needs_clarification: {
      label: "Clarify",
      icon: <HelpCircle size={iconSize} />,
      bg: "var(--color-warning-50)",
      text: "var(--color-warning-700)",
      border: "var(--color-warning-100)",
    },
    rejected: {
      label: "Rejected",
      icon: <XCircle size={iconSize} />,
      bg: "var(--color-error-50)",
      text: "var(--color-error-700)",
      border: "var(--color-error-100)",
    },
  };

  return (
    configs[key] || {
      label: status,
      icon: <CircleDot size={iconSize} />,
      bg: "var(--color-info-50)",
      text: "var(--color-info-700)",
      border: "var(--color-info-100)",
    }
  );
}

export function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  const iconSize = size === "sm" ? iconSm : iconMd;
  const config = getConfig(status, iconSize);
  const padding = size === "sm" ? "px-2 py-0.5" : "px-2.5 py-1";
  const fontSize = size === "sm" ? "text-[11px]" : "text-xs";

  return (
    <motion.span
      initial={{ opacity: 0, scale: 0.85 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      className={`inline-flex items-center gap-1.5 ${padding} rounded-full font-medium ${fontSize} whitespace-nowrap border`}
      style={{
        backgroundColor: config.bg,
        color: config.text,
        borderColor: config.border,
      }}
    >
      <span className="flex-shrink-0" aria-hidden="true">
        {config.icon}
      </span>
      {config.label}
    </motion.span>
  );
}
