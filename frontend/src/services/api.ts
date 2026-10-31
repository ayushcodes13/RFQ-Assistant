import {
  AuditEvent,
  BatchReviewRequest,
  CatalogImportResponse,
  CatalogItem,
  ExportManifest,
  RFQCase,
  RFQLineItem,
  RFQLineItemUpdate,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY;

/**
 * Local demo mode needs no credentials. When the backend runs with
 * REQUIRE_AUTH=true, set NEXT_PUBLIC_API_KEY to a configured pilot key.
 */
function authHeaders(): Record<string, string> {
  return API_KEY ? { "X-API-Key": API_KEY } : {};
}

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
    headers: authHeaders(),
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
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await readError(res, fallback));
  if (res.status === 204) return undefined as T;
  return res.json();
}

export async function fetchHealth() {
  return getJson<{ status: string; catalog_size: number; total_cases: number }>(
    "/api/health",
    "Backend service unreachable"
  );
}

export async function listCases(): Promise<RFQCase[]> {
  return getJson<RFQCase[]>("/api/rfqs", "Failed to load RFQ cases");
}

export async function getCase(caseId: string): Promise<RFQCase> {
  return getJson<RFQCase>(`/api/rfqs/${caseId}`, "Failed to load case details");
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
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) throw new Error(await readError(res, "Upload failed"));
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
    headers: authHeaders(),
    body: formData,
  });
  if (!res.ok) throw new Error(await readError(res, "Failed to parse text"));
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
    headers: authHeaders(),
  });
  if (!res.ok) throw new Error(await readError(res, "Failed to delete case"));
}

export async function listCatalog(): Promise<CatalogItem[]> {
  return getJson<CatalogItem[]>("/api/catalogs", "Failed to load catalog");
}

export async function importCatalogCSV(file: File): Promise<CatalogImportResponse> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/catalogs/import`, {
    method: "POST",
    headers: authHeaders(),
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
  return `${API_BASE}${downloadUrl.startsWith("/") ? "" : "/"}${downloadUrl}`;
}

export function getExportDownloadUrl(caseId: string, exportId: string): string {
  return `${API_BASE}/api/rfqs/${caseId}/exports/${exportId}`;
}
