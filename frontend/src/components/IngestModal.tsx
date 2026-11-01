"use client";

import React, { useState, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  X,
  Upload,
  AlertCircle,
} from "lucide-react";
import { createCaseFromSources } from "@/services/api";
import { RFQCase } from "@/types";
import { suggestCustomerFromEmail } from "@/lib/customer-suggestion";

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
  const [files, setFiles] = useState<File[]>([]);
  const [pasteText, setPasteText] = useState("");
  const [title, setTitle] = useState("");
  const [customer, setCustomer] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sourceCount = files.length + (pasteText.trim() ? 1 : 0);
  const suggestedCustomer = suggestCustomerFromEmail(pasteText);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    setFiles((previous) => [...previous, ...Array.from(e.dataTransfer.files ?? [])].slice(0, 6));
  }, []);

  const handleSubmit = async () => {
    setError(null);
    setSubmitting(true);
    try {
      if (!files.length && !pasteText.trim()) throw new Error("Add an email or at least one attachment.");
      if (sourceCount > 6) throw new Error("An RFQ can contain at most six sources, including pasted email text.");
      if (files.some((file) => file.size > 10 * 1024 * 1024)) throw new Error("Each attachment must be 10 MB or smaller.");
      const totalBytes = files.reduce((total, file) => total + file.size, new TextEncoder().encode(pasteText).byteLength);
      if (totalBytes > 25 * 1024 * 1024) throw new Error("Combined email and attachment size must be 25 MB or smaller.");
      const newCase = await createCaseFromSources(files, pasteText, title || undefined, customer || undefined);
      onCaseCreated(newCase);
      onClose();
      setFiles([]);
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
              <label className="mb-2 block text-sm font-semibold" style={{ color: "var(--color-brown-700)" }} htmlFor="rfq-source-files">Customer email and attachments</label>
              <p className="mb-3 text-xs" style={{ color: "var(--color-brown-400)" }}>Add the email text and up to six files to one RFQ. Each source keeps its own processing status and citation.</p>
              <div
                className={`rounded-xl border-2 border-dashed p-5 text-center cursor-pointer transition-all duration-300 mb-3 ${dragOver ? "scale-[1.01]" : ""}`}
                role="button"
                tabIndex={0}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); fileInputRef.current?.click(); } }}
                aria-label="Choose RFQ attachment files"
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                style={{ borderColor: dragOver ? "var(--color-amber-400)" : "var(--color-sand-300)", backgroundColor: dragOver ? "var(--color-amber-50)" : "var(--color-cream-100)" }}
              >
                <input id="rfq-source-files" ref={fileInputRef} type="file" multiple accept=".pdf,.xlsx,.xls,.csv,.txt" onChange={(event) => { const selectedFiles = Array.from(event.currentTarget.files ?? []); setFiles((previous) => [...previous, ...selectedFiles].slice(0, 6)); }} className="hidden" />
                <Upload size={24} className="mx-auto mb-2" style={{ color: "var(--color-sand-400)" }} />
                <p className="text-sm font-medium" style={{ color: "var(--color-brown-500)" }}>Drop files here or click to browse</p>
                <p className="mt-1 text-xs" style={{ color: "var(--color-brown-300)" }}>PDF, XLSX, XLS, CSV or TXT · maximum 6 sources</p>
              </div>
              {files.length > 0 && <ul className="mb-3 space-y-1" aria-label="Selected attachments">{files.map((file, index) => <li key={`${file.name}-${file.size}-${index}`} className="flex items-center justify-between gap-2 rounded-md bg-white px-3 py-2 text-xs"><span className="truncate">{file.name} · {(file.size / 1024 / 1024).toFixed(2)} MB</span><button type="button" className="underline" onClick={() => setFiles((previous) => previous.filter((_, itemIndex) => itemIndex !== index))} aria-label={`Remove ${file.name}`}>Remove</button></li>)}</ul>}
              <textarea
                placeholder="Optional: paste the customer's email or request text…"
                aria-label="Customer email text"
                value={pasteText}
                onChange={(e) => setPasteText(e.target.value)}
                rows={5}
                className="w-full rounded-xl border p-3 text-sm resize-y outline-none transition-colors duration-200 mb-4 font-mono"
                style={{ borderColor: "var(--color-sand-200)", backgroundColor: "var(--color-cream-100)", color: "var(--color-brown-800)" }}
              />
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

              {/* A source header is a suggestion, never confirmed identity. */}
              <label className="mb-1 block text-xs font-semibold" htmlFor="rfq-customer-label" style={{ color: "var(--color-brown-500)" }}>
                Customer name or company · verify with the request
              </label>
              {suggestedCustomer && suggestedCustomer !== customer && (
                <button type="button" className="mb-2 block rounded-lg border border-[#d6cbbd] bg-white px-3 py-2 text-left text-xs text-[#35484e]"
                  onClick={() => setCustomer(suggestedCustomer)}>
                  Email header suggests <strong>{suggestedCustomer}</strong> · Use this name after checking
                </button>
              )}
              {!customer.trim() && (
                <p className="mb-2 text-xs text-[#78500a]">Customer not verified. The RFQ can be reviewed, but its draft will show Customer not specified.</p>
              )}
              <input
                id="rfq-customer-label"
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
                  (!files.length && !pasteText.trim()) || sourceCount > 6
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
