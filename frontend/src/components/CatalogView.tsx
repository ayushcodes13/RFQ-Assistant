"use client";

import React, { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Upload,
  CheckCircle,
  XCircle,
  AlertTriangle,
  FileSpreadsheet,
  Info,
} from "lucide-react";
import { importCatalogCSV } from "@/services/api";
import { CatalogImportSummary } from "@/types";
import { MotionWrapper } from "@/components/ui/MotionWrapper";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

export function CatalogView() {
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState<CatalogImportSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f && f.name.endsWith(".csv")) {
      setFile(f);
      setError(null);
    } else {
      setError("Please upload a .csv file");
    }
  }, []);

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);
    setError(null);
    setResult(null);
    try {
      const res = await importCatalogCSV(file);
      setResult(res.summary);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Import failed";
      setError(msg);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="rfq-content">
      <MotionWrapper direction="up">
        <div className="mb-6">
          <h1 className="rfq-page-title">Catalog</h1>
          <p className="rfq-subtitle">Import and maintain the customer-authorized item master used for exact matching.</p>
        </div>
      </MotionWrapper>

      <MotionWrapper direction="up" className="max-w-[760px]">
        <h2 className="rfq-section-title mb-1">Import a catalog CSV</h2>
        <p className="mb-4 text-[13px] text-[#52656b]">Required columns: Internal SKU, Manufacturer, Manufacturer Part Number. Descriptions do not establish interchangeability.</p>
        {/* Drop zone */}
        <div
          className="relative mb-4 cursor-pointer rounded-md border border-dashed p-8 text-center transition-colors duration-100"
          style={{
            borderColor: dragOver
              ? "var(--color-amber-400)"
              : file
                ? "var(--color-success-500)"
                : "var(--color-sand-400)",
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
          onClick={() => {
            const input = document.getElementById(
              "catalog-file-input"
            ) as HTMLInputElement;
            input?.click();
          }}
          role="button"
          tabIndex={0}
          aria-label="Choose or drop a catalog CSV file"
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") {
              event.preventDefault();
              document.getElementById("catalog-file-input")?.click();
            }
          }}
        >
          <input
            id="catalog-file-input"
            type="file"
            accept=".csv"
            onChange={(e) => {
              setFile(e.target.files?.[0] || null);
              setError(null);
            }}
            className="hidden"
          />

          <AnimatePresence mode="wait">
            {file ? (
              <motion.div
                key="has-file"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
              >
                <CheckCircle
                  size={36}
                  className="mx-auto mb-3"
                  style={{ color: "var(--color-success-500)" }}
                />
                <p
                  className="font-semibold text-sm"
                  style={{ color: "var(--color-success-700)" }}
                >
                  {file.name}
                </p>
                <p
                  className="text-xs mt-1"
                  style={{ color: "var(--color-success-500)" }}
                >
                  Click to change file
                </p>
              </motion.div>
            ) : (
              <motion.div
                key="no-file"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
              >
                <Upload
                  size={23}
                  strokeWidth={1.7}
                  className="mx-auto mb-3"
                  style={{ color: "var(--color-sand-400)" }}
                />
                <p
                  className="font-medium text-sm"
                  style={{ color: "var(--color-brown-500)" }}
                >
                  Drop a CSV file here
                </p>
                <p
                  className="text-xs mt-1"
                  style={{ color: "var(--color-brown-300)" }}
                >
                  or click to browse
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Import button */}
        <div className="mb-6 flex justify-start">
          <button
            onClick={handleImport}
            disabled={!file || importing}
            className="rfq-primary disabled:opacity-50"
            style={{
              backgroundColor: "var(--color-amber-400)",
              color: "var(--color-brown-900)",
            }}
          >
            {importing ? (
              <>
                <LoadingSpinner size="sm" />
                Importing…
              </>
            ) : (
              <>
                <Upload size={16} />
                Import catalog
              </>
            )}
          </button>
        </div>
      </MotionWrapper>

      {/* Error */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="flex items-start gap-3 p-4 rounded-xl border mb-4"
            role="alert"
            style={{
              backgroundColor: "var(--color-error-50)",
              borderColor: "var(--color-error-100)",
              color: "var(--color-error-700)",
            }}
          >
            <XCircle size={18} className="flex-shrink-0 mt-0.5" />
            <p className="text-sm">{error}</p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Result */}
      <AnimatePresence>
        {result && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 12 }}
            className="rounded-xl border p-5"
            style={{
              backgroundColor: "var(--color-success-50)",
              borderColor: "var(--color-success-100)",
            }}
          >
            <h3
              className="text-sm font-semibold mb-3 flex items-center gap-2"
              style={{ color: "var(--color-success-700)" }}
            >
              <CheckCircle size={16} />
              Import results
            </h3>
            <div className="grid grid-cols-3 gap-3">
              <div
                className="text-center rounded-lg p-3"
                style={{ backgroundColor: "rgba(255,255,255,0.6)" }}
              >
                <div
                  className="text-2xl font-bold"
                  style={{ color: "var(--color-success-700)" }}
                >
                  {result.imported}
                </div>
                <div
                  className="text-xs font-medium mt-0.5"
                  style={{ color: "var(--color-success-600)" }}
                >
                  Imported
                </div>
              </div>
              <div
                className="text-center rounded-lg p-3"
                style={{ backgroundColor: "rgba(255,255,255,0.6)" }}
              >
                <div
                  className="text-2xl font-bold"
                  style={{ color: "var(--color-warning-600)" }}
                >
                  {result.duplicates}
                </div>
                <div
                  className="text-xs font-medium mt-0.5"
                  style={{ color: "var(--color-warning-600)" }}
                >
                  Duplicates
                </div>
              </div>
              <div
                className="text-center rounded-lg p-3"
                style={{ backgroundColor: "rgba(255,255,255,0.6)" }}
              >
                <div
                  className="text-2xl font-bold"
                  style={{ color: "var(--color-error-600)" }}
                >
                  {result.collisions}
                </div>
                <div
                  className="text-xs font-medium mt-0.5"
                  style={{ color: "var(--color-error-600)" }}
                >
                  MPN collisions
                </div>
              </div>
            </div>
            <p
              className="text-xs mt-3"
              style={{ color: "var(--color-success-600)" }}
            >
              Catalog now contains {result.total_catalog_size} item
              {result.total_catalog_size === 1 ? "" : "s"}.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
