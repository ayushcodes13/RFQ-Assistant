"use client";

import React, { useEffect, useState } from "react";
import {
  AuditEvent,
  MatchCandidate,
  RFQCase,
  RFQLineItem,
  ReviewDecision,
} from "@/types";
import { StatusBadge } from "@/components/StatusBadge";
import {
  batchReviewLines,
  getAuditTrail,
  getCaseLines,
  updateLineItem,
} from "@/services/api";

interface WorkbenchViewProps {
  caseData: RFQCase;
  onOpenExport: () => void;
  onBackToInbox: () => void;
}

export function WorkbenchView({
  caseData,
  onOpenExport,
  onBackToInbox,
}: WorkbenchViewProps) {
  const [lines, setLines] = useState<RFQLineItem[]>([]);
  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<"ALL" | "ACTION_REQUIRED" | "EXACT" | "APPROVED">("ALL");
  const [loading, setLoading] = useState(true);
  const [savingLine, setSavingLine] = useState(false);
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [showAuditDrawer, setShowAuditDrawer] = useState(false);
  const [reviewerNote, setReviewerNote] = useState("");

  const loadData = async () => {
    setLoading(true);
    try {
      const items = await getCaseLines(caseData.case_id);
      setLines(items);
      if (items.length > 0 && !selectedLineId) {
        setSelectedLineId(items[0].line_id);
      }
      const audits = await getAuditTrail(caseData.case_id);
      setAuditEvents(audits);
    } catch (e: any) {
      console.error("Failed to load lines", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [caseData.case_id]);

  const selectedLine = lines.find((l) => l.line_id === selectedLineId);

  useEffect(() => {
    if (selectedLine) {
      setReviewerNote(selectedLine.reviewer_notes || "");
    }
  }, [selectedLineId]);

  // Handle single line field updates
  const handleQuickUpdate = async (lineId: string, updates: Partial<RFQLineItem>) => {
    setSavingLine(true);
    try {
      const updated = await updateLineItem(caseData.case_id, lineId, updates);
      setLines((prev) => prev.map((l) => (l.line_id === lineId ? updated : l)));
      const audits = await getAuditTrail(caseData.case_id);
      setAuditEvents(audits);
    } catch (err: any) {
      alert(`Update failed: ${err.message}`);
    } finally {
      setSavingLine(false);
    }
  };

  // Batch approve all visible exact matches
  const handleBatchApproveExact = async () => {
    const exactLines = lines.filter(
      (l) => l.match_status === "EXACT_MATCH" && l.quantity !== null && l.review_decision !== "APPROVED"
    );
    if (exactLines.length === 0) {
      alert("No pending exact matches with valid quantities to approve.");
      return;
    }

    if (
      confirm(
        `Approve ${exactLines.length} exact catalog matches? Staff remains responsible for quote accuracy.`
      )
    ) {
      try {
        const ids = exactLines.map((l) => l.line_id);
        await batchReviewLines(caseData.case_id, ids, "APPROVED", "Inside Sales", "Batch approved exact matches");
        loadData();
      } catch (err: any) {
        alert(err.message);
      }
    }
  };

  // Filter lines
  const filteredLines = lines.filter((l) => {
    if (filterMode === "ACTION_REQUIRED") {
      return (
        l.quantity === null ||
        l.match_status === "COLLISION" ||
        l.match_status === "NO_MATCH" ||
        l.review_decision === "NEEDS_CLARIFICATION" ||
        l.review_decision === "PENDING"
      );
    }
    if (filterMode === "EXACT") {
      return l.match_status === "EXACT_MATCH";
    }
    if (filterMode === "APPROVED") {
      return l.review_decision === "APPROVED";
    }
    return true;
  });

  const unresolvedCount = lines.filter(
    (l) =>
      l.quantity === null ||
      (l.match_status !== "EXACT_MATCH" && l.match_status !== "MANUAL_OVERRIDE") ||
      l.review_decision !== "APPROVED"
  ).length;

  return (
    <div className="workbench-layout">
      {/* Workbench Header */}
      <div className="workbench-header">
        <div className="header-meta">
          <button className="back-link" onClick={onBackToInbox}>
            ← Cases Inbox
          </button>
          <div className="title-row">
            <h1 className="case-title font-mono">{caseData.case_id}</h1>
            <StatusBadge type="case" value={caseData.status} />
            <span className="case-name">{caseData.title}</span>
            {caseData.customer_label && (
              <span className="customer-tag">{caseData.customer_label}</span>
            )}
          </div>
        </div>

        <div className="header-actions">
          <div className="counters-box">
            <span className="count-label">Total Lines:</span>
            <strong>{lines.length}</strong>
            <span className="divider">|</span>
            <span className="count-label">Unresolved:</span>
            <strong className={unresolvedCount > 0 ? "text-amber" : "text-emerald"}>
              {unresolvedCount}
            </strong>
          </div>

          <button
            className="secondary-btn"
            onClick={() => setShowAuditDrawer(!showAuditDrawer)}
            title="Inspect audit history"
          >
            📋 Audit Log ({auditEvents.length})
          </button>

          <button
            className={`export-btn ${unresolvedCount > 0 ? "has-unresolved" : "ready"}`}
            onClick={onOpenExport}
          >
            Export Quotation Worksheet →
          </button>
        </div>
      </div>

      {/* Main Split Panels */}
      <div className="split-workspace">
        {/* Left Panel: ORIGINAL SOURCE DOCUMENT INSPECTOR */}
        <aside className="source-panel">
          <div className="panel-header">
            <div className="panel-title">ORIGINAL SOURCE EVIDENCE</div>
            <span className="badge-source">
              {caseData.source_file ? caseData.source_file.source_type : "EMAIL_TEXT"}
            </span>
          </div>

          <div className="file-info-card">
            <div className="info-row">
              <span className="info-label">File:</span>
              <strong className="info-val font-mono">
                {caseData.source_file ? caseData.source_file.file_name : "pasted_inquiry.txt"}
              </strong>
            </div>
            {caseData.source_file && (
              <div className="info-row">
                <span className="info-label">SHA-256 Digest:</span>
                <span className="info-val font-mono font-xs">
                  {caseData.source_file.sha256_digest.slice(0, 16)}...
                </span>
              </div>
            )}
          </div>

          {selectedLine ? (
            <div className="selected-locator-box">
              <div className="locator-header">
                <span>📍 Source Pinpoint for Line #{selectedLine.line_number}</span>
                <span className="locator-coord font-mono">
                  {selectedLine.source_locator.sheet_name
                    ? `Sheet: ${selectedLine.source_locator.sheet_name}`
                    : ""}
                  {selectedLine.source_locator.page_number
                    ? `Page: ${selectedLine.source_locator.page_number}`
                    : ""}
                  {selectedLine.source_locator.row_number
                    ? ` | Row: ${selectedLine.source_locator.row_number}`
                    : ""}
                </span>
              </div>

              <div className="raw-snippet-container">
                <div className="snippet-title">Extracted Raw Text Snippet:</div>
                <div className="raw-snippet-box font-mono">
                  {selectedLine.source_locator.text_snippet || selectedLine.raw_text}
                </div>
              </div>

              {selectedLine.extraction_warnings.length > 0 && (
                <div className="warnings-container">
                  <div className="warning-heading">Extraction Warnings:</div>
                  {selectedLine.extraction_warnings.map((w, idx) => (
                    <div key={idx} className="warning-item">
                      ⚠ <strong>[{w.code}]:</strong> {w.message}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="no-line-selected">Select a line item from the grid to view source provenance.</div>
          )}

          {/* Document Overview Snippet */}
          <div className="doc-preview-wrapper">
            <div className="doc-preview-header">Source Document Excerpt</div>
            <pre className="doc-preview-content font-mono">
              {caseData.raw_text ||
                (caseData.source_file
                  ? `[Binary ${caseData.source_file.source_type} document loaded securely. Lines extracted with deterministic coordinates.]`
                  : "")}
            </pre>
          </div>
        </aside>

        {/* Right Panel: QUOTATION PREPARATION GRID */}
        <main className="table-panel">
          {/* Table Toolbar */}
          <div className="table-toolbar">
            <div className="filter-tabs">
              <button
                className={`tab-btn ${filterMode === "ALL" ? "active" : ""}`}
                onClick={() => setFilterMode("ALL")}
              >
                All Lines ({lines.length})
              </button>
              <button
                className={`tab-btn ${filterMode === "ACTION_REQUIRED" ? "active" : ""}`}
                onClick={() => setFilterMode("ACTION_REQUIRED")}
              >
                Action Required ({unresolvedCount})
              </button>
              <button
                className={`tab-btn ${filterMode === "EXACT" ? "active" : ""}`}
                onClick={() => setFilterMode("EXACT")}
              >
                Exact Catalog ({lines.filter((l) => l.match_status === "EXACT_MATCH").length})
              </button>
              <button
                className={`tab-btn ${filterMode === "APPROVED" ? "active" : ""}`}
                onClick={() => setFilterMode("APPROVED")}
              >
                Approved ({lines.filter((l) => l.review_decision === "APPROVED").length})
              </button>
            </div>

            <div className="toolbar-actions">
              <button
                className="batch-approve-btn"
                onClick={handleBatchApproveExact}
                title="Bulk approve all exact matches after reviewing"
              >
                ✓ Approve Exact Matches
              </button>
            </div>
          </div>

          {/* Grid View */}
          <div className="grid-scroll-area">
            {loading ? (
              <div className="table-loading">Loading line items...</div>
            ) : filteredLines.length === 0 ? (
              <div className="table-empty">No lines match the active filter.</div>
            ) : (
              <table className="review-grid">
                <thead>
                  <tr>
                    <th style={{ width: "40px" }}>#</th>
                    <th style={{ width: "85px" }}>Decision</th>
                    <th style={{ width: "95px" }}>Qty / UOM</th>
                    <th>Requested Part & Manufacturer</th>
                    <th>Matched Catalog SKU / Candidate</th>
                    <th style={{ width: "120px" }}>Match Status</th>
                    <th style={{ width: "115px" }} className="align-right">Quick Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredLines.map((line) => {
                    const isSelected = line.line_id === selectedLineId;
                    const hasMissingQty = line.quantity === null;
                    const isCollision = line.match_status === "COLLISION";
                    const isNoMatch = line.match_status === "NO_MATCH";

                    return (
                      <tr
                        key={line.line_id}
                        className={`grid-row ${isSelected ? "selected" : ""} ${
                          hasMissingQty || isCollision ? "row-attention" : ""
                        }`}
                        onClick={() => setSelectedLineId(line.line_id)}
                      >
                        <td className="align-center font-mono font-muted">
                          {line.line_number}
                        </td>

                        <td>
                          <StatusBadge type="review" value={line.review_decision} />
                        </td>

                        <td>
                          <div className="qty-cell">
                            <input
                              type="number"
                              className={`qty-input ${hasMissingQty ? "missing" : ""}`}
                              placeholder="?"
                              value={line.quantity ?? ""}
                              onChange={(e) => {
                                const val = e.target.value === "" ? null : parseFloat(e.target.value);
                                handleQuickUpdate(line.line_id, { quantity: val });
                              }}
                              onClick={(e) => e.stopPropagation()}
                            />
                            <span className="uom-label font-mono">{line.unit || "EA"}</span>
                          </div>
                        </td>

                        <td>
                          <div className="part-desc-cell">
                            <div className="mpn-line">
                              <span className="mpn-text font-mono font-bold">
                                {line.requested_mpn || "Unspecified MPN"}
                              </span>
                              {line.requested_manufacturer && (
                                <span className="oem-pill">
                                  {line.requested_manufacturer}
                                </span>
                              )}
                            </div>
                            <div className="raw-subtext">
                              {line.description || line.raw_text}
                            </div>
                          </div>
                        </td>

                        <td>
                          {line.selected_catalog_sku ? (
                            <div className="sku-match-cell">
                              <span className="sku-badge font-mono">
                                {line.selected_catalog_sku}
                              </span>
                              {line.candidates[0] && (
                                <span className="candidate-desc">
                                  {line.candidates[0].catalog_item.manufacturer} —{" "}
                                  {line.candidates[0].catalog_item.description.slice(0, 45)}...
                                </span>
                              )}
                            </div>
                          ) : isCollision ? (
                            <div className="collision-cell">
                              <span className="collision-warning">
                                ⚠ {line.candidates.length} Brand Candidates
                              </span>
                              <span className="subtle-hint">Selection required</span>
                            </div>
                          ) : isNoMatch ? (
                            <span className="no-match-text">Not in Item Master</span>
                          ) : (
                            <span className="text-muted">—</span>
                          )}
                        </td>

                        <td>
                          <StatusBadge type="match" value={line.match_status} />
                        </td>

                        <td className="align-right" onClick={(e) => e.stopPropagation()}>
                          <div className="quick-actions">
                            <button
                              className={`action-icon-btn approve ${
                                line.review_decision === "APPROVED" ? "active" : ""
                              }`}
                              title="Approve this line"
                              onClick={() =>
                                handleQuickUpdate(line.line_id, {
                                  review_decision: "APPROVED",
                                  reviewer_notes: "Approved by operator",
                                })
                              }
                            >
                              ✓
                            </button>
                            <button
                              className={`action-icon-btn clarify ${
                                line.review_decision === "NEEDS_CLARIFICATION" ? "active" : ""
                              }`}
                              title="Flag for clarification"
                              onClick={() =>
                                handleQuickUpdate(line.line_id, {
                                  review_decision: "NEEDS_CLARIFICATION",
                                  reviewer_notes: "Requires customer confirmation",
                                })
                              }
                            >
                              ?
                            </button>
                            <button
                              className={`action-icon-btn reject ${
                                line.review_decision === "REJECTED" ? "active" : ""
                              }`}
                              title="Reject line"
                              onClick={() =>
                                handleQuickUpdate(line.line_id, {
                                  review_decision: "REJECTED",
                                  reviewer_notes: "Declined to quote",
                                })
                              }
                            >
                              ✕
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          {/* Selected Line Detail & Candidate Inspector Drawer */}
          {selectedLine && (
            <div className="line-inspector">
              <div className="inspector-header">
                <div className="inspector-title">
                  Line #{selectedLine.line_number} Inspector & Catalog Grounding
                </div>
                <div className="saving-indicator">
                  {savingLine ? "Saving changes..." : "Auto-saved"}
                </div>
              </div>

              <div className="inspector-content">
                {/* Candidates List / Collision Resolution */}
                <div className="candidates-column">
                  <div className="section-title">Catalog Match Proposals (Ground Truth):</div>
                  {selectedLine.candidates.length === 0 ? (
                    <div className="no-candidates-msg">
                      No exact matches in distributor catalog. To quote an approved equivalent, enter SKU or
                      mark for customer clarification. Never invent unverified parts.
                    </div>
                  ) : (
                    <div className="candidate-cards">
                      {selectedLine.candidates.map((c, idx) => {
                        const isChosen = selectedLine.selected_catalog_sku === c.catalog_item.internal_sku;
                        return (
                          <div
                            key={idx}
                            className={`candidate-card ${isChosen ? "chosen" : ""}`}
                          >
                            <div className="card-top">
                              <div>
                                <span className="cand-sku font-mono font-bold">
                                  {c.catalog_item.internal_sku}
                                </span>
                                <span className="cand-oem">
                                  {c.catalog_item.manufacturer} — {c.catalog_item.manufacturer_part_number}
                                </span>
                              </div>
                              <button
                                className={`select-candidate-btn ${isChosen ? "is-selected" : ""}`}
                                onClick={() =>
                                  handleQuickUpdate(selectedLine.line_id, {
                                    selected_catalog_sku: c.catalog_item.internal_sku,
                                  })
                                }
                              >
                                {isChosen ? "✓ Selected" : "Select SKU"}
                              </button>
                            </div>
                            <div className="cand-desc">{c.catalog_item.description}</div>
                            <div className="cand-footer">
                              <span className="cand-exp">{c.explanation}</span>
                              {c.catalog_item.list_price !== null && (
                                <span className="cand-price font-mono font-bold">
                                  List: ${c.catalog_item.list_price?.toFixed(2)}
                                </span>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Reviewer Note / Decision */}
                <div className="notes-column">
                  <div className="section-title">Reviewer Clarification Notes:</div>
                  <textarea
                    className="notes-textarea"
                    rows={3}
                    placeholder="Add clarification notes for the customer or internal pricing desk..."
                    value={reviewerNote}
                    onChange={(e) => setReviewerNote(e.target.value)}
                    onBlur={() => {
                      if (reviewerNote !== (selectedLine.reviewer_notes || "")) {
                        handleQuickUpdate(selectedLine.line_id, {
                          reviewer_notes: reviewerNote,
                        });
                      }
                    }}
                  />
                  <div className="decision-actions">
                    <button
                      className="approve-big-btn"
                      onClick={() =>
                        handleQuickUpdate(selectedLine.line_id, {
                          review_decision: "APPROVED",
                          reviewer_notes: reviewerNote,
                        })
                      }
                    >
                      ✓ Approve Line for Quote
                    </button>
                    <button
                      className="clarify-big-btn"
                      onClick={() =>
                        handleQuickUpdate(selectedLine.line_id, {
                          review_decision: "NEEDS_CLARIFICATION",
                          reviewer_notes: reviewerNote || "Customer confirmation required",
                        })
                      }
                    >
                      ? Mark for Clarification
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Audit Drawer Modal */}
      {showAuditDrawer && (
        <div className="audit-modal-backdrop" onClick={() => setShowAuditDrawer(false)}>
          <div className="audit-drawer" onClick={(e) => e.stopPropagation()}>
            <div className="drawer-header">
              <h3>Immutable Audit Trail (Case #{caseData.case_id})</h3>
              <button className="close-btn" onClick={() => setShowAuditDrawer(false)}>
                ✕
              </button>
            </div>
            <div className="audit-list">
              {auditEvents.length === 0 ? (
                <div className="no-audits">No audit events logged yet.</div>
              ) : (
                auditEvents.map((evt) => (
                  <div key={evt.event_id} className="audit-item">
                    <div className="audit-time font-mono">
                      {new Date(evt.recorded_at).toLocaleTimeString()}
                    </div>
                    <div className="audit-body">
                      <div className="audit-action font-bold">
                        {evt.action} — by {evt.actor}
                      </div>
                      {evt.field_name && (
                        <div className="audit-field">
                          Modified <code>{evt.field_name}</code>: &apos;{evt.old_value || "None"}&apos; → &apos;
                          {evt.new_value || "None"}&apos;
                        </div>
                      )}
                      {evt.notes && <div className="audit-notes">{evt.notes}</div>}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        .workbench-layout {
          display: flex;
          flex-direction: column;
          height: calc(100vh - 64px);
          overflow: hidden;
          background: var(--bg-app);
        }
        .workbench-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.75rem 1.5rem;
          background: #FFFFFF;
          border-bottom: 1px solid var(--border-light);
          z-index: 20;
        }
        .header-meta {
          display: flex;
          flex-direction: column;
          gap: 0.2rem;
        }
        .back-link {
          background: none;
          border: none;
          color: var(--accent-primary);
          font-size: 0.8rem;
          font-weight: 500;
          cursor: pointer;
          padding: 0;
          text-align: left;
        }
        .back-link:hover {
          text-decoration: underline;
        }
        .title-row {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }
        .case-title {
          font-size: 1.05rem;
          font-weight: 600;
          color: var(--text-primary);
        }
        .case-name {
          font-size: 0.875rem;
          color: var(--text-secondary);
        }
        .customer-tag {
          background: var(--bg-subtle);
          padding: 0.15rem 0.5rem;
          border-radius: 4px;
          font-size: 0.75rem;
          color: var(--text-muted);
          border: 1px solid var(--border-light);
        }
        .header-actions {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }
        .counters-box {
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.8rem;
          background: var(--bg-subtle);
          padding: 0.4rem 0.75rem;
          border-radius: 6px;
          border: 1px solid var(--border-light);
        }
        .count-label {
          color: var(--text-muted);
        }
        .divider {
          color: var(--border-medium);
          margin: 0 0.2rem;
        }
        .text-amber { 
          color: #D97706; 
          font-weight: 600; 
        }
        .text-emerald { 
          color: #059669; 
          font-weight: 600; 
        }
        .secondary-btn {
          background: #FFFFFF;
          border: 1px solid var(--border-medium);
          color: var(--text-secondary);
          padding: 0.45rem 0.8rem;
          border-radius: 6px;
          font-size: 0.82rem;
          font-weight: 500;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .secondary-btn:hover {
          background: var(--bg-subtle);
          color: var(--text-primary);
        }
        .export-btn {
          background: var(--accent-primary);
          border: 1px solid var(--accent-primary);
          color: #FFFFFF;
          padding: 0.45rem 1rem;
          border-radius: 6px;
          font-size: 0.875rem;
          font-weight: 500;
          cursor: pointer;
          transition: background 0.15s ease;
        }
        .export-btn:hover {
          background: var(--accent-primary-hover);
        }
        .export-btn.has-unresolved {
          background: #0F172A;
          border-color: #0F172A;
        }

        .split-workspace {
          display: flex;
          flex: 1;
          overflow: hidden;
        }
        .source-panel {
          width: 35%;
          min-width: 340px;
          max-width: 460px;
          background: #FFFFFF;
          border-right: 1px solid var(--border-light);
          display: flex;
          flex-direction: column;
          overflow-y: auto;
          padding: 1.25rem;
          gap: 1rem;
        }
        .panel-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding-bottom: 0.5rem;
          border-bottom: 1px solid var(--border-light);
        }
        .panel-title {
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-muted);
          letter-spacing: 0.5px;
          text-transform: uppercase;
        }
        .badge-source {
          background: var(--bg-subtle);
          color: var(--text-secondary);
          border: 1px solid var(--border-light);
          font-family: var(--font-mono);
          font-size: 0.72rem;
          padding: 0.1rem 0.4rem;
          border-radius: 4px;
        }
        .file-info-card {
          background: var(--bg-subtle);
          border: 1px solid var(--border-light);
          border-radius: 6px;
          padding: 0.75rem;
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }
        .info-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.8rem;
        }
        .info-label {
          color: var(--text-muted);
        }
        .font-xs { font-size: 0.72rem; }

        .selected-locator-box {
          background: #EFF6FF;
          border: 1px solid #BFDBFE;
          border-radius: 6px;
          padding: 0.85rem;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }
        .locator-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.8rem;
          font-weight: 600;
          color: var(--accent-primary);
        }
        .locator-coord {
          font-size: 0.75rem;
          color: var(--text-secondary);
        }
        .raw-snippet-container {
          background: #FFFFFF;
          border: 1px solid #BFDBFE;
          border-radius: 4px;
          padding: 0.65rem;
        }
        .snippet-title {
          font-size: 0.72rem;
          color: var(--text-muted);
          margin-bottom: 0.25rem;
        }
        .raw-snippet-box {
          font-size: 0.82rem;
          color: var(--text-primary);
          line-height: 1.4;
          white-space: pre-wrap;
          word-break: break-word;
        }
        .warnings-container {
          background: #FFFBEB;
          border: 1px solid #FDE68A;
          border-radius: 4px;
          padding: 0.5rem 0.65rem;
          font-size: 0.78rem;
          color: #92400E;
        }
        .warning-heading {
          font-weight: 600;
          margin-bottom: 0.2rem;
        }
        .no-line-selected {
          padding: 2.5rem 1rem;
          text-align: center;
          color: var(--text-muted);
          font-size: 0.85rem;
        }
        .doc-preview-wrapper {
          border: 1px solid var(--border-light);
          border-radius: 6px;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          flex: 1;
          background: #FFFFFF;
        }
        .doc-preview-header {
          background: var(--bg-subtle);
          padding: 0.45rem 0.75rem;
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-muted);
          border-bottom: 1px solid var(--border-light);
        }
        .doc-preview-content {
          padding: 0.75rem;
          font-size: 0.78rem;
          color: var(--text-secondary);
          line-height: 1.45;
          white-space: pre-wrap;
          overflow-y: auto;
          flex: 1;
          background: #FAFAFA;
        }

        .table-panel {
          flex: 1;
          display: flex;
          flex-direction: column;
          background: #FFFFFF;
          overflow: hidden;
        }
        .table-toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.65rem 1.25rem;
          border-bottom: 1px solid var(--border-light);
          background: #FAFAFA;
        }
        .filter-tabs {
          display: flex;
          gap: 0.35rem;
        }
        .tab-btn {
          background: none;
          border: 1px solid transparent;
          padding: 0.35rem 0.65rem;
          border-radius: 4px;
          font-size: 0.8rem;
          font-weight: 500;
          color: var(--text-secondary);
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .tab-btn:hover {
          color: var(--text-primary);
          background: var(--bg-subtle);
        }
        .tab-btn.active {
          background: #FFFFFF;
          color: var(--accent-primary);
          font-weight: 600;
          border-color: var(--border-light);
          box-shadow: var(--shadow-sm);
        }
        .batch-approve-btn {
          background: #FFFFFF;
          border: 1px solid var(--border-medium);
          color: #059669;
          font-size: 0.78rem;
          font-weight: 500;
          padding: 0.35rem 0.65rem;
          border-radius: 4px;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .batch-approve-btn:hover {
          background: #ECFDF5;
          border-color: #A7F3D0;
        }

        .grid-scroll-area {
          flex: 1;
          overflow-y: auto;
        }
        .review-grid {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.85rem;
          text-align: left;
        }
        .review-grid th {
          position: sticky;
          top: 0;
          background: #F8FAFC;
          padding: 0.65rem 0.85rem;
          font-weight: 600;
          font-size: 0.75rem;
          color: var(--text-muted);
          text-transform: uppercase;
          border-bottom: 1px solid var(--border-light);
          z-index: 10;
        }
        .review-grid td {
          padding: 0.65rem 0.85rem;
          border-bottom: 1px solid var(--border-light);
          vertical-align: middle;
        }
        .grid-row {
          cursor: pointer;
          transition: background 0.1s ease;
        }
        .grid-row:hover {
          background: #F8FAFC;
        }
        .grid-row.selected {
          background: #EFF6FF !important;
          border-left: 3px solid var(--accent-primary);
        }
        .grid-row.row-attention {
          background: #FFFDF5;
        }
        .align-center { text-align: center; }
        .align-right { text-align: right; }
        .font-muted { color: var(--text-muted); }
        .font-mono { font-family: var(--font-mono); }
        .font-bold { font-weight: 600; }

        .qty-cell {
          display: flex;
          align-items: center;
          gap: 0.35rem;
        }
        .qty-input {
          width: 55px;
          padding: 0.25rem 0.4rem;
          border: 1px solid var(--border-medium);
          background: #FFFFFF;
          color: var(--text-primary);
          border-radius: 4px;
          font-size: 0.85rem;
          font-family: var(--font-mono);
          text-align: center;
        }
        .qty-input:focus {
          border-color: var(--accent-primary);
          outline: none;
        }
        .qty-input.missing {
          border-color: #EF4444;
          background: #FEF2F2;
          color: #DC2626;
        }
        .uom-label {
          font-size: 0.72rem;
          color: var(--text-muted);
        }
        .part-desc-cell {
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
        }
        .mpn-line {
          display: flex;
          align-items: center;
          gap: 0.45rem;
        }
        .mpn-text {
          color: var(--text-primary);
        }
        .oem-pill {
          background: var(--bg-subtle);
          border: 1px solid var(--border-light);
          padding: 0.05rem 0.35rem;
          border-radius: 3px;
          font-size: 0.7rem;
          color: var(--text-secondary);
        }
        .raw-subtext {
          font-size: 0.75rem;
          color: var(--text-muted);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          max-width: 320px;
        }
        .sku-match-cell {
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
        }
        .sku-badge {
          background: #EFF6FF;
          color: var(--accent-primary);
          border: 1px solid #BFDBFE;
          padding: 0.1rem 0.35rem;
          border-radius: 3px;
          font-size: 0.75rem;
          display: inline-block;
          width: fit-content;
        }
        .candidate-desc {
          font-size: 0.72rem;
          color: var(--text-muted);
        }
        .collision-cell {
          display: flex;
          flex-direction: column;
        }
        .collision-warning {
          color: #B45309;
          font-weight: 500;
          font-size: 0.75rem;
        }
        .subtle-hint {
          font-size: 0.7rem;
          color: var(--text-muted);
        }
        .no-match-text {
          color: #DC2626;
          font-size: 0.75rem;
          font-weight: 500;
        }

        .quick-actions {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 0.35rem;
        }
        .action-icon-btn {
          width: 26px;
          height: 26px;
          border-radius: 4px;
          border: 1px solid var(--border-medium);
          background: #FFFFFF;
          color: var(--text-secondary);
          cursor: pointer;
          font-size: 0.8rem;
          font-weight: 600;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: all 0.15s ease;
        }
        .action-icon-btn.approve:hover, .action-icon-btn.approve.active {
          background: #059669;
          color: #FFFFFF;
          border-color: #059669;
        }
        .action-icon-btn.clarify:hover, .action-icon-btn.clarify.active {
          background: #D97706;
          color: #FFFFFF;
          border-color: #D97706;
        }
        .action-icon-btn.reject:hover, .action-icon-btn.reject.active {
          background: #DC2626;
          color: #FFFFFF;
          border-color: #DC2626;
        }

        .line-inspector {
          height: 230px;
          border-top: 1px solid var(--border-light);
          background: #FAFAFA;
          display: flex;
          flex-direction: column;
          padding: 0.85rem 1.25rem;
        }
        .inspector-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding-bottom: 0.45rem;
          border-bottom: 1px solid var(--border-light);
          margin-bottom: 0.65rem;
        }
        .inspector-title {
          font-size: 0.82rem;
          font-weight: 600;
          color: var(--text-primary);
        }
        .saving-indicator {
          font-size: 0.75rem;
          color: var(--text-muted);
        }
        .inspector-content {
          display: flex;
          gap: 1.25rem;
          flex: 1;
          overflow: hidden;
        }
        .candidates-column {
          flex: 3;
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
          overflow-y: auto;
        }
        .notes-column {
          flex: 2;
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
        }
        .section-title {
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
        }
        .candidate-cards {
          display: flex;
          flex-direction: column;
          gap: 0.45rem;
        }
        .candidate-card {
          border: 1px solid var(--border-light);
          border-radius: 6px;
          padding: 0.65rem;
          background: #FFFFFF;
        }
        .candidate-card.chosen {
          border-color: var(--accent-primary);
          background: #EFF6FF;
        }
        .card-top {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 0.25rem;
        }
        .cand-sku {
          color: var(--accent-primary);
          margin-right: 0.5rem;
        }
        .cand-oem {
          font-size: 0.8rem;
          color: var(--text-secondary);
        }
        .select-candidate-btn {
          background: #FFFFFF;
          border: 1px solid var(--border-medium);
          color: var(--text-secondary);
          padding: 0.2rem 0.55rem;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 500;
          cursor: pointer;
        }
        .select-candidate-btn:hover {
          background: var(--bg-subtle);
          color: var(--text-primary);
        }
        .select-candidate-btn.is-selected {
          background: var(--accent-primary);
          color: #FFFFFF;
          border-color: var(--accent-primary);
        }
        .cand-desc {
          font-size: 0.78rem;
          color: var(--text-primary);
          margin-bottom: 0.25rem;
        }
        .cand-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-size: 0.72rem;
          color: var(--text-muted);
        }
        .cand-price {
          color: #059669;
          font-weight: 600;
        }
        .no-candidates-msg {
          font-size: 0.8rem;
          color: var(--text-muted);
          padding: 0.75rem;
          background: #FFFFFF;
          border-radius: 4px;
          border: 1px dashed var(--border-medium);
        }

        .notes-textarea {
          width: 100%;
          padding: 0.5rem;
          border: 1px solid var(--border-medium);
          background: #FFFFFF;
          color: var(--text-primary);
          border-radius: 4px;
          font-size: 0.82rem;
          resize: none;
        }
        .notes-textarea:focus {
          outline: none;
          border-color: var(--accent-primary);
        }
        .decision-actions {
          display: flex;
          gap: 0.5rem;
        }
        .approve-big-btn {
          flex: 1;
          background: #059669;
          color: #FFFFFF;
          border: 1px solid #059669;
          padding: 0.45rem;
          border-radius: 4px;
          font-size: 0.8rem;
          font-weight: 500;
          cursor: pointer;
        }
        .approve-big-btn:hover {
          background: #047857;
        }
        .clarify-big-btn {
          flex: 1;
          background: #D97706;
          color: #FFFFFF;
          border: 1px solid #D97706;
          padding: 0.45rem;
          border-radius: 4px;
          font-size: 0.8rem;
          font-weight: 500;
          cursor: pointer;
        }
        .clarify-big-btn:hover {
          background: #B45309;
        }

        .audit-modal-backdrop {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(15, 23, 42, 0.35);
          z-index: 100;
          display: flex;
          justify-content: flex-end;
        }
        .audit-drawer {
          width: 440px;
          background: #FFFFFF;
          height: 100%;
          box-shadow: var(--shadow-lg);
          display: flex;
          flex-direction: column;
          padding: 1.5rem;
        }
        .drawer-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding-bottom: 1rem;
          border-bottom: 1px solid var(--border-light);
        }
        .drawer-header h3 {
          font-size: 0.95rem;
          font-weight: 600;
          color: var(--text-primary);
        }
        .close-btn {
          background: none;
          border: none;
          color: var(--text-muted);
          font-size: 1.1rem;
          cursor: pointer;
        }
        .close-btn:hover {
          color: var(--text-primary);
        }
        .audit-list {
          flex: 1;
          overflow-y: auto;
          padding-top: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }
        .audit-item {
          display: flex;
          gap: 0.75rem;
          font-size: 0.8rem;
          padding: 0.5rem;
          background: var(--bg-subtle);
          border-radius: 4px;
        }
        .audit-time {
          color: var(--text-muted);
          font-size: 0.72rem;
          white-space: nowrap;
        }
        .audit-body {
          display: flex;
          flex-direction: column;
          gap: 0.2rem;
        }
        .audit-action {
          color: var(--text-primary);
        }
        .audit-field {
          color: var(--text-secondary);
          font-size: 0.75rem;
        }
        .audit-field code {
          background: #FFFFFF;
          border: 1px solid var(--border-light);
          padding: 0.1rem 0.25rem;
          border-radius: 3px;
        }
        .audit-notes {
          color: var(--text-muted);
          font-style: italic;
          font-size: 0.75rem;
        }
        .no-audits {
          color: var(--text-muted);
          font-size: 0.85rem;
          text-align: center;
          padding: 2rem 0;
        }
      `}</style>
    </div>
  );
}
