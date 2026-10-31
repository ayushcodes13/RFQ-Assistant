"use client";

import React from "react";
import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";

interface LoadingSpinnerProps {
  message?: string;
  size?: "sm" | "md" | "lg";
}

const sizes = {
  sm: { icon: 20, dots: 4, text: "text-xs" },
  md: { icon: 32, dots: 6, text: "text-sm" },
  lg: { icon: 48, dots: 8, text: "text-base" },
};

export function LoadingSpinner({ message, size = "md" }: LoadingSpinnerProps) {
  const s = sizes[size];

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="flex flex-col items-center justify-center gap-4 py-12"
    >
      <div className="relative">
        <Loader2
          size={s.icon}
          className="animate-spin-slow"
          style={{ color: "var(--color-amber-400)" }}
        />
      </div>

      {/* Pulsing dots */}
      <div className="flex items-center gap-1.5">
        {[0, 1, 2].map((i) => (
          <motion.div
            key={i}
            className="rounded-full"
            style={{
              width: s.dots,
              height: s.dots,
              backgroundColor: "var(--color-sand-400)",
            }}
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{
              duration: 1.4,
              repeat: Infinity,
              delay: i * 0.2,
              ease: "easeInOut",
            }}
          />
        ))}
      </div>

      {message && (
        <p
          className={`${s.text} font-medium`}
          style={{ color: "var(--color-brown-400)" }}
        >
          {message}
        </p>
      )}
    </motion.div>
  );
}
