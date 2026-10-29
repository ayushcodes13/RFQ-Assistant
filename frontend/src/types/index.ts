export type CaseStatus = "NEW" | "PROCESSING" | "NEEDS_REVIEW" | "READY_TO_EXPORT" | "EXPORTED" | "FAILED";
export type SourceType = "EMAIL_TEXT" | "CSV" | "XLSX" | "PDF_NATIVE" | "PDF_SCANNED";
export type ExtractionStatus = "EXTRACTED" | "NEEDS_CORRECTION" | "UNRESOLVED";
export type MatchStatus = "EXACT_MATCH" | "COLLISION" | "NO_MATCH" | "MANUAL_OVERRIDE";
export type ReviewDecision = "PENDING" | "APPROVED" | "NEEDS_CLARIFICATION" | "REJECTED";
export type AuditAction = "CASE_CREATED" | "PARSED" | "LINE_EDITED" | "LINE_APPROVED" | "LINE_REJECTED" | "LINE_FLAGGED" | "CATALOG_IMPORTED" | "EXPORTED";

export interface SourceLocator {
  file_name: string;
  page_number?: number | null;
  sheet_name?: string | null;
  row_number?: number | null;
  text_snippet?: string | null;
}

export interface ExtractionWarning {
  code: string;
  message: string;
  severity: string;
}

export interface CatalogItem {
  internal_sku: string;
  manufacturer: string;
  manufacturer_part_number: string;
  description: string;
  list_price?: number | null;
  stock_qty?: number | null;
  catalog_version?: string | null;
}

export interface MatchCandidate {
  catalog_item: CatalogItem;
  match_type: MatchStatus;
  explanation: string;
  confidence_note: string;
}

export interface RFQLineItem {
  line_id: string;
  case_id: string;
  line_number: number;
  raw_text: string;
  source_locator: SourceLocator;
  requested_manufacturer?: string | null;
  requested_mpn?: string | null;
  description?: string | null;
  quantity?: number | null;
  unit?: string | null;
  required_by?: string | null;
  notes?: string | null;
  extraction_status: ExtractionStatus;
  extraction_warnings: ExtractionWarning[];
  match_status: MatchStatus;
  selected_catalog_sku?: string | null;
  candidates: MatchCandidate[];
  review_decision: ReviewDecision;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  reviewer_notes?: string | null;
  version: number;
}

export interface SourceFileMetadata {
  file_id: string;
  file_name: string;
  source_type: SourceType;
  mime_type: string;
  size_bytes: number;
  sha256_digest: string;
  uploaded_at: string;
}

export interface RFQCase {
  case_id: string;
  title: string;
  customer_label?: string | null;
  status: CaseStatus;
  source_type: SourceType;
  source_file?: SourceFileMetadata | null;
  raw_text?: string | null;
  created_at: string;
  updated_at: string;
  line_count: number;
  unresolved_count: number;
  parser_version: string;
  catalog_id?: string | null;
}

export interface AuditEvent {
  event_id: string;
  case_id: string;
  line_id?: string | null;
  actor: string;
  action: AuditAction;
  field_name?: string | null;
  old_value?: string | null;
  new_value?: string | null;
  recorded_at: string;
  notes?: string | null;
}

export interface ExportManifest {
  export_id: string;
  case_id: string;
  file_name: string;
  format: string;
  is_draft: boolean;
  total_lines: number;
  approved_lines: number;
  unresolved_lines_omitted: number;
  generated_at: string;
  reviewer_name: string;
  unsent_email_draft: string;
  download_url: string;
}
