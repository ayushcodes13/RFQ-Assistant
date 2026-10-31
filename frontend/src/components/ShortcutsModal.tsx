"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Keyboard } from "lucide-react";

interface ShortcutsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const shortcuts = [
  { keys: "Tab", action: "Navigate between cells" },
  { keys: "Enter", action: "Confirm cell edit" },
  { keys: "Escape", action: "Cancel edit / close modal" },
  { keys: "Ctrl/⌘ + F", action: "Search extracted rows" },
  { keys: "Double-click", action: "Edit a cell value" },
];

export function ShortcutsModal({ isOpen, onClose }: ShortcutsModalProps) {
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
            className="w-full max-w-sm rounded-2xl overflow-hidden shadow-xl"
            style={{
              backgroundColor: "var(--color-cream-50)",
              border: "1px solid var(--color-sand-200)",
            }}
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-label="Keyboard shortcuts"
          >
            {/* Header */}
            <div
              className="flex items-center justify-between px-5 py-4 border-b"
              style={{ borderColor: "var(--color-sand-200)" }}
            >
              <h2
                className="text-lg font-bold flex items-center gap-2"
                style={{ color: "var(--color-brown-800)" }}
              >
                <Keyboard size={20} />
                Shortcuts
              </h2>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg transition-colors duration-200"
                style={{ color: "var(--color-brown-300)" }}
                aria-label="Close"
              >
                <X size={18} />
              </button>
            </div>

            {/* Body */}
            <div className="px-5 py-4">
              <div className="space-y-0">
                {shortcuts.map((s, i) => (
                  <motion.div
                    key={s.keys}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{
                      delay: i * 0.05,
                      duration: 0.3,
                      ease: [0.16, 1, 0.3, 1],
                    }}
                    className="flex items-center justify-between py-3 border-b last:border-b-0"
                    style={{ borderColor: "var(--color-sand-100)" }}
                  >
                    <span
                      className="text-sm"
                      style={{ color: "var(--color-brown-600)" }}
                    >
                      {s.action}
                    </span>
                    <kbd
                      className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-mono font-medium border"
                      style={{
                        backgroundColor: "var(--color-sand-50)",
                        borderColor: "var(--color-sand-200)",
                        color: "var(--color-brown-600)",
                      }}
                    >
                      {s.keys}
                    </kbd>
                  </motion.div>
                ))}
              </div>
            </div>

            {/* Footer */}
            <div
              className="flex justify-end px-5 py-4 border-t"
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
                Close
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
