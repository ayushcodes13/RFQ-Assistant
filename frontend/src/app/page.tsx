"use client";

import React, { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Header } from "@/components/Header";
import { InboxView } from "@/components/InboxView";
import { WorkbenchView } from "@/components/WorkbenchView";
import { CatalogView } from "@/components/CatalogView";
import { IngestModal } from "@/components/IngestModal";
import { ExportModal } from "@/components/ExportModal";
import { ShortcutsModal } from "@/components/ShortcutsModal";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { getCase, listCases } from "@/services/api";
import { RFQCase } from "@/types";

const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
};

export default function Home() {
  const [currentTab, setCurrentTab] = useState<
    "inbox" | "workbench" | "catalog"
  >("inbox");
  const [cases, setCases] = useState<RFQCase[]>([]);
  const [activeCase, setActiveCase] = useState<RFQCase | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [appReady, setAppReady] = useState(false);

  // Modals state
  const [isIngestOpen, setIsIngestOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);

  const fetchCases = async () => {
    setLoadingCases(true);
    try {
      const data = await listCases();
      setCases(data);
      if (activeCase) {
        const updated = data.find(
          (c) => c.case_id === activeCase.case_id
        );
        if (updated) setActiveCase(updated);
      }
    } catch (e: unknown) {
      console.error("Failed to load cases", e);
    } finally {
      setLoadingCases(false);
    }
  };

  useEffect(() => {
    // Simulated app initialization with a brief loading
    const timer = setTimeout(() => {
      setAppReady(true);
      fetchCases();
    }, 600);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSelectCase = async (caseId: string) => {
    try {
      const c = await getCase(caseId);
      setActiveCase(c);
      setCurrentTab("workbench");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Unknown error";
      alert(`Could not open case: ${msg}`);
    }
  };

  const handleCaseCreated = (newCase: RFQCase) => {
    setCases((prev) => [newCase, ...prev]);
    setActiveCase(newCase);
    setCurrentTab("workbench");
  };

  // App loading screen
  if (!appReady) {
    return (
      <div
        className="fixed inset-0 flex flex-col items-center justify-center"
        style={{ backgroundColor: "var(--color-cream-50)" }}
      >
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          className="text-center"
        >
          <h1
            className="text-2xl sm:text-3xl font-bold mb-2 tracking-tight"
            style={{ color: "var(--color-brown-900)" }}
          >
            RFQ Assistant
          </h1>
          <p
            className="text-sm mb-8"
            style={{ color: "var(--color-brown-400)" }}
          >
            Industrial Quotation Preparation Workbench
          </p>
          <LoadingSpinner size="md" />
        </motion.div>
      </div>
    );
  }

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{ backgroundColor: "var(--color-cream-50)" }}
    >
      <Header
        currentTab={currentTab}
        onTabChange={(tab) => setCurrentTab(tab)}
        onOpenNewRfq={() => setIsIngestOpen(true)}
        onOpenShortcuts={() => setIsShortcutsOpen(true)}
        activeCaseId={activeCase?.case_id}
      />

      <main className="flex-1">
        <AnimatePresence mode="wait">
          {currentTab === "inbox" && (
            <motion.div
              key="inbox"
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <InboxView
                cases={cases}
                loading={loadingCases}
                onSelectCase={handleSelectCase}
                onRefresh={fetchCases}
                onOpenNewRfq={() => setIsIngestOpen(true)}
              />
            </motion.div>
          )}

          {currentTab === "workbench" && activeCase && (
            <motion.div
              key="workbench"
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <WorkbenchView
                caseData={activeCase}
                onOpenExport={() => setIsExportOpen(true)}
                onBackToInbox={() => {
                  fetchCases();
                  setCurrentTab("inbox");
                }}
              />
            </motion.div>
          )}

          {currentTab === "catalog" && (
            <motion.div
              key="catalog"
              variants={pageVariants}
              initial="initial"
              animate="animate"
              exit="exit"
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <CatalogView />
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      {/* Footer */}
      <footer
        className="py-4 px-6 text-center border-t"
        style={{
          borderColor: "var(--color-sand-100)",
          color: "var(--color-brown-300)",
        }}
      >
        <p className="text-xs">
          RFQ Assistant · Draft preparation tool · All outputs require
          independent human review
        </p>
      </footer>

      {/* Modals */}
      <IngestModal
        isOpen={isIngestOpen}
        onClose={() => setIsIngestOpen(false)}
        onCaseCreated={handleCaseCreated}
      />

      {activeCase && (
        <ExportModal
          isOpen={isExportOpen}
          caseData={activeCase}
          onClose={() => {
            setIsExportOpen(false);
            fetchCases();
          }}
        />
      )}

      <ShortcutsModal
        isOpen={isShortcutsOpen}
        onClose={() => setIsShortcutsOpen(false)}
      />
    </div>
  );
}
