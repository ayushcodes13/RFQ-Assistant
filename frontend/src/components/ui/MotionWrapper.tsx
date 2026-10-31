import React from "react";

interface MotionWrapperProps {
  children: React.ReactNode;
  delay?: number;
  direction?: "up" | "down" | "left" | "right";
  className?: string;
  once?: boolean;
}

/** Retained as a layout wrapper for existing screens; app content does not animate on entry. */
export function MotionWrapper({ children, className = "" }: MotionWrapperProps) {
  return <div className={className}>{children}</div>;
}
