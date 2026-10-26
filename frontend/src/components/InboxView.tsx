"use client";

import React, { useState } from "react";
import { RFQCase } from "@/types";
import { StatusBadge } from "@/components/StatusBadge";
import { createCaseFromText, deleteCase } from "@/services/api";

interface InboxViewProps {
  cases: RFQCase[];
  loading: boolean;
  onSelectCase: (caseId: string) => void;
  onRefresh: () => void;
  onOpenNewRfq: () => void;
}

export function InboxView({
  cases,
  loading,
  onSelectCase,
  onRefresh,
  onOpenNewRfq,
}: InboxViewProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [filterStatus, setFilterStatus] = useState<string>("ALL");
  const [loadingSample, setLoadingSample] = useState(false);

  // Fast Synthetic Benchmark Loaders
  const loadSyntheticScenario = async (scenario: "20lines" | "messy_email" | "collision") => {
    setLoadingSample(true);
    try {
      if (scenario === "messy_email") {
        const text = `SYNTHETIC TEST FIXTURE — EMAIL INTAKE
From: plant_ops@apex-mfg-synthetic.com
Subject: Urgent RFQ - Spare parts line 3

Could you please quote us on the following items for delivery next Tuesday?
1. 10 pcs of Schneider Electric LC1D09BD contactors (24VDC coil)
2. 4 units Siemens 6ES7223-1BL32-0XB0 digital I/O modules
3. 25x XB4BA31 green pushbuttons (Schneider)
4. Need 5 pcs of MY4N-D2-DC24 relays from Omron
5. Also quote the sensor from last time we ordered for conveyor 2, about 3 pieces
6. 12 EA of Eaton FAZ-C10/1 breakers

Please confirm pricing and lead time ASAP.`;
        const newCase = await createCaseFromText(
          text,
          "Scenario 2: Messy Email Quote Request",
          "Apex Manufacturing (Synthetic)"
        );
        onRefresh();
        onSelectCase(newCase.case_id);
      } else if (scenario === "collision") {
        const text = `SYNTHETIC TEST FIXTURE — BRAND COLLISION
Customer: Apex Maintenance Services
RFQ Ref: AMS-2026-9041

Please provide unit price and stock for:
- 10 EA part number XG-42 (Manufacturer not specified)
- 4 EA part number ABC-12 from Acme Industrial
- 2 EA part number ABC-12-R2 from Acme Industrial`;
        const newCase = await createCaseFromText(
          text,
          "Scenario 3: Cross-Brand Collision (XG-42)",
          "Apex Maintenance Services (Synthetic)"
        );
        onRefresh();
        onSelectCase(newCase.case_id);
      } else if (scenario === "20lines") {
        // Fallback text representing the 20-line BOM
        const text = `SYNTHETIC SAMPLE RFQ - ACME AUTOMATION PROJECT
Line 1: 10 EA Schneider Electric LC1D09BD (TeSys D contactor 9A 24VDC)
Line 2: 4 EA Schneider Electric LC1D25BD (TeSys D contactor 25A 24VDC)
Line 3: 25 EA Schneider Electric XB4BA31 (Flush green pushbutton 1NO)
Line 4: 15 EA Schneider Electric XB4BV63 (Green pilot light 250V)
Line 5: 6 EA Schneider Electric GV2ME10 (Manual motor protector 4-6.3A)
Line 6: 2 EA Siemens 6ES7214-1AG40-0XB0 (S7-1200 CPU 1214C DC/DC/DC)
Line 7: 4 EA Siemens 6ES7223-1BL32-0XB0 (S7-1200 SM 1223 16DI/16DO)
Line 8: 12 EA Siemens 3RT2015-1BB41 (SIRIUS power contactor 7A 24VDC)
Line 9: 8 EA Siemens 3RV2011-1AA10 (SIRIUS motor starter 1.1-1.6A)
Line 10: 20 EA Omron E2E-X7D1-N (Proximity sensor M18 shielded)
Line 11: 50 EA Omron MY4N-D2-DC24 (Miniature relay 4PDT 24VDC)
Line 12: 5 EA Omron H3CR-A8 (Solid state timer 100-240VAC)
Line 13: 3 EA Omron S8VK-G24024 (DIN rail power supply 240W 24VDC)
Line 14: 30 EA Eaton FAZ-C10/1 (Miniature circuit breaker 1P 10A)
Line 15: 15 EA Eaton FAZ-C16/2 (Miniature circuit breaker 2P 16A)
Line 16: 6 EA Eaton DILM9-10(24VDC) (Contactor 3P 9A 1NO 24VDC)
Line 17: 40 EA Phoenix Contact 2900364 (PLC-RPT-24DC/21 Relay Module)
Line 18: Phoenix Contact UT 2.5 (Feed-through terminal block gray)
Line 19: 2 EA Unknown Mfr NONEXISTENT-PART-999 (Custom enclosure bracket)
Line 20: 5 EA Acme Industrial ABC-12A (Thermal overload relay with aux NC)`;
        const newCase = await createCaseFromText(
          text,
          "Scenario 1: 20-Line Industrial Automation BOM",
          "Acme Automation Project (Synthetic)"
        );
        onRefresh();
        onSelectCase(newCase.case_id);
      }
    } catch (e: any) {
      alert(`Error loading sample: ${e.message}`);
    } finally {
      setLoadingSample(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, caseId: string) => {
    e.stopPropagation();
    if (confirm(`Are you sure you want to delete case ${caseId}?`)) {
      try {
        await deleteCase(caseId);
        onRefresh();
      } catch (err: any) {
        alert(err.message);
      }
    }
  };

  const filteredCases = cases.filter((c) => {
    const matchesSearch =
      c.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.case_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (c.customer_label || "").toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = filterStatus === "ALL" || c.status === filterStatus;
    return matchesSearch && matchesStatus;
  });

  const totalLines = cases.reduce((acc, c) => acc + c.line_count, 0);
  const needsReviewCount = cases.filter((c) => c.status === "NEEDS_REVIEW").length;
  const readyCount = cases.filter((c) => c.status === "READY_TO_EXPORT").length;

  return (
    <div className="inbox-container">
      {/* Top Banner / Metrics */}
      <section className="metrics-bar">
        <div className="metric-card">
          <div className="metric-label">Active RFQ Cases</div>
          <div className="metric-value">{cases.length}</div>
        </div>
        <div className="metric-card warning">
          <div className="metric-label">Needs Human Review</div>
          <div className="metric-value">{needsReviewCount}</div>
        </div>
        <div className="metric-card success">
          <div className="metric-label">Ready to Export</div>
          <div className="metric-value">{readyCount}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Extracted Line Items</div>
          <div className="metric-value">{totalLines}</div>
        </div>
      </section>

      {/* Demo Quick Launchers */}
      <section className="demo-launcher-bar">
        <div className="demo-launcher-title">
          <span>⚡ One-Click Demo Scenarios:</span>
        </div>
        <div className="demo-launcher-buttons">
          <button
            className="demo-btn"
            disabled={loadingSample}
            onClick={() => loadSyntheticScenario("20lines")}
            title="Load 20-line BOM with missing quantity edge case on line 18"
          >
            Load 20-Line BOM (Scenario 1)
          </button>
          <button
            className="demo-btn"
            disabled={loadingSample}
            onClick={() => loadSyntheticScenario("messy_email")}
            title="Load natural language email with vague item 'sensor from last time'"
          >
            Load Messy Email (Scenario 2)
          </button>
          <button
            className="demo-btn"
            disabled={loadingSample}
            onClick={() => loadSyntheticScenario("collision")}
            title="Load brand collision case: XG-42 without OEM"
          >
            Load Brand Collision (Scenario 3)
          </button>
        </div>
      </section>

      {/* Controls & Filter bar */}
      <div className="controls-row">
        <div className="search-group">
          <input
            type="text"
            className="search-input"
            placeholder="Search cases by ID, title, or customer..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="filter-group">
          <select
            className="filter-select"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="ALL">All Statuses ({cases.length})</option>
            <option value="NEEDS_REVIEW">Needs Review</option>
            <option value="READY_TO_EXPORT">Ready to Export</option>
            <option value="NEW">New</option>
            <option value="EXPORTED">Exported</option>
          </select>

          <button className="refresh-btn" onClick={onRefresh} title="Refresh case list">
            ↻ Refresh
          </button>
          <button className="primary-btn" onClick={onOpenNewRfq}>
            + Ingest New RFQ
          </button>
        </div>
      </div>

      {/* Cases Table */}
      <div className="table-wrapper">
        {loading ? (
          <div className="loading-state">Loading quotation cases...</div>
        ) : filteredCases.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">📋</div>
            <div className="empty-title">No RFQ cases match your criteria</div>
            <p className="empty-desc">
              Upload an Excel/PDF/CSV quotation request, paste email text, or click one of the synthetic
              scenarios above to test the intake workflow.
            </p>
            <button className="primary-btn" onClick={onOpenNewRfq}>
              Start New RFQ Intake
            </button>
          </div>
        ) : (
          <table className="cases-table">
            <thead>
              <tr>
                <th>Case Ref</th>
                <th>Title / Request</th>
                <th>Customer</th>
                <th>Source Document</th>
                <th>Status</th>
                <th className="align-center">Lines</th>
                <th className="align-center">Unresolved</th>
                <th>Received</th>
                <th className="align-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {filteredCases.map((c) => (
                <tr
                  key={c.case_id}
                  className="case-row"
                  onClick={() => onSelectCase(c.case_id)}
                >
                  <td className="case-id font-mono">{c.case_id}</td>
                  <td className="case-title">{c.title}</td>
                  <td className="customer-cell">{c.customer_label || "—"}</td>
                  <td>
                    <span className="source-tag">
                      {c.source_file ? c.source_file.file_name : "Pasted Text"}
                    </span>
                  </td>
                  <td>
                    <StatusBadge type="case" value={c.status} />
                  </td>
                  <td className="align-center font-mono font-bold">{c.line_count}</td>
                  <td className="align-center">
                    {c.unresolved_count > 0 ? (
                      <span className="unresolved-pill">{c.unresolved_count} to fix</span>
                    ) : (
                      <span className="resolved-pill">All clear</span>
                    )}
                  </td>
                  <td className="time-cell">{new Date(c.created_at).toLocaleDateString()}</td>
                  <td className="align-right" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="open-btn"
                      onClick={() => onSelectCase(c.case_id)}
                    >
                      Open Workbench →
                    </button>
                    <button
                      className="delete-icon-btn"
                      title="Delete case"
                      onClick={(e) => handleDelete(e, c.case_id)}
                    >
                      🗑
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <style jsx>{`
        .inbox-container {
          padding: 1.5rem;
          max-width: 1440px;
          margin: 0 auto;
        }
        .metrics-bar {
          display: grid;
          grid-template-columns: repeat(4, 1fr);
          gap: 1rem;
          margin-bottom: 1.25rem;
        }
        .metric-card {
          background: #ffffff;
          border: 1px solid var(--border-light);
          padding: 1rem 1.25rem;
          border-radius: 8px;
          box-shadow: var(--shadow-sm);
        }
        .metric-card.warning {
          border-left: 4px solid #F59E0B;
        }
        .metric-card.success {
          border-left: 4px solid #10B981;
        }
        .metric-label {
          font-size: 0.8rem;
          color: var(--text-muted);
          font-weight: 500;
          margin-bottom: 0.25rem;
        }
        .metric-value {
          font-size: 1.6rem;
          font-weight: 700;
          color: var(--text-primary);
        }
        .demo-launcher-bar {
          display: flex;
          align-items: center;
          gap: 1rem;
          background: #EFF6FF;
          border: 1px solid var(--accent-border);
          padding: 0.65rem 1rem;
          border-radius: 6px;
          margin-bottom: 1.25rem;
        }
        .demo-launcher-title {
          font-size: 0.82rem;
          font-weight: 600;
          color: var(--accent-primary);
          white-space: nowrap;
        }
        .demo-launcher-buttons {
          display: flex;
          gap: 0.5rem;
          flex-wrap: wrap;
        }
        .demo-btn {
          background: #ffffff;
          border: 1px solid var(--accent-border);
          color: var(--accent-primary);
          padding: 0.35rem 0.65rem;
          border-radius: 4px;
          font-size: 0.78rem;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .demo-btn:hover:not(:disabled) {
          background: var(--accent-primary);
          color: #ffffff;
        }
        .controls-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          margin-bottom: 1rem;
        }
        .search-input {
          width: 380px;
          padding: 0.5rem 0.85rem;
          border: 1px solid var(--border-medium);
          border-radius: 6px;
          font-size: 0.88rem;
          background: #ffffff;
        }
        .search-input:focus {
          outline: none;
          border-color: var(--border-focus);
        }
        .filter-group {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .filter-select {
          padding: 0.5rem 0.75rem;
          border: 1px solid var(--border-medium);
          border-radius: 6px;
          font-size: 0.85rem;
          background: #ffffff;
        }
        .refresh-btn {
          background: #ffffff;
          border: 1px solid var(--border-medium);
          padding: 0.5rem 0.75rem;
          border-radius: 6px;
          font-size: 0.85rem;
          font-weight: 500;
          cursor: pointer;
        }
        .primary-btn {
          background: var(--accent-primary);
          border: 1px solid var(--accent-primary);
          color: #ffffff;
          padding: 0.5rem 1rem;
          border-radius: 6px;
          font-size: 0.88rem;
          font-weight: 600;
          cursor: pointer;
        }
        .primary-btn:hover {
          background: var(--accent-primary-hover);
        }
        .table-wrapper {
          background: #ffffff;
          border: 1px solid var(--border-light);
          border-radius: 8px;
          box-shadow: var(--shadow-sm);
          overflow: hidden;
        }
        .cases-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.88rem;
          text-align: left;
        }
        .cases-table th {
          background: var(--bg-subtle);
          padding: 0.75rem 1rem;
          font-weight: 600;
          color: var(--text-secondary);
          border-bottom: 1px solid var(--border-light);
        }
        .cases-table td {
          padding: 0.85rem 1rem;
          border-bottom: 1px solid var(--border-light);
          color: var(--text-primary);
        }
        .case-row {
          cursor: pointer;
          transition: background 0.1s ease;
        }
        .case-row:hover {
          background: #F8FAFC;
        }
        .case-id {
          color: var(--accent-primary);
          font-weight: 600;
          font-size: 0.85rem;
        }
        .case-title {
          font-weight: 600;
          max-width: 280px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .customer-cell {
          color: var(--text-secondary);
        }
        .source-tag {
          background: var(--bg-subtle);
          border: 1px solid var(--border-medium);
          padding: 0.15rem 0.45rem;
          border-radius: 4px;
          font-size: 0.75rem;
          font-family: var(--font-mono);
        }
        .unresolved-pill {
          background: #FEF3C7;
          color: #92400E;
          font-size: 0.75rem;
          font-weight: 600;
          padding: 0.15rem 0.45rem;
          border-radius: 4px;
        }
        .resolved-pill {
          background: #D1FAE5;
          color: #065F46;
          font-size: 0.75rem;
          font-weight: 600;
          padding: 0.15rem 0.45rem;
          border-radius: 4px;
        }
        .time-cell {
          color: var(--text-muted);
          font-size: 0.8rem;
        }
        .align-center {
          text-align: center;
        }
        .align-right {
          text-align: right;
        }
        .font-mono {
          font-family: var(--font-mono);
        }
        .font-bold {
          font-weight: 700;
        }
        .open-btn {
          background: var(--bg-subtle);
          border: 1px solid var(--border-medium);
          color: var(--text-primary);
          padding: 0.35rem 0.65rem;
          border-radius: 4px;
          font-size: 0.8rem;
          font-weight: 600;
          cursor: pointer;
          margin-right: 0.5rem;
        }
        .open-btn:hover {
          background: var(--accent-primary);
          border-color: var(--accent-primary);
          color: #ffffff;
        }
        .delete-icon-btn {
          background: none;
          border: none;
          font-size: 0.9rem;
          cursor: pointer;
          opacity: 0.6;
        }
        .delete-icon-btn:hover {
          opacity: 1;
        }
        .empty-state {
          padding: 4rem 2rem;
          text-align: center;
        }
        .empty-icon {
          font-size: 2.5rem;
          margin-bottom: 0.75rem;
        }
        .empty-title {
          font-size: 1.15rem;
          font-weight: 700;
          margin-bottom: 0.5rem;
        }
        .empty-desc {
          color: var(--text-muted);
          max-width: 480px;
          margin: 0 auto 1.5rem auto;
          font-size: 0.9rem;
        }
        .loading-state {
          padding: 3rem;
          text-align: center;
          color: var(--text-muted);
        }
      `}</style>
    </div>
  );
}
