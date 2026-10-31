import { Check, Circle, LoaderCircle } from "lucide-react";
import type { RFQCase } from "@/types";

const stages = [
  { id: "QUEUED", label: "Upload received" },
  { id: "VALIDATING", label: "Validating document" },
  { id: "EXTRACTING", label: "Extracting line items" },
  { id: "CHECKING_FIELDS", label: "Checking missing fields" },
  { id: "MATCHING", label: "Matching catalog" },
] as const;

const labels: Record<string, string> = {
  QUEUED: "Upload received",
  VALIDATING: "Validating document",
  EXTRACTING: "Extracting line items",
  CHECKING_FIELDS: "Checking missing fields",
  MATCHING: "Matching catalog",
  READY_FOR_REVIEW: "Ready for review",
  FAILED: "Processing needs attention",
};

export function processingStageLabel(stage: RFQCase["processing_stage"]) {
  return stage ? labels[stage] ?? "Processing" : "Processing queued work";
}

export function ProcessingProgress({ caseData }: { caseData: RFQCase }) {
  const currentIndex = stages.findIndex((stage) => stage.id === caseData.processing_stage);
  const failed = caseData.processing_stage === "FAILED" || caseData.status === "FAILED";

  return (
    <section
      className={`rounded-lg border px-4 py-3 ${failed ? "border-[#f0c7c1] bg-[#fff7f5]" : "border-[#cbd6d9] bg-white"}`}
      aria-label="Document processing progress"
      aria-live="polite"
    >
      <p className={`text-sm font-semibold ${failed ? "text-[#84241f]" : "text-[#1d2b30]"}`}>
        {processingStageLabel(caseData.processing_stage)}
      </p>
      {!failed && (
        <ol className="mt-3 grid gap-2 sm:grid-cols-5" aria-label="Processing stages">
          {stages.map((stage, index) => {
            const complete = currentIndex > index || caseData.processing_stage === "READY_FOR_REVIEW";
            const current = index === currentIndex;
            return (
              <li
                key={stage.id}
                className={`flex items-center gap-2 text-xs ${current ? "font-semibold text-[#1d465f]" : complete ? "text-[#42624f]" : "text-[#667980]"}`}
                aria-current={current ? "step" : undefined}
              >
                {complete ? <Check size={14} aria-hidden="true" /> : current ? <LoaderCircle size={14} className="animate-spin" aria-hidden="true" /> : <Circle size={14} aria-hidden="true" />}
                <span>{stage.label}</span>
              </li>
            );
          })}
        </ol>
      )}
      {failed && (
        <p className="mt-1 text-sm text-[#84241f]">
          The original upload is retained. Review the processing warning below, then correct the file and upload it again or use manual entry.
        </p>
      )}
    </section>
  );
}
