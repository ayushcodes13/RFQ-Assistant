"use client";

import { useEffect, useRef, useState } from "react";
import { getEmailDraft } from "@/services/api";

type Props = { caseId: string; onClose: () => void };

/** Human-editable copy-only draft. No outbound email capability is exposed. */
export function ClarificationDraftDialog({ caseId, onClose }: Props) {
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(true);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;
    closeRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    void getEmailDraft(caseId)
      .then(({ draft: value }) => { if (active) setDraft(value); })
      .catch((err: unknown) => {
        if (active) setError(err instanceof Error ? err.message : "Draft unavailable");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => {
      active = false;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [caseId, onClose]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
    } catch {
      setError("Clipboard access was blocked. Select the draft text and copy it manually.");
    }
  };

  return (
    <div
      className="fixed inset-0 z-[220] flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="clarification-title"
        className="flex w-full max-w-2xl flex-col gap-3 rounded-2xl bg-white p-5 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3">
          <h2 id="clarification-title" className="text-lg font-semibold">
            Unsent customer clarification
          </h2>
          <button ref={closeRef} type="button" onClick={onClose} aria-label="Close clarification draft" className="rfq-secondary">
            Close
          </button>
        </div>
        <p className="text-sm text-[#6b574d]">
          Review and edit before copying into your own email client. Nothing is sent automatically.
        </p>
        {loading ? (
          <p role="status">Preparing the clarification draft…</p>
        ) : error && !draft ? (
          <p role="alert" className="text-sm text-red-700">{error}</p>
        ) : (
          <>
            <label htmlFor="clarification-body" className="text-sm font-medium">Editable draft text</label>
            <textarea
              id="clarification-body"
              aria-label="Editable clarification draft"
              value={draft}
              onChange={(event) => { setDraft(event.target.value); setCopied(false); }}
              rows={14}
              className="w-full resize-y rounded-lg border border-[#d6cbbd] p-3 font-mono text-sm"
            />
            <div className="flex flex-wrap items-center gap-3">
              <button type="button" className="rfq-primary" disabled={!draft.trim()} onClick={() => { void handleCopy(); }}>
                Copy edited draft
              </button>
              {copied && <span role="status" className="text-sm">Copied. Review recipients manually before sending.</span>}
              {error && <span role="alert" className="text-sm text-red-700">{error}</span>}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
