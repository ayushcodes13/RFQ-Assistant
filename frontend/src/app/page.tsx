"use client";

import React, { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { InboxView } from "@/components/InboxView";
import { WorkbenchView } from "@/components/WorkbenchView";
import { CatalogView } from "@/components/CatalogView";
import { IngestModal } from "@/components/IngestModal";
import { ExportModal } from "@/components/ExportModal";
import { ShortcutsModal } from "@/components/ShortcutsModal";
import { getCase, listCases } from "@/services/api";
import { RFQCase } from "@/types";

export default function Home() {
  const [currentTab, setCurrentTab] = useState<"inbox" | "workbench" | "catalog">("inbox");
  const [cases, setCases] = useState<RFQCase[]>([]);
  const [activeCase, setActiveCase] = useState<RFQCase | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);

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
        // Refresh active case data if still present
        const updated = data.find((c) => c.case_id === activeCase.case_id);
        if (updated) setActiveCase(updated);
      }
    } catch (e: any) {
      console.error("Failed to load cases", e);
    } finally {
      setLoadingCases(false);
    }
  };

  useEffect(() => {
    fetchCases();
  }, []);

  const handleSelectCase = async (caseId: string) => {
    try {
      const c = await getCase(caseId);
      setActiveCase(c);
      setCurrentTab("workbench");
    } catch (e: any) {
      alert(`Could not open case: ${e.message}`);
    }
  };

  const handleCaseCreated = (newCase: RFQCase) => {
    setCases((prev) => [newCase, ...prev]);
    setActiveCase(newCase);
    setCurrentTab("workbench");
  };

  return (
    <div className="app-container">
      <Header
        currentTab={currentTab}
        onTabChange={(tab) => setCurrentTab(tab)}
        onOpenNewRfq={() => setIsIngestOpen(true)}
        onOpenShortcuts={() => setIsShortcutsOpen(true)}
        activeCaseId={activeCase?.case_id}
      />

      <main className="main-content">
        {currentTab === "inbox" && (
          <InboxView
            cases={cases}
            loading={loadingCases}
            onSelectCase={handleSelectCase}
            onRefresh={fetchCases}
            onOpenNewRfq={() => setIsIngestOpen(true)}
          />
        )}

        {currentTab === "workbench" && activeCase && (
          <WorkbenchView
            caseData={activeCase}
            onOpenExport={() => setIsExportOpen(true)}
            onBackToInbox={() => {
              fetchCases();
              setCurrentTab("inbox");
            }}
          />
        )}

        {currentTab === "catalog" && <CatalogView />}
      </main>

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

      <style jsx>{`
        .app-container {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
        }
        .main-content {
          flex: 1;
        }
      `}</style>
    </div>
  );
}
