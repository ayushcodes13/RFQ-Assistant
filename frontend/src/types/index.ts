/**
 * Frontend domain types derived from the backend OpenAPI schema.
 *
 * The generated file (`api.generated.ts`) is the source of truth for wire
 * shapes. Regenerate both files with:
 *
 *   python -m rfq_assistant.scripts.export_openapi
 *   cd frontend && npm run gen:types
 *
 * Only UI-only helpers (catalog import summary, optimistic edit payload)
 * are declared by hand below.
 */
import type { components } from "./api.generated";

type Schemas = components["schemas"];

// Enum unions straight from the backend schema.
export type CaseStatus = Schemas["CaseStatus"];
export type SourceType = Schemas["SourceType"];
export type ExtractionStatus = Schemas["ExtractionStatus"];
export type MatchStatus = Schemas["MatchStatus"];
export type ReviewDecision = Schemas["ReviewDecision"];
export type AuditAction = Schemas["AuditAction"];

export type SourceLocator = Schemas["SourceLocator"];
export type ExtractionWarning = Schemas["ExtractionWarning"];
export type CatalogItem = Schemas["CatalogItem"];
export type MatchCandidate = Schemas["MatchCandidate"];
export type SourceFileMetadata = Schemas["SourceFileMetadata"];

/**
 * The backend always serialises defaulted collections, so require them here
 * instead of making every render guard against `undefined`.
 */
export type RFQLineItem = Schemas["RFQLineItem"] & {
  extraction_warnings: ExtractionWarning[];
  candidates: MatchCandidate[];
};

export type RFQCase = Schemas["RFQCase"] & {
  created_at: string;
  updated_at: string;
};

export type AuditEvent = Schemas["AuditEvent"] & {
  recorded_at: string;
};

export type ExportManifest = Schemas["ExportManifest"] & {
  generated_at: string;
};

// Request payloads.
export type RFQLineItemUpdate = Schemas["RFQLineItemUpdate"];
export type BatchReviewRequest = Schemas["BatchReviewRequest"];
export type ExportRequest = Schemas["ExportRequest"];

/** Response from `POST /api/catalogs/import` (no response_model on backend). */
export interface CatalogImportSummary {
  imported: number;
  duplicates: number;
  collisions: number;
  total_catalog_size: number;
}

export interface CatalogImportResponse {
  status: string;
  summary: CatalogImportSummary;
}
