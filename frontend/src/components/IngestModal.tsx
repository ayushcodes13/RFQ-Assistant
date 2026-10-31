"use client";

import React, { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Upload,
  FileText,
  CheckCircle,
  AlertCircle,
} from "lucide-react";
import { createCaseFromText, createCaseFromUpload } from "@/services/api";
import { RFQCase } from "@/types";

interface IngestModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCaseCreated: (newCase: RFQCase) => void;
}

export function IngestModal({
  isOpen,
  onClose,
  onCaseCreated,
}: IngestModalProps) {
  const [mode, setMode] = useState<"file" | "paste">("file");
  const [file, setFile] = useState<File | null>(null);
  const [pasteText, setPasteText] = useState("");
  const [title, setTitle] = useState("");
  const [customer, setCustomer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) {
      setFile(f);
      setMode("file");
    }
  }, []);

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      let newCase: RFQCase;
      if (mode === "file" && file) {
        newCase = await createCaseFromUpload(
          file,
          title || undefined,
          customer || undefined
        );
      } else if (mode === "paste" && pasteText.trim()) {
        newCase = await createCaseFromText(
          pasteText,
          title || undefined,
          customer || undefined
        );
      } else {
        throw new Error("Please provide a file or paste text.");
      }
      onCaseCreated(newCase);
      onClose();
      setFile(null);
      setPasteText("");
      setTitle("");
      setCustomer("");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Submission failed";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="fixed inset-0 z-[200] flex items-center justify-center p-4"
          style={{ backgroundColor: "rgba(42, 35, 24, 0.4)" }}
          onClick={onClose}
        >
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            transition={{
              duration: 0.35,
              ease: [0.16, 1, 0.3, 1],
            }}
            className="w-full max-w-lg rounded-2xl overflow-hidden shadow-xl"
            style={{
              backgroundColor: "var(--color-cream-50)",
              border: "1px solid var(--color-sand-200)",
            }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-label="New RFQ"
          >
            {/* Header */}
            <div
              className="flex items-center justify-between px-5 py-4 border-b"
              style={{ borderColor: "var(--color-sand-200)" }}
            >
              <h2
                className="text-lg font-bold"
                style={{ color: "var(--color-brown-800)" }}
              >
                New RFQ
              </h2>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg transition-colors duration-200"
                style={{ color: "var(--color-brown-300)" }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor =
                    "var(--color-sand-100)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor =
                    "transparent";
                }}
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="px-5 py-5">
              {/* Mode toggle */}
              <div
                className="flex rounded-lg p-1 mb-5"
                style={{ backgroundColor: "var(--color-sand-100)" }}
              >
                <button
                  onClick={() => setMode("file")}
                  className="flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm font-medium transition-all duration-200"
                  style={{
                    backgroundColor:
                      mode === "file"
                        ? "var(--color-cream-50)"
                        : "transparent",
                    color:
                      mode === "file"
                        ? "var(--color-brown-800)"
                        : "var(--color-brown-400)",
                    boxShadow:
                      mode === "file"
                        ? "0 1px 3px rgba(139,115,85,0.08)"
                        : "none",
                  }}
                >
                  <Upload size={15} />
                  Upload file
                </button>
                <button
                  onClick={() => setMode("paste")}
                  className="flex-1 flex items-center justify-center gap-2 py-2 rounded-md text-sm font-medium transition-all duration-200"
                  style={{
                    backgroundColor:
                      mode === "paste"
                        ? "var(--color-cream-50)"
                        : "transparent",
                    color:
                      mode === "paste"
                        ? "var(--color-brown-800)"
                        : "var(--color-brown-400)",
                    boxShadow:
                      mode === "paste"
                        ? "0 1px 3px rgba(139,115,85,0.08)"
                        : "none",
                  }}
                >
                  <FileText size={15} />
                  Paste text
                </button>
              </div>

              {/* File Upload */}
              {mode === "file" && (
                <div
                  className={`rounded-xl border-2 border-dashed p-6 text-center cursor-pointer transition-all duration-300 mb-4 ${
                    dragOver ? "scale-[1.01]" : ""
                  }`}
                  style={{
                    borderColor: dragOver
                      ? "var(--color-amber-400)"
                      : file
                        ? "var(--color-success-500)"
                        : "var(--color-sand-300)",
                    backgroundColor: dragOver
                      ? "var(--color-amber-50)"
                      : file
                        ? "var(--color-success-50)"
                        : "var(--color-cream-100)",
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragOver(true);
                  }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={handleDrop}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".pdf,.xlsx,.xls,.csv,.txt"
                    onChange={(e) =>
                      setFile(e.target.files?.[0] || null)
                    }
                    className="hidden"
                  />
                  <AnimatePresence mode="wait">
                    {file ? (
                      <motion.div
                        key="has-file"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                      >
                        <CheckCircle
                          size={28}
                          className="mx-auto mb-2"
                          style={{
                            color: "var(--color-success-500)",
                          }}
                        />
                        <p
                          className="text-sm font-semibold"
                          style={{
                            color: "var(--color-success-700)",
                          }}
                        >
                          {file.name}
                        </p>
                      </motion.div>
                    ) : (
                      <motion.div
                        key="no-file"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                      >
                        <Upload
                          size={28}
                          className="mx-auto mb-2"
                          style={{
                            color: "var(--color-sand-400)",
                          }}
                        />
                        <p
                          className="text-sm font-medium"
                          style={{
                            color: "var(--color-brown-500)",
                          }}
                        >
                          Drop PDF, XLSX or CSV here
                        </p>
                        <p
                          className="text-xs mt-1"
                          style={{
                            color: "var(--color-brown-300)",
                          }}
                        >
                          or click to browse
                        </p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}

              {/* Text Paste */}
              {mode === "paste" && (
                <textarea
                  placeholder="Paste email or RFQ text here…"
                  value={pasteText}
                  onChange={(e) => setPasteText(e.target.value)}
                  rows={7}
                  className="w-full rounded-xl border p-3 text-sm resize-y outline-none transition-colors duration-200 mb-4 font-mono"
                  style={{
                    borderColor: "var(--color-sand-200)",
                    backgroundColor: "var(--color-cream-100)",
                    color: "var(--color-brown-800)",
                  }}
                  onFocus={(e) => {
                    e.currentTarget.style.borderColor =
                      "var(--color-amber-300)";
                  }}
                  onBlur={(e) => {
                    e.currentTarget.style.borderColor =
                      "var(--color-sand-200)";
                  }}
                />
              )}

              {/* Optional title */}
              <input
                type="text"
                placeholder="Optional case title"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm outline-none transition-colors duration-200 mb-4"
                style={{
                  borderColor: "var(--color-sand-200)",
                  backgroundColor: "var(--color-cream-100)",
                  color: "var(--color-brown-800)",
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor =
                    "var(--color-amber-300)";
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor =
                    "var(--color-sand-200)";
                }}
              />

              {/* Optional customer label */}
              <input
                type="text"
                placeholder="Optional customer label"
                value={customer}
                onChange={(e) => setCustomer(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm outline-none transition-colors duration-200 mb-4"
                style={{
                  borderColor: "var(--color-sand-200)",
                  backgroundColor: "var(--color-cream-100)",
                  color: "var(--color-brown-800)",
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor =
                    "var(--color-amber-300)";
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor =
                    "var(--color-sand-200)";
                }}
              />

              {/* Error */}
              <AnimatePresence>
                {error && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex items-start gap-2 p-3 rounded-lg mb-3"
                    role="alert"
                    style={{
                      backgroundColor: "var(--color-error-50)",
                      color: "var(--color-error-700)",
                    }}
                  >
                    <AlertCircle
                      size={16}
                      className="flex-shrink-0 mt-0.5"
                    />
                    <p className="text-xs">{error}</p>
                  </motion.div>
                )}
              </AnimatePresence>

              <p
                className="text-[11px] leading-relaxed"
                style={{ color: "var(--color-brown-300)" }}
              >
                Uploaded files are stored locally for processing. Review
                our data handling practices.
              </p>
            </div>

            {/* Footer */}
            <div
              className="flex justify-end gap-2.5 px-5 py-4 border-t"
              style={{ borderColor: "var(--color-sand-200)" }}
            >
              <button
                onClick={onClose}
                className="px-4 py-2 rounded-lg text-sm font-medium border transition-all duration-200"
                style={{
                  color: "var(--color-brown-500)",
                  borderColor: "var(--color-sand-200)",
                  backgroundColor: "var(--color-cream-100)",
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSubmit}
                disabled={
                  submitting ||
                  (mode === "file" && !file) ||
                  (mode === "paste" && !pasteText.trim())
                }
                className="px-5 py-2 rounded-lg text-sm font-semibold transition-all duration-200 hover:shadow-md active:scale-[0.97] disabled:opacity-40 disabled:cursor-not-allowed"
                style={{
                  backgroundColor: "var(--color-amber-400)",
                  color: "var(--color-brown-900)",
                }}
              >
                {submitting ? "Processing…" : "Extract line items"}
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
