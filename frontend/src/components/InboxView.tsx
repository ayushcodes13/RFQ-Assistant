"use client";

import React from "react";
import { motion } from "framer-motion";
import { FileText, Paperclip, Clock, RotateCw, Plus } from "lucide-react";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { MotionWrapper } from "@/components/ui/MotionWrapper";
import { RFQCase } from "@/types";

interface InboxViewProps {
  cases: RFQCase[];
  loading: boolean;
  onSelectCase: (caseId: string) => void;
  onRefresh: () => void;
  onOpenNewRfq: () => void;
}

const cardVariants = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: {
      delay: i * 0.06,
      duration: 0.5,
      ease: [0.16, 1, 0.3, 1] as [number, number, number, number],
    },
  }),
};

export function InboxView({
  cases,
  loading,
  onSelectCase,
  onRefresh,
  onOpenNewRfq,
}: InboxViewProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <LoadingSpinner message="Loading cases…" size="lg" />
      </div>
    );
  }

  if (cases.length === 0) {
    return (
      <MotionWrapper direction="up" className="flex items-center justify-center min-h-[60vh] px-4">
        <div className="text-center max-w-md">
          {/* Decorative icon area */}
          <div className="relative mx-auto w-28 h-28 mb-6">
            <div
              className="absolute inset-0 rounded-2xl border-2 border-dashed rotate-6"
              style={{ borderColor: "var(--color-sand-300)" }}
            />
            <div
              className="absolute inset-0 rounded-2xl flex items-center justify-center"
              style={{ backgroundColor: "var(--color-cream-200)" }}
            >
              <FileText
                size={48}
                style={{ color: "var(--color-amber-400)" }}
              />
            </div>
          </div>

          <h2
            className="text-xl sm:text-2xl font-bold mb-2"
            style={{ color: "var(--color-brown-800)" }}
          >
            No RFQ cases yet
          </h2>
          <p
            className="text-sm sm:text-base mb-6 leading-relaxed"
            style={{ color: "var(--color-brown-400)" }}
          >
            Upload a PDF, Excel or CSV file, or paste email text to get
            started with your first quotation.
          </p>
          <button
            onClick={onOpenNewRfq}
            className="inline-flex items-center gap-2 px-6 py-2.5 rounded-xl text-sm font-semibold transition-all duration-200 hover:shadow-lg active:scale-[0.97]"
            style={{
              backgroundColor: "var(--color-amber-400)",
              color: "var(--color-brown-900)",
            }}
          >
            <Plus size={18} />
            New RFQ
          </button>
        </div>
      </MotionWrapper>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 py-6 sm:py-8">
      {/* Header Row */}
      <MotionWrapper direction="up">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h2
              className="text-xl sm:text-2xl font-bold"
              style={{ color: "var(--color-brown-800)" }}
            >
              RFQ Cases
            </h2>
            <p
              className="text-sm mt-0.5"
              style={{ color: "var(--color-brown-400)" }}
            >
              {cases.length} case{cases.length !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onRefresh}
              className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium border transition-all duration-200 active:scale-[0.97]"
              style={{
                color: "var(--color-brown-500)",
                borderColor: "var(--color-sand-200)",
                backgroundColor: "var(--color-cream-100)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor =
                  "var(--color-sand-400)";
                e.currentTarget.style.backgroundColor =
                  "var(--color-sand-50)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor =
                  "var(--color-sand-200)";
                e.currentTarget.style.backgroundColor =
                  "var(--color-cream-100)";
              }}
            >
              <RotateCw size={15} />
              <span className="hidden sm:inline">Refresh</span>
            </button>
            <button
              onClick={onOpenNewRfq}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-200 hover:shadow-md active:scale-[0.97]"
              style={{
                backgroundColor: "var(--color-amber-400)",
                color: "var(--color-brown-900)",
              }}
            >
              <Plus size={16} />
              <span>New RFQ</span>
            </button>
          </div>
        </div>
      </MotionWrapper>

      {/* Cards Grid */}
      <div className="grid gap-3 sm:gap-4 grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        {cases.map((c, i) => (
          <motion.button
            key={c.case_id}
            custom={i}
            variants={cardVariants}
            initial="hidden"
            animate="visible"
            whileHover={{ y: -3, transition: { duration: 0.2 } }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onSelectCase(c.case_id)}
            className="text-left w-full p-4 sm:p-5 rounded-xl border transition-shadow duration-200 hover:shadow-md"
            style={{
              backgroundColor: "var(--color-cream-100)",
              borderColor: "var(--color-sand-200)",
            }}
          >
            <div className="flex items-start justify-between gap-3 mb-3">
              <h3
                className="text-sm font-semibold truncate max-w-[70%]"
                style={{ color: "var(--color-brown-800)" }}
              >
                {c.title || c.case_id.slice(0, 12)}
              </h3>
              <StatusBadge status={c.status} size="sm" />
            </div>
            <div
              className="flex flex-wrap items-center gap-3 text-xs"
              style={{ color: "var(--color-brown-400)" }}
            >
              <span className="inline-flex items-center gap-1">
                <Paperclip size={12} />
                {c.source_file ? 1 : 0} file
                {c.source_file ? "" : "s"}
              </span>
              <span className="inline-flex items-center gap-1">
                <Clock size={12} />
                {new Date(c.created_at).toLocaleDateString(undefined, {
                  month: "short",
                  day: "numeric",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            </div>
          </motion.button>
        ))}
      </div>
    </div>
  );
}
