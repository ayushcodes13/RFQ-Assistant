# RFQ Assistant — Target OSS Architecture

## 1. Executive Summary

The RFQ Assistant implements a robust, security-first open-source stack tailored for independent industrial electrical, automation, and electronic-component distributors.

**Core Principle:**
> **AI may read, extract, rank, explain, and draft. Deterministic services calculate and validate. Humans approve commercial commitments.**

This separation is strictly enforced at code, permission, and tool levels rather than relying merely on UI copy.

---

## 2. Recommended Open-Source Stack

| Layer | Component | License | Architectural Role |
| :--- | :--- | :--- | :--- |
| **Attachment Security** | **ClamAV** | GPLv2 (Socket) | Pre-parser malware scanning over TCP/Unix socket; runs as an isolated daemon/sidecar rather than linking `libclamav` into application code. |
| **Spreadsheet Fidelity** | **openpyxl + defusedxml** | MIT / Python | Cell-level, sheet-level, formula, hidden-row/sheet inspection; defends against quadratic XML blowup attacks. |
| **Part Matching** | **RapidFuzz** | MIT | Fast local candidate generator over item masters behind deterministic exact matching; similarity != equivalence. |
| **Agent / HITL** | **Pydantic AI** | MIT | Typed Pydantic outputs, system prompt contracts, and tools with explicit approval gates (`requires_approval=True`). |
| **Domain References** | **InvenTree & ERPNext** | MIT / GPL-3.0 | Schema models for Parts, Supplier Parts, BOMs, RFQs, Supplier Quotations, and Sales Quotations. |

---

## 3. Staged Data Flow & Safety Boundaries

```mermaid
flowchart TD
    Inbound[Inbound Customer RFQ / Attachment] --> RawStore[Immutable Raw Artifact Storage]
    RawStore --> ClamAVScan[ClamAV Scanner + Quarantine]
    ClamAVScan -- Malicious / Infected --> Quarantine[Quarantine Vault & Security Alert]
    ClamAVScan -- Clean --> DocRouter[Document Type Router]
    
    DocRouter -->|XLSX / XLSM| OpenPyXL[openpyxl + defusedxml Inspector]
    DocRouter -->|PDF / Scan| PDFParser[Docling / pypdf Parser]
    DocRouter -->|Email Text| TextParser[Deterministic Text Parser]
    
    OpenPyXL --> CanonicalSchema[Canonical RFQ Line Schema with Source Refs]
    PDFParser --> CanonicalSchema
    TextParser --> CanonicalSchema
    
    CanonicalSchema --> ExactMatch[Deterministic Exact Matcher]
    ExactMatch -- Match Found --> VerifiedRow[Exact Catalog Match]
    ExactMatch -- No Exact Match --> RapidFuzz[RapidFuzz Candidate Retrieval]
    RapidFuzz --> CandidateRow[Candidate Status (Review Required)]
    
    VerifiedRow --> QuoteValidator[Deterministic Quote Validator]
    CandidateRow --> WorkbenchUI[Inside-Sales Review Workbench]
    
    WorkbenchUI --> HumanEdit[Human Correction & Audit Trail]
    HumanEdit --> QuoteValidator
    
    QuoteValidator --> ProposedQuote[Proposed Quote Draft with Version Hash]
    ProposedQuote --> ApprovalGate[Version-Bound Approval Gate]
    
    ApprovalGate -- Approved (Hash Bound) --> OutboundAction[Draft Export / ERP Connector]
    ApprovalGate -- Unapproved / Tampered --> Blocked[Transmission Blocked]
```

---

## 4. Public V1 Contract Endpoints

- `POST /v1/rfqs/extract`: Scans attachment via ClamAV, routes to appropriate parser, extracts RFQ lines with provenance.
- `POST /v1/rfqs/{case_id}/match`: Exact catalog lookup and RapidFuzz candidate retrieval.
- `POST /v1/rfqs/{case_id}/draft-quote`: Compiles proposed quotation draft with price provenance and locks cryptographic draft hash.
- `GET /v1/quote-drafts/{quote_id}`: Retrieves draft, hash, and validation results.
- `POST /v1/quote-drafts/{quote_id}/approve`: Approves quotation draft bound to expected version hash.
- `POST /v1/quote-drafts/{quote_id}/reject`: Rejects draft with recorded reason.
- `POST /v1/approved-quotes/{quote_id}/send`: Transmits quotation strictly after human approval verification.
