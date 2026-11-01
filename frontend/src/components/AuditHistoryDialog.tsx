"use client";

import { useEffect, useRef, useState } from "react";
import { getAuditTrail } from "@/services/api";
import type { AuditEvent } from "@/types";

type Props = { caseId: string; onClose: () => void };

export function AuditHistoryDialog({ caseId, onClose }: Props) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    let active = true;
    closeRef.current?.focus();
    const keyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", keyDown);
    void getAuditTrail(caseId)
      .then((items) => { if (active) setEvents(items.slice().reverse()); })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : "Unable to load activity history");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => {
      active = false;
      document.removeEventListener("keydown", keyDown);
    };
  }, [caseId]);

  return (
    <div className="fixed inset-0 z-[230] flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
      <section
        role="dialog" aria-modal="true" aria-labelledby="history-title"
        className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-3 rounded-xl bg-white p-5 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3">
          <h2 id="history-title" className="text-lg font-semibold">RFQ activity history</h2>
          <button type="button" ref={closeRef} className="rfq-secondary" onClick={onClose}>Close</button>
        </div>
        <p className="text-sm text-[#52656b]">Recorded case changes, reviewer decisions and export events. These are audit records, not proof that a document is correct.</p>
        {loading ? <p role="status">Loading recorded activity…</p>
          : error ? <p role="alert" className="text-sm text-red-700">{error}</p>
          : events.length === 0 ? <p role="status">No activity has been recorded for this RFQ.</p>
          : (
            <ol aria-label="Recorded RFQ events" className="min-h-0 space-y-3 overflow-y-auto pr-1">
              {events.map((event) => (
                <li key={event.event_id} className="rounded-lg border border-[#e0d9d0] p-3 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <strong className="font-semibold">{event.action.replaceAll("_", " ")}</strong>
                    <time dateTime={event.recorded_at ?? undefined} className="text-xs text-[#52656b]">
                      {event.recorded_at ? new Date(event.recorded_at).toLocaleString() : "Timestamp unavailable"}
                    </time>
                  </div>
                  <p className="mt-1 text-[#52656b]">By {event.actor || "Unknown operator"}{event.line_id ? ` · ${event.line_id}` : ""}</p>
                  {event.field_name && <p className="mt-1">Field: {event.field_name}</p>}
                  {(event.old_value != null || event.new_value != null) && (
                    <p className="mt-1 break-words text-xs">
                      Previous: {event.old_value ?? "(empty)"} · New: {event.new_value ?? "(empty)"}
                    </p>
                  )}
                  {event.notes && <p className="mt-1 break-words text-xs text-[#52656b]">{event.notes}</p>}
                </li>
              ))}
            </ol>
          )}
      </section>
    </div>
  );
}
