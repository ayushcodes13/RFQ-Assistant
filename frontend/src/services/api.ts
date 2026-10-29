import {
  AuditEvent,
  CatalogItem,
  ExportManifest,
  RFQCase,
  RFQLineItem,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export async function fetchHealth() {
  const res = await fetch(`${API_BASE}/api/health`);
  if (!res.ok) throw new Error("Backend service unreachable");
  return res.json();
}

export async function listCases(): Promise<RFQCase[]> {
  const res = await fetch(`${API_BASE}/api/rfqs`);
  if (!res.ok) throw new Error("Failed to load RFQ cases");
  return res.json();
}

export async function getCase(caseId: string): Promise<RFQCase> {
  const res = await fetch(`${API_BASE}/api/rfqs/${caseId}`);
  if (!res.ok) throw new Error("Failed to load case details");
  return res.json();
}

export async function getCaseLines(caseId: string): Promise<RFQLineItem[]> {
  const res = await fetch(`${API_BASE}/api/rfqs/${caseId}/lines`);
  if (!res.ok) throw new Error("Failed to load RFQ line items");
  return res.json();
}

export async function updateLineItem(
  caseId: string,
  lineId: string,
  update: Partial<RFQLineItem> & { actor?: string; reviewer_notes?: string | null; expected_version?: number }
): Promise<RFQLineItem> {
  const res = await fetch(`${API_BASE}/api/rfqs/${caseId}/lines/${lineId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to update line item");
  }
  return res.json();
}

export async function batchReviewLines(
  caseId: string,
  lineIds: string[],
  decision: string,
  actor: string = "Inside Sales",
  notes?: string
): Promise<{ updated_count: number }> {
  const res = await fetch(`${API_BASE}/api/rfqs/${caseId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ line_ids: lineIds, decision, actor, notes }),
  });
  if (!res.ok) throw new Error("Batch review failed");
  return res.json();
}

export async function createCaseFromUpload(
  file: File,
  title?: string,
  customer?: string,
  actor: string = "Inside Sales"
): Promise<RFQCase> {
  const formData = new FormData();
  formData.append("file", file);
  if (title) formData.append("title", title);
  if (customer) formData.append("customer_label", customer);
  formData.append("actor", actor);

  const res = await fetch(`${API_BASE}/api/rfqs`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Upload failed");
  }
  return res.json();
}

export async function createCaseFromText(
  text: string,
  title?: string,
  customer?: string,
  actor: string = "Inside Sales"
): Promise<RFQCase> {
  const formData = new FormData();
  formData.append("pasted_text", text);
  if (title) formData.append("title", title);
  if (customer) formData.append("customer_label", customer);
  formData.append("actor", actor);

  const res = await fetch(`${API_BASE}/api/rfqs`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to parse text");
  }
  return res.json();
}

export async function getAuditTrail(caseId: string): Promise<AuditEvent[]> {
  const res = await fetch(`${API_BASE}/api/rfqs/${caseId}/audit`);
  if (!res.ok) throw new Error("Failed to load audit events");
  return res.json();
}

export async function deleteCase(caseId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/rfqs/${caseId}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete case");
}

export async function listCatalog(): Promise<CatalogItem[]> {
  const res = await fetch(`${API_BASE}/api/catalogs`);
  if (!res.ok) throw new Error("Failed to load catalog");
  return res.json();
}

export async function importCatalogCSV(file: File): Promise<{ summary: any }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/catalogs/import`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Catalog import failed");
  }
  return res.json();
}

export async function exportWorksheet(
  caseId: string,
  allowPartial: boolean = false,
  format: string = "xlsx",
  actor: string = "Inside Sales"
): Promise<ExportManifest> {
  const res = await fetch(`${API_BASE}/api/rfqs/${caseId}/exports`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ case_id: caseId, allow_partial: allowPartial, format, actor }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Export validation failed");
  }
  return res.json();
}

export async function getEmailDraft(caseId: string): Promise<{ draft: string }> {
  const res = await fetch(`${API_BASE}/api/rfqs/${caseId}/email-draft`);
  if (!res.ok) throw new Error("Failed to generate email draft");
  return res.json();
}

export function getExportDownloadUrl(caseId: string, exportId: string): string {
  return `${API_BASE}/api/rfqs/${caseId}/exports/${exportId}`;
}

/** Original uploaded RFQ for source verification (local demo / authenticated endpoint). */
export function getCaseSourceUrl(caseId: string): string {
  return `${API_BASE}/api/rfqs/${encodeURIComponent(caseId)}/source`;
}
