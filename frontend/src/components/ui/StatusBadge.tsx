interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md";
}

const styles: Record<string, { label: string; color: string; background: string }> = {
  new: { label: "New", color: "#1d465f", background: "#eaf3f8" },
  processing: { label: "Processing", color: "#1d465f", background: "#eaf3f8" },
  needs_review: { label: "Needs review", color: "#694407", background: "#fff5dc" },
  ready_to_export: { label: "Ready", color: "#194f37", background: "#e9f6ee" },
  exported: { label: "Draft prepared", color: "#3d5056", background: "#edf1f2" },
  failed: { label: "Failed", color: "#84241f", background: "#fff0ed" },
  pending: { label: "Pending", color: "#1d465f", background: "#eaf3f8" },
  unreviewed: { label: "Unreviewed", color: "#3d5056", background: "#edf1f2" },
  approved: { label: "Approved", color: "#194f37", background: "#e9f6ee" },
  needs_clarification: { label: "Clarify", color: "#694407", background: "#fff5dc" },
  rejected: { label: "Rejected", color: "#84241f", background: "#fff0ed" },
};

export function StatusBadge({ status, size = "md" }: StatusBadgeProps) {
  const config = styles[status.toLowerCase()] ?? {
    label: status.replaceAll("_", " "),
    color: "#3d5056",
    background: "#edf1f2",
  };
  return (
    <span
      className={`inline-flex flex-none items-center gap-1.5 whitespace-nowrap rounded-[4px] px-2 ${size === "sm" ? "py-0.5 text-[12px]" : "py-1 text-[13px]"} font-medium`}
      style={{ color: config.color, backgroundColor: config.background }}
    >
      <span className="size-1.5 flex-none rounded-full" style={{ backgroundColor: config.color }} aria-hidden="true" />
      {config.label}
    </span>
  );
}
