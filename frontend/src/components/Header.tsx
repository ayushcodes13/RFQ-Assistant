"use client";

import { useState } from "react";
import Image from "next/image";
import { BookOpen, Database, Inbox, Keyboard, Menu, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { RFQCase } from "@/types";

export type AppTab = "inbox" | "workbench" | "catalog" | "updates";

interface HeaderProps {
  currentTab: AppTab;
  onTabChange: (tab: AppTab) => void;
  onOpenShortcuts: () => void;
  cases: RFQCase[];
  sidebarCollapsed: boolean;
  onToggleSidebar: () => void;
}

const navigation = [
  { id: "inbox" as const, label: "RFQ inbox", icon: Inbox },
  { id: "catalog" as const, label: "Catalog", icon: BookOpen },
  { id: "updates" as const, label: "Update data", icon: Database },
];

function ProductMark({ size = 34 }: { size?: number }) {
  return <Image src="/rfq-assistant-mark.svg" alt="" width={size} height={size} aria-hidden="true" />;
}

function NavItems({
  currentTab,
  cases,
  onTabChange,
  onNavigate,
  collapsed = false,
}: {
  currentTab: AppTab;
  cases: RFQCase[];
  onTabChange: (tab: AppTab) => void;
  onNavigate?: () => void;
  collapsed?: boolean;
}) {
  const waitingCount = cases.filter((item) => item.status === "NEEDS_REVIEW").length;
  const activeTab = currentTab === "workbench" ? "inbox" : currentTab;

  return (
    <nav aria-label="Main navigation" className="mt-8">
      {!collapsed && <p className="px-3 pb-2 text-[12px] font-medium text-[var(--color-brown-500)]">Workspace</p>}
      <div className="space-y-1">
        {navigation.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            type="button"
            className="rfq-nav-link"
            title={collapsed ? label : undefined}
            aria-label={collapsed ? label : undefined}
            aria-current={activeTab === id ? "page" : undefined}
            onClick={() => {
              onTabChange(id);
              onNavigate?.();
            }}
          >
            <Icon size={17} strokeWidth={1.7} aria-hidden="true" />
            {!collapsed && <span>{label}</span>}
            {!collapsed && id === "inbox" && waitingCount > 0 && (
              <span className="rfq-nav-count" aria-label={`${waitingCount} cases need review`}>
                {waitingCount}
              </span>
            )}
          </button>
        ))}
      </div>
    </nav>
  );
}

export function Header({ currentTab, onTabChange, onOpenShortcuts, cases, sidebarCollapsed, onToggleSidebar }: HeaderProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <>
      <aside className={`rfq-sidebar${sidebarCollapsed ? " rfq-sidebar-collapsed" : ""}`} aria-label="RFQ Assistant navigation">
        <div className={`flex items-center ${sidebarCollapsed ? "justify-center" : "justify-between"} gap-2 px-2`}>
        <a href="#main-content" className="flex min-w-0 items-center gap-3 no-underline" title={sidebarCollapsed ? "RFQ Assistant" : undefined}>
          <ProductMark />
          {!sidebarCollapsed && <span className="min-w-0">
            <span className="block text-[15px] font-semibold leading-5 text-[#142126]">RFQ Assistant</span>
            <span className="block text-[12px] leading-4 text-[#52656b]">Quotation workspace</span>
          </span>}
        </a>
        <button type="button" className="rfq-collapse-toggle hidden min-[701px]:inline-flex" onClick={onToggleSidebar} aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!sidebarCollapsed} title={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {sidebarCollapsed ? <PanelLeftOpen size={17} aria-hidden="true" /> : <PanelLeftClose size={17} aria-hidden="true" />}
        </button>
        </div>

        <NavItems currentTab={currentTab} cases={cases} onTabChange={onTabChange} collapsed={sidebarCollapsed} />

        <div className="mt-auto border-t border-[#dfe7e9] pt-4">
          <button type="button" className="rfq-nav-link" onClick={onOpenShortcuts} title={sidebarCollapsed ? "Keyboard shortcuts" : undefined} aria-label={sidebarCollapsed ? "Keyboard shortcuts" : undefined}>
            <Keyboard size={16} strokeWidth={1.7} aria-hidden="true" />
            {!sidebarCollapsed && <span>Keyboard shortcuts</span>}
          </button>
          {!sidebarCollapsed && <div className="mt-4 rounded-md border border-[#dfe7e9] bg-[#f8fafb] px-3 py-3">
            <div className="flex items-center gap-2 text-[13px] font-medium text-[#26373d]">
              <span className="size-2 rounded-full bg-[#c64c22]" />
              Local demo
            </div>
            <p className="mt-1 text-[12px] leading-[17px] text-[#52656b]">Files stay in local storage. Quotes are never sent automatically.</p>
          </div>}
        </div>
      </aside>

      <div className="rfq-mobile-topbar">
        <a href="#main-content" className="flex items-center gap-2.5 no-underline">
          <ProductMark size={30} />
          <span className="text-[14px] font-semibold text-[#142126]">RFQ Assistant</span>
        </a>
        <button
          type="button"
          className="rfq-secondary size-10 !p-0"
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={mobileOpen}
          onClick={() => setMobileOpen((value) => !value)}
        >
          {mobileOpen ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-[100] bg-[#142126]/30 md:hidden" onClick={() => setMobileOpen(false)}>
          <div className="h-full w-[min(320px,88vw)] bg-[#f2f6f7] p-4 shadow-xl" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between px-2">
              <div className="flex items-center gap-3"><ProductMark /><span className="font-semibold text-[#142126]">RFQ Assistant</span></div>
              <button type="button" className="rfq-secondary size-10 !p-0" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X size={18} /></button>
            </div>
            <NavItems currentTab={currentTab} cases={cases} onTabChange={onTabChange} onNavigate={() => setMobileOpen(false)} />
            <div className="mt-6 border-t border-[#dfe7e9] pt-3">
              <button type="button" className="rfq-nav-link" onClick={() => { setMobileOpen(false); onOpenShortcuts(); }}><Keyboard size={16} /><span>Keyboard shortcuts</span></button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export function AppTopbar({ currentTab, activeCaseTitle }: { currentTab: AppTab; activeCaseTitle?: string }) {
  const pageLabel = currentTab === "workbench" ? activeCaseTitle || "RFQ review" : currentTab === "inbox" ? "RFQ inbox" : currentTab === "catalog" ? "Catalog" : "Update data";
  return (
    <div className="rfq-topbar">
      <div className="flex min-w-0 items-center gap-2 text-[13px]">
        <span className="shrink-0 text-[#52656b]">Local workspace</span>
        <span aria-hidden="true" className="text-[#91a3a9]">/</span>
        <span className="min-w-0 truncate font-medium text-[#26373d]">{pageLabel}</span>
      </div>
      <span className="hidden items-center gap-2 text-[12px] text-[#52656b] sm:inline-flex">
        <span className="size-1.5 rounded-full bg-[#26704c]" />
        Local storage
      </span>
    </div>
  );
}
