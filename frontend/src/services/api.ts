import {
  AuditEvent,
  BatchReviewRequest,
  CatalogImportResponse,
  CatalogItem,
  CatalogUpdateProposal,
  ExportManifest,
  ExportDocumentSummary,
  RFQCase,
  RFQCaseSummary,
  RFQLineItem,
  RFQLineItemUpdate,
  ReviewPlan,
  QuoteDraft,
  SpreadsheetSourcePreview,
} from "@/types";

const API_BASE = "/api/proxy";

async function readError(res: Response, fallback: string): Promise<string> {
  const body = await res.json().catch(() => null);
  if (body && typeof body.detail === "string") return body.detail;
  if (body && Array.isArray(body.detail)) {
    return body.detail.map((d: { msg?: string }) => d.msg).filter(Boolean).join("; ") || fallback;
  }
  return `${fallback} (HTTP ${res.status})`;
}

async function getJson<T>(path: string, fallback: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: {},
    cache: "no-store",
  });
  if (!res.ok) throw new Error(await readError(res, fallback));
  return res.json();
}

async function sendJson<T>(
  path: string,
  method: "POST" | "PATCH" | "DELETE",
  body: unknown,
  fallback: string
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readError(res, fallback));
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function fetchHealth() {
  return getJson<{ status: "healthy" }>(
    "/api/health",
    "Backend service unreachable"
  );
}

export async function listCases(): Promise<RFQCaseSummary[]> {
  return getJson<RFQCaseSummary[]>("/api/rfqs", "Failed to load RFQ cases");
}

export async function getCase(caseId: string): Promise<RFQCase> {
  return getJson<RFQCase>(`/api/rfqs/${caseId}`, "Failed to load case details");
}

export async function listCaseExports(caseId: string): Promise<ExportDocumentSummary[]> {
  return getJson<ExportDocumentSummary[]>(`/api/rfqs/${encodeURIComponent(caseId)}/exports`, "Failed to load case documents");
}

export async function getCaseQuoteDraft(caseId: string): Promise<QuoteDraft> {
  return getJson<QuoteDraft>(`/v1/rfqs/${encodeURIComponent(caseId)}/quote-draft`, "Failed to load quote draft");
}

export async function createCaseQuoteDraft(caseId: string): Promise<QuoteDraft> {
  return sendJson<QuoteDraft>(`/v1/rfqs/${encodeURIComponent(caseId)}/draft-quote`, "POST", {}, "Quote draft could not be prepared");
}

export async function getCaseLines(caseId: string): Promise<RFQLineItem[]> {
  return getJson<RFQLineItem[]>(
    `/api/rfqs/${caseId}/lines`,
    "Failed to load RFQ line items"
  );
}

export async function updateLineItem(
  caseId: string,
  lineId: string,
  update: RFQLineItemUpdate
): Promise<RFQLineItem> {
  return sendJson<RFQLineItem>(
    `/api/rfqs/${caseId}/lines/${lineId}`,
    "PATCH",
    update,
    "Failed to update line item"
  );
}

export async function rematchLineItem(
  caseId: string,
  lineId: string,
  expectedVersion: number,
): Promise<RFQLineItem> {
  return sendJson<RFQLineItem>(
    `/api/rfqs/${caseId}/lines/${lineId}/rematch`,
    "POST",
    { expected_version: expectedVersion },
    "Failed to refresh catalog match",
  );
}

export async function batchReviewLines(
  caseId: string,
  request: BatchReviewRequest
): Promise<{ status: string; updated_count: number }> {
  return sendJson<{ status: string; updated_count: number }>(
    `/api/rfqs/${caseId}/review`,
    "POST",
    request,
    "Batch review failed"
  );
}

export async function getReviewPlan(caseId: string): Promise<ReviewPlan> {
  return getJson<ReviewPlan>(`/api/rfqs/${caseId}/review-plan`, "Failed to load review plan");
}

export async function getSpreadsheetSourcePreview(
  caseId: string,
  sheetName: string,
  rowNumber: number,
  targetCells: string[] = [],
  sourceFileId?: string,
): Promise<SpreadsheetSourcePreview> {
  const query = new URLSearchParams({
    sheet_name: sheetName,
    row_number: String(rowNumber),
    radius: "4",
  });
  targetCells.forEach((cell) => query.append("target_cells", cell));
  if (sourceFileId) query.set("source_file_id", sourceFileId);
  return getJson<SpreadsheetSourcePreview>(
    `/api/rfqs/${encodeURIComponent(caseId)}/source/preview?${query.toString()}`,
    "Failed to open the source worksheet",
  );
}

export async function approveRemainingValidatedLines(
  caseId: string,
  expectedVersions: Record<string, number>,
): Promise<{ status: string; updated_count: number }> {
  return sendJson<{ status: string; updated_count: number }>(
    `/api/rfqs/${caseId}/review-plan/approve-remaining`,
    "POST",
    { expected_versions: expectedVersions },
    "Batch approval failed"
  );
}

export async function createCaseFromUpload(
  file: File,
  title?: string,
  customer?: string
): Promise<RFQCase> {
  const formData = new FormData();
  formData.append("file", file);
  if (title) formData.append("title", title);
  if (customer) formData.append("customer_label", customer);

  const res = await fetch(`${API_BASE}/api/rfqs`, {
    method: "POST",
    headers: {},
    body: formData,
  });
  if (!res.ok) throw new Error(await readError(res, "Upload failed"));
  return res.json();
}

