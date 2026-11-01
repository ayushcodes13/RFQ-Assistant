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

export interface QuoteDraftSource {
  file_id: string;
  page?: number | null;
  sheet?: string | null;
  cell_range?: string | null;
  text_excerpt?: string | null;
  bbox?: number[] | null;
}

export interface QuoteDraftLine {
  line_no: number;
  requested_mpn: string;
  requested_manufacturer?: string | null;
  catalogue_part_id?: string | null;
  description?: string | null;
  quantity?: string | null;
  unit: string;
  unit_price?: string | null;
  currency?: string | null;
  line_total?: string | null;
  match_status: string;
  requires_human_review: boolean;
  sources: QuoteDraftSource[];
}

export interface QuoteDraft {
  quote_id: string;
  case_id: string;
  currency: string;
  lines: QuoteDraftLine[];
  total_amount?: string | null;
  validation_errors: string[];
  quote_proposal_status: "grounded" | "not_configured" | "failed" | "no_retrieved_prices";
  quote_proposal_warnings: string[];
  is_approved: boolean;
}

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
