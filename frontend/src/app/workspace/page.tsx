"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Header, AppTopbar, AppTab } from "@/components/Header";
import { OverviewView } from "@/components/OverviewView";
import { InboxView } from "@/components/InboxView";
import { WorkbenchView } from "@/components/WorkbenchView";
import { CatalogView } from "@/components/CatalogView";
import { IngestModal } from "@/components/IngestModal";
import { ExportModal } from "@/components/ExportModal";
import { ShortcutsModal } from "@/components/ShortcutsModal";
import { getCase, listCases } from "@/services/api";
import { RFQCase } from "@/types";

export default function Home() {
  const [currentTab, setCurrentTab] = useState<AppTab>("overview");
  const [cases, setCases] = useState<RFQCase[]>([]);
  const [activeCase, setActiveCase] = useState<RFQCase | null>(null);
  const [loadingCases, setLoadingCases] = useState(true);
  const [casesError, setCasesError] = useState<string | null>(null);
  const [isIngestOpen, setIsIngestOpen] = useState(false);
  const [isExportOpen, setIsExportOpen] = useState(false);
  const [exportSession, setExportSession] = useState(0);
  const [isShortcutsOpen, setIsShortcutsOpen] = useState(false);
  const hasLoadedRef = useRef(false);

  const fetchCases = useCallback(async () => {
    setLoadingCases(!hasLoadedRef.current);
    setCasesError(null);
    try {
      const data = await listCases();
      setCases(data);
      hasLoadedRef.current = true;
      setActiveCase((current) => current ? data.find((item) => item.case_id === current.case_id) ?? current : null);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "The RFQ list could not be loaded.";
      setCasesError(message);
    } finally {
      setLoadingCases(false);
    }
  }, []);

  useEffect(() => {
    void fetchCases();
  }, [fetchCases]);

  // Keep polling the selected case as well as the inbox list. An initial list
  // request can race an upload and return a snapshot from just before that case
  // was created; the selected case must still advance to its persisted result.
  const hasProcessingCases = activeCase?.status === "PROCESSING" || cases.some((item) => item.status === "PROCESSING");
  useEffect(() => {
    if (!hasProcessingCases) return;
    const timer = window.setInterval(() => void fetchCases(), 500);
    return () => window.clearInterval(timer);
  }, [fetchCases, hasProcessingCases]);

  const handleSelectCase = async (caseId: string) => {
    setCasesError(null);
    try {
      const item = await getCase(caseId);
      setActiveCase(item);
      setCurrentTab("workbench");
    } catch (error: unknown) {
      setCasesError(error instanceof Error ? error.message : "This request could not be opened. Refresh and try again.");
    }
  };

  const handleCaseCreated = (created: RFQCase) => {
    setCases((items) => [created, ...items.filter((item) => item.case_id !== created.case_id)]);
    setActiveCase(created);
    setCurrentTab("workbench");
  };

  return (
    <div className="rfq-frame">
      <Header
        currentTab={currentTab}
        onTabChange={setCurrentTab}
        onOpenShortcuts={() => setIsShortcutsOpen(true)}
        cases={cases}
      />
      <div className="rfq-sheet">
        <AppTopbar currentTab={currentTab} activeCaseTitle={activeCase?.title} />
        <main id="main-content" className="min-h-0 flex-1">
          {currentTab === "overview" && (
            <OverviewView
              cases={cases}
              loading={loadingCases}
              error={casesError}
              onOpenNewRfq={() => setIsIngestOpen(true)}
              onOpenInbox={() => setCurrentTab("inbox")}
              onSelectCase={handleSelectCase}
              onRefresh={() => void fetchCases()}
            />
          )}
          {currentTab === "inbox" && (
            <InboxView
              cases={cases}
              loading={loadingCases}
              error={casesError}
              onSelectCase={handleSelectCase}
              onRefresh={() => void fetchCases()}
              onOpenNewRfq={() => setIsIngestOpen(true)}
            />
          )}
          {currentTab === "workbench" && activeCase && (
            <WorkbenchView
              caseData={activeCase}
              onOpenExport={() => {
                setExportSession((session) => session + 1);
                setIsExportOpen(true);
              }}
              onCaseUpdated={fetchCases}
            />
          )}
          {currentTab === "catalog" && <CatalogView />}
        </main>
      </div>

      <IngestModal isOpen={isIngestOpen} onClose={() => setIsIngestOpen(false)} onCaseCreated={handleCaseCreated} />
      {activeCase && (
        <ExportModal
          key={`${activeCase.case_id}-${exportSession}`}
          isOpen={isExportOpen}
          caseData={activeCase}
          onClose={() => {
            setIsExportOpen(false);
            void fetchCases();
          }}
        />
      )}
      <ShortcutsModal isOpen={isShortcutsOpen} onClose={() => setIsShortcutsOpen(false)} />
    </div>
  );
}