export async function createCaseFromText(
  text: string,
  title?: string,
  customer?: string
): Promise<RFQCase> {
  const formData = new FormData();
  formData.append("pasted_text", text);
  if (title) formData.append("title", title);
  if (customer) formData.append("customer_label", customer);

  const res = await fetch(`${API_BASE}/api/rfqs`, {
    method: "POST",
    headers: {},
    body: formData,
  });
  if (!res.ok) throw new Error(await readError(res, "Failed to parse text"));
  return res.json();
}

export async function createCaseFromSources(
  files: File[],
  pastedText: string,
  title?: string,
  customer?: string,
): Promise<RFQCase> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (pastedText.trim()) formData.append("pasted_text", pastedText);
  if (title) formData.append("title", title);
  if (customer) formData.append("customer_label", customer);
  const res = await fetch(`${API_BASE}/api/rfqs`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await readError(res, "RFQ intake failed"));
  return res.json();
}

export async function retrySourceDocument(caseId: string, sourceFileId: string): Promise<RFQCase> {
  const res = await fetch(`${API_BASE}/api/rfqs/${encodeURIComponent(caseId)}/sources/${encodeURIComponent(sourceFileId)}/retry`, { method: "POST" });
  if (!res.ok) throw new Error(await readError(res, "Attachment retry failed"));
  return res.json();
}

export async function getAuditTrail(caseId: string): Promise<AuditEvent[]> {
  return getJson<AuditEvent[]>(
    `/api/rfqs/${caseId}/audit`,
    "Failed to load audit events"
  );
}

export async function deleteCase(caseId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/rfqs/${caseId}`, {
    method: "DELETE",
    headers: {},
  });
  if (!res.ok) throw new Error(await readError(res, "Failed to delete case"));
}

export async function listCatalog(): Promise<CatalogItem[]> {
  return getJson<CatalogItem[]>("/api/catalogs", "Failed to load catalog");
}

export async function listCatalogUpdateProposals(): Promise<CatalogUpdateProposal[]> {
  return getJson<CatalogUpdateProposal[]>("/api/catalogs/updates", "Failed to load distributor data changes");
}

export async function stageCatalogUpdate(input: { text?: string; file?: File; revisionOf?: string; clearFields?: ("list_price" | "currency" | "stock_qty")[] }): Promise<CatalogUpdateProposal[]> {
  const formData = new FormData();
  if (input.text) formData.append("pasted_text", input.text);
  if (input.file) formData.append("file", input.file);
  if (input.revisionOf) formData.append("revision_of", input.revisionOf);
  if (input.clearFields?.length) formData.append("clear_fields", input.clearFields.join(","));
  const res = await fetch(`${API_BASE}/api/catalogs/updates`, { method: "POST", body: formData });
  if (!res.ok) throw new Error(await readError(res, "Distributor data could not be processed"));
  return res.json();
}

async function reviewCatalogUpdate(proposalId: string, decision: "accept" | "reject", note?: string): Promise<CatalogUpdateProposal> {
  return sendJson<CatalogUpdateProposal>(
    `/api/catalogs/updates/${encodeURIComponent(proposalId)}/${decision}`,
    "POST",
    { note },
    decision === "accept" ? "Change could not be applied" : "Change could not be rejected",
  );
}

export function acceptCatalogUpdate(proposalId: string): Promise<CatalogUpdateProposal> {
  return reviewCatalogUpdate(proposalId, "accept");
}

export function rejectCatalogUpdate(proposalId: string): Promise<CatalogUpdateProposal> {
  return reviewCatalogUpdate(proposalId, "reject");
}

export async function importCatalogCSV(file: File): Promise<CatalogImportResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/catalogs/import`, {
    method: "POST",
    headers: {},
    body: formData,
  });
  if (!res.ok) throw new Error(await readError(res, "Catalog import failed"));
  return res.json();
}

export async function exportWorksheet(
  caseId: string,
  allowPartial: boolean = false,
  format: string = "xlsx",
  actor: string = "Inside Sales"
): Promise<ExportManifest> {
  return sendJson<ExportManifest>(
    `/api/rfqs/${caseId}/exports`,
    "POST",
    { case_id: caseId, allow_partial: allowPartial, format, actor },
    "Export validation failed"
  );
}

export async function getEmailDraft(caseId: string): Promise<{ draft: string }> {
  return getJson<{ draft: string }>(
    `/api/rfqs/${caseId}/email-draft`,
    "Failed to generate email draft"
  );
}

/**
 * The backend returns a root-relative `download_url`; the browser needs the
 * API origin when the frontend is served from a different port.
 */
export function resolveDownloadUrl(downloadUrl: string): string {
  if (/^https?:\/\//i.test(downloadUrl)) return downloadUrl;
  if (/^https?:\/\//i.test(downloadUrl)) return downloadUrl;
  return `${API_BASE}${downloadUrl.startsWith("/") ? "" : "/"}${downloadUrl}`;
}

export function getExportDownloadUrl(caseId: string, exportId: string): string {
  return `${API_BASE}/api/rfqs/${caseId}/exports/${exportId}`;
}
