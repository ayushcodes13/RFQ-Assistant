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
    if (confirm(`Are you sure you want to delete quote case ${caseId}?`)) {
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

  const needsReviewCount = cases.filter((c) => c.status === "NEEDS_REVIEW").length;
  const readyCount = cases.filter((c) => c.status === "READY_TO_EXPORT").length;

  return (
    <div className="inbox-container">
      {/* Page Title & Simple Stats */}
      <div className="inbox-header">
        <div>
          <h1 className="page-title">Quotation Requests</h1>
          <p className="page-subtitle">Review incoming RFQs, verify exact part numbers, and export ready worksheets.</p>
        </div>

        <div className="stats-row">
          <div className="stat-pill">
            <span className="stat-label">Total:</span>
            <span className="stat-num">{cases.length}</span>
          </div>
          <div className="stat-pill warning">
            <span className="stat-label">Needs Review:</span>
            <span className="stat-num">{needsReviewCount}</span>
          </div>
          <div className="stat-pill success">
            <span className="stat-label">Ready:</span>
            <span className="stat-num">{readyCount}</span>
          </div>
        </div>
      </div>

      {/* Quick Sample Links */}
      <div className="sample-bar">
        <span className="sample-label">Try sample data:</span>
        <button
          className="sample-btn"
          disabled={loadingSample}
          onClick={() => loadSyntheticScenario("20lines")}
        >
          20-Item BOM
        </button>
        <button
          className="sample-btn"
          disabled={loadingSample}
          onClick={() => loadSyntheticScenario("messy_email")}
        >
          Messy Email
        </button>
        <button
          className="sample-btn"
          disabled={loadingSample}
          onClick={() => loadSyntheticScenario("collision")}
        >
          Brand Collision
        </button>
      </div>

      {/* Controls & Filter Bar */}
      <div className="toolbar">
        <input
          type="text"
          className="search-input"
          placeholder="Search by title, customer, or ID..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />

        <div className="toolbar-actions">
          <select
            className="filter-select"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="ALL">All Statuses</option>
            <option value="NEEDS_REVIEW">Needs Review</option>
            <option value="READY_TO_EXPORT">Ready to Export</option>
            <option value="NEW">New</option>
            <option value="EXPORTED">Exported</option>
          </select>

          <button className="btn-secondary" onClick={onRefresh} title="Refresh case list">
            Refresh
          </button>
          <button className="btn-primary" onClick={onOpenNewRfq}>
            + Ingest RFQ
          </button>
        </div>
      </div>

      {/* Cases Table */}
      <div className="table-card">
        {loading ? (
          <div className="state-box">Loading quotation cases...</div>
        ) : filteredCases.length === 0 ? (
          <div className="state-box">
            <p className="empty-title">No RFQs found</p>
            <p className="empty-sub">
              Upload an inquiry file, paste an email quote request, or click one of the sample buttons above.
            </p>
            <button className="btn-primary" style={{ marginTop: "1rem" }} onClick={onOpenNewRfq}>
              Create Quote Request
            </button>
          </div>
        ) : (
          <table className="cases-table">
            <thead>
              <tr>
                <th>Reference</th>
                <th>Request / Title</th>
                <th>Customer</th>
                <th>Source</th>
                <th>Status</th>
                <th className="align-center">Items</th>
                <th className="align-center">Attention</th>
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
                  <td className="source-cell">
                    {c.source_file ? c.source_file.file_name : "Pasted Text"}
                  </td>
                  <td>
                    <StatusBadge type="case" value={c.status} />
                  </td>
                  <td className="align-center font-mono">{c.line_count}</td>
                  <td className="align-center">
                    {c.unresolved_count > 0 ? (
                      <span className="badge-attention">{c.unresolved_count} items</span>
                    ) : (
                      <span className="badge-ok">✓ Ready</span>
                    )}
                  </td>
                  <td className="time-cell">{new Date(c.created_at).toLocaleDateString()}</td>
                  <td className="align-right" onClick={(e) => e.stopPropagation()}>
                    <button
                      className="btn-secondary btn-sm"
                      onClick={() => onSelectCase(c.case_id)}
                    >
                      Review
                    </button>
                    <button
                      className="delete-btn"
                      title="Delete case"
                      onClick={(e) => handleDelete(e, c.case_id)}
                    >
                      ✕
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
          padding: 2rem;
          max-width: 1200px;
          margin: 0 auto;
        }
        .inbox-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          margin-bottom: 1.25rem;
        }
        .page-title {
          font-size: 1.35rem;
          font-weight: 600;
          color: var(--text-primary);
        }
        .page-subtitle {
          font-size: 0.875rem;
          color: var(--text-muted);
          margin-top: 0.2rem;
        }
        .stats-row {
          display: flex;
          gap: 0.5rem;
        }
        .stat-pill {
          background: #FFFFFF;
          border: 1px solid var(--border-light);
          padding: 0.35rem 0.75rem;
          border-radius: 6px;
          display: flex;
          align-items: center;
          gap: 0.4rem;
          font-size: 0.8rem;
          box-shadow: var(--shadow-sm);
        }
        .stat-label {
          color: var(--text-muted);
        }
        .stat-num {
          font-weight: 600;
          color: var(--text-primary);
        }
        .stat-pill.warning .stat-num {
          color: #D97706;
        }
        .stat-pill.success .stat-num {
          color: #059669;
        }
        .sample-bar {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.5rem 0.75rem;
          background: #FFFFFF;
          border: 1px solid var(--border-light);
          border-radius: 6px;
          margin-bottom: 1.25rem;
          font-size: 0.8rem;
        }
        .sample-label {
          color: var(--text-muted);
          margin-right: 0.25rem;
        }
        .sample-btn {
          background: var(--bg-subtle);
          border: 1px solid var(--border-medium);
          padding: 0.25rem 0.6rem;
          border-radius: 4px;
          font-size: 0.75rem;
          font-weight: 500;
          color: var(--text-secondary);
          cursor: pointer;
          transition: all 0.15s ease;
        }
        .sample-btn:hover:not(:disabled) {
          background: #E2E8F0;
          color: var(--text-primary);
        }
        .toolbar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 1rem;
          margin-bottom: 1rem;
        }
        .search-input {
          width: 340px;
          padding: 0.5rem 0.75rem;
          border: 1px solid var(--border-medium);
          border-radius: 6px;
          font-size: 0.875rem;
          background: #FFFFFF;
          color: var(--text-primary);
        }
        .search-input:focus {
          outline: none;
          border-color: var(--accent-primary);
        }
        .toolbar-actions {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }
        .filter-select {
          padding: 0.5rem 0.75rem;
          border: 1px solid var(--border-medium);
          border-radius: 6px;
          font-size: 0.85rem;
          background: #FFFFFF;
          color: var(--text-primary);
          cursor: pointer;
        }
        .filter-select:focus {
          outline: none;
          border-color: var(--accent-primary);
        }
        .table-card {
          background: #FFFFFF;
          border: 1px solid var(--border-light);
          border-radius: 8px;
          box-shadow: var(--shadow-sm);
          overflow: hidden;
        }
        .cases-table {
          width: 100%;
          border-collapse: collapse;
          font-size: 0.875rem;
          text-align: left;
        }
        .cases-table th {
          background: #F8FAFC;
          padding: 0.75rem 1rem;
          font-weight: 600;
          color: var(--text-muted);
          font-size: 0.75rem;
          text-transform: uppercase;
          border-bottom: 1px solid var(--border-light);
        }
        .cases-table td {
          padding: 0.85rem 1rem;
          border-bottom: 1px solid var(--border-light);
          color: var(--text-secondary);
        }
        .case-row {
          cursor: pointer;
          transition: background 0.1s ease;
        }
        .case-row:hover {
          background: #F8FAFC;
        }
        .case-id {
          font-size: 0.8rem;
          color: var(--accent-primary);
          font-weight: 500;
        }
        .case-title {
          font-weight: 500;
          color: var(--text-primary);
          max-width: 260px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .customer-cell {
          color: var(--text-secondary);
        }
        .source-cell {
          font-size: 0.8rem;
          color: var(--text-muted);
        }
        .badge-attention {
          background: #FFFBEB;
          color: #B45309;
          border: 1px solid #FDE68A;
          font-size: 0.72rem;
          font-weight: 500;
          padding: 0.15rem 0.45rem;
          border-radius: 4px;
        }
        .badge-ok {
          color: #059669;
          font-size: 0.75rem;
          font-weight: 500;
        }
        .time-cell {
          color: var(--text-muted);
          font-size: 0.8rem;
        }
        .btn-sm {
          padding: 0.3rem 0.65rem;
          font-size: 0.8rem;
        }
        .delete-btn {
          background: none;
          border: none;
          color: var(--text-muted);
          font-size: 0.85rem;
          cursor: pointer;
          padding: 0.3rem 0.5rem;
          margin-left: 0.35rem;
          border-radius: 4px;
        }
        .delete-btn:hover {
          color: #EF4444;
          background: #FEF2F2;
        }
        .state-box {
          padding: 3.5rem 2rem;
          text-align: center;
        }
        .empty-title {
          font-size: 1.1rem;
          font-weight: 600;
          color: var(--text-primary);
        }
        .empty-sub {
          font-size: 0.85rem;
          color: var(--text-muted);
          margin-top: 0.35rem;
        }
        .align-center { text-align: center; }
        .align-right { text-align: right; }
        .font-mono { font-family: var(--font-mono); }
      `}</style>
    </div>
  );
}
