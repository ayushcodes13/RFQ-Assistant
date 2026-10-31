"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Inbox,
  Wrench,
  BookOpen,
  Plus,
  Keyboard,
  Menu,
  X,
} from "lucide-react";

interface HeaderProps {
  currentTab: "inbox" | "workbench" | "catalog";
  onTabChange: (tab: "inbox" | "workbench" | "catalog") => void;
  onOpenNewRfq: () => void;
  onOpenShortcuts: () => void;
  activeCaseId?: string;
}

const tabs = [
  { id: "inbox" as const, label: "RFQs", icon: Inbox },
  { id: "workbench" as const, label: "Workbench", icon: Wrench },
  { id: "catalog" as const, label: "Catalog", icon: BookOpen },
];

export function Header({
  currentTab,
  onTabChange,
  onOpenNewRfq,
  onOpenShortcuts,
  activeCaseId,
}: HeaderProps) {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <motion.header
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      className="sticky top-0 z-50 border-b"
      style={{
        background: "rgba(255, 253, 247, 0.88)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        borderColor: "var(--color-sand-200)",
      }}
    >
      <div className="mx-auto max-w-7xl px-4 sm:px-6">
        <div className="flex h-14 sm:h-16 items-center justify-between">
          {/* Left: Logo */}
          <div className="flex items-center gap-2.5 flex-shrink-0">
            <h1
              className="text-base sm:text-lg font-bold tracking-tight"
              style={{ color: "var(--color-brown-900)" }}
            >
              RFQ Assistant
            </h1>
            <span
              className="hidden sm:inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider border"
              style={{
                color: "var(--color-amber-700)",
                backgroundColor: "var(--color-amber-50)",
                borderColor: "var(--color-amber-200)",
              }}
            >
              Demo
            </span>
          </div>

          {/* Center: Desktop Nav */}
          <nav
            className="hidden md:flex items-center gap-1"
            role="navigation"
            aria-label="Main navigation"
          >
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = currentTab === tab.id;
              const isDisabled = tab.id === "workbench" && !activeCaseId;

              return (
                <button
                  key={tab.id}
                  onClick={() => !isDisabled && onTabChange(tab.id)}
                  disabled={isDisabled}
                  aria-current={isActive ? "page" : undefined}
                  title={
                    isDisabled ? "Open an RFQ case first" : undefined
                  }
                  className="relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors duration-200 disabled:opacity-35 disabled:cursor-not-allowed"
                  style={{
                    color: isActive
                      ? "var(--color-amber-700)"
                      : "var(--color-brown-400)",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive && !isDisabled) {
                      e.currentTarget.style.color =
                        "var(--color-brown-700)";
                      e.currentTarget.style.backgroundColor =
                        "var(--color-sand-100)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      e.currentTarget.style.color =
                        "var(--color-brown-400)";
                      e.currentTarget.style.backgroundColor =
                        "transparent";
                    }
                  }}
                >
                  <Icon size={16} />
                  <span>{tab.label}</span>
                  {isActive && (
                    <motion.div
                      layoutId="activeTab"
                      className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full"
                      style={{
                        backgroundColor: "var(--color-amber-400)",
                      }}
                      transition={{
                        type: "spring",
                        stiffness: 380,
                        damping: 30,
                      }}
                    />
                  )}
                </button>
              );
            })}
          </nav>

          {/* Right: Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={onOpenNewRfq}
              className="hidden sm:inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold transition-all duration-200 hover:shadow-md active:scale-[0.97]"
              style={{
                backgroundColor: "var(--color-amber-400)",
                color: "var(--color-brown-900)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor =
                  "var(--color-amber-500)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor =
                  "var(--color-amber-400)";
              }}
            >
              <Plus size={16} />
              New RFQ
            </button>
            <button
              onClick={onOpenShortcuts}
              className="hidden sm:flex items-center justify-center w-9 h-9 rounded-lg transition-colors duration-200"
              style={{ color: "var(--color-brown-400)" }}
              onMouseEnter={(e) => {
                e.currentTarget.style.backgroundColor =
                  "var(--color-sand-100)";
                e.currentTarget.style.color = "var(--color-brown-700)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.backgroundColor = "transparent";
                e.currentTarget.style.color = "var(--color-brown-400)";
              }}
              title="Keyboard shortcuts"
              aria-label="Keyboard shortcuts"
            >
              <Keyboard size={18} />
            </button>

            {/* Mobile menu button */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="md:hidden flex items-center justify-center w-9 h-9 rounded-lg transition-colors duration-200"
              style={{ color: "var(--color-brown-500)" }}
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <X size={20} /> : <Menu size={20} />}
            </button>
          </div>
        </div>
      </div>

      {/* Mobile Menu */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            className="md:hidden overflow-hidden border-t"
            style={{
              borderColor: "var(--color-sand-200)",
              backgroundColor: "var(--color-cream-50)",
            }}
          >
            <div className="px-4 py-3 space-y-1">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = currentTab === tab.id;
                const isDisabled =
                  tab.id === "workbench" && !activeCaseId;

                return (
                  <button
                    key={tab.id}
                    onClick={() => {
                      if (!isDisabled) {
                        onTabChange(tab.id);
                        setMobileMenuOpen(false);
                      }
                    }}
                    disabled={isDisabled}
                    className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium transition-colors duration-200 disabled:opacity-35"
                    style={{
                      color: isActive
                        ? "var(--color-amber-700)"
                        : "var(--color-brown-500)",
                      backgroundColor: isActive
                        ? "var(--color-amber-50)"
                        : "transparent",
                    }}
                  >
                    <Icon size={18} />
                    {tab.label}
                  </button>
                );
              })}
              <div
                className="border-t my-2"
                style={{ borderColor: "var(--color-sand-200)" }}
              />
              <button
                onClick={() => {
                  onOpenNewRfq();
                  setMobileMenuOpen(false);
                }}
                className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-semibold"
                style={{
                  backgroundColor: "var(--color-amber-400)",
                  color: "var(--color-brown-900)",
                }}
              >
                <Plus size={18} />
                New RFQ
              </button>
              <button
                onClick={() => {
                  onOpenShortcuts();
                  setMobileMenuOpen(false);
                }}
                className="flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm font-medium"
                style={{ color: "var(--color-brown-400)" }}
              >
                <Keyboard size={18} />
                Keyboard shortcuts
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.header>
  );
}
