/** Frontend wire types are derived from the FastAPI OpenAPI contract. */
import type { components } from "./api.generated";

type Schemas = components["schemas"];

export type CaseStatus = Schemas["CaseStatus"];
export type SourceType = Schemas["SourceType"];
export type ExtractionStatus = Schemas["ExtractionStatus"];
export type MatchStatus = Schemas["MatchStatus"];
export type ReviewDecision = Schemas["ReviewDecision"];
export type AuditAction = Schemas["AuditAction"];
export type SourceLocator = Schemas["SourceLocator"];
export type ExtractionWarning = Schemas["ExtractionWarning"];
export type CatalogItem = Schemas["CatalogItem"];
export type CatalogUpdateProposal = Schemas["CatalogUpdateProposal"];
export type MatchCandidate = Schemas["MatchCandidate"];
export type SourceFileMetadata = Schemas["SourceFileMetadata"];
export type RFQLineItem = Schemas["RFQLineItem"] & {
  extraction_warnings: ExtractionWarning[];
  candidates: MatchCandidate[];
};
export type RFQCase = Schemas["RFQCase"] & {
  created_at: string;
  updated_at: string;
};
export type RFQCaseSummary = Schemas["RFQCaseSummary"] & {
  created_at: string;
  updated_at: string;
};
export type AuditEvent = Schemas["AuditEvent"] & { recorded_at: string };
export type ExportManifest = Schemas["ExportManifest"] & { generated_at: string };
export type ExportDocumentSummary = Schemas["ExportDocumentSummary"];
export type RFQLineItemUpdate = Schemas["RFQLineItemUpdateRequest"];
export type BatchReviewRequest = Schemas["BatchReviewRequest"];
export type ReviewPlan = Schemas["ReviewPlan"];
export type SpreadsheetSourcePreview = Schemas["SpreadsheetSourcePreview"];
export type ExportRequest = Schemas["ExportRequest"];

export interface CatalogImportSummary {
  imported: number;
  duplicates: number;
  collisions: number;
  total_catalog_size: number;
  catalog_version: string | null;
}

export interface CatalogImportResponse {
  status: string;
  summary: CatalogImportSummary;
}
