"""Case lifecycle manager with audit logging and state tracking."""

import csv
import hashlib
import json
import logging
import math
import threading
import time
import uuid
from datetime import datetime
from importlib import metadata as package_metadata
from io import BytesIO, StringIO
from typing import Dict, List, Optional

from openpyxl import load_workbook

from rfq_assistant.ingestion import (
    DocumentParserError,
    DocumentStorage,
    get_parser,
    validate_file_upload,
)
from rfq_assistant.ingestion.ai_extraction import (
    EvidenceSegment,
    GroundedLLMExtractor,
    LLM_SCHEMA_VERSION,
    LLM_VALIDATOR_VERSION,
)
from rfq_assistant.ingestion.parsers.base import ParsedDocumentResult, ParsedLineDraft
from rfq_assistant.ingestion.parsers.spreadsheet_parser import identify_columns
from rfq_assistant.ingestion.source_segments import source_segments
from rfq_assistant.matching import CatalogRepository, ExactMatchEngine
from rfq_assistant.quotation.line_rules import blocking_line_issues
from rfq_assistant.persistence import StateStore
from rfq_assistant.schemas.enums import (
    AuditAction,
    CaseStatus,
    ExtractionStatus,
    MatchStatus,
    ReviewDecision,
    SourceType,
)

from rfq_assistant.schemas.models import (
    AuditEvent,
    BatchReviewRequest,
    ExtractionWarning,
    RFQCase,
    RFQLineItem,
    RFQLineItemUpdate,
    ReviewPlan,
    SourceFileMetadata,
    SourceCoverageUnit,
    SourceLocator,
)

MAX_TEXT_INTAKE_REGIONS = 500

log = logging.getLogger(__name__)


class IngestionLeaseLostError(RuntimeError):
    """Raised when a worker no longer owns the processing lease for a case."""


class CaseManager:
    """Orchestrates case ingestion, catalog matching, line updates, and audit logging."""

    def __init__(
        self,
        catalog: CatalogRepository,
        storage: Optional[DocumentStorage] = None,
        state_store: Optional[StateStore] = None,
        llm_extractor: Optional[GroundedLLMExtractor] = None,
    ):
        self.catalog = catalog
        self.storage = storage or DocumentStorage()
        self.state_store = state_store
        self.llm_extractor = llm_extractor
        self.matcher = ExactMatchEngine(self.catalog)

        # Runtime caches backed by SQLite when persistence is configured.
        self._cases: Dict[str, RFQCase] = {}
        self._lines_by_case: Dict[str, List[RFQLineItem]] = {}
        self._audit_events: Dict[str, List[AuditEvent]] = {}
        self._processing_locks: Dict[str, threading.Lock] = {}
        self._processing_locks_guard = threading.Lock()
        if self.state_store:
            for payload in self.state_store.load_cases():
                case = RFQCase.model_validate(payload)
                self._cases[case.case_id] = case
                self._lines_by_case[case.case_id] = [
                    RFQLineItem.model_validate(item) for item in self.state_store.load_lines(case.case_id)
                ]
                self._audit_events[case.case_id] = [
                    AuditEvent.model_validate(item) for item in self.state_store.load_audit_events(case.case_id)
                ]

    def get_case(self, case_id: str) -> Optional[RFQCase]:
        return self._cases.get(case_id)

    def list_cases(self) -> List[RFQCase]:
        return sorted(self._cases.values(), key=lambda c: c.created_at, reverse=True)

    def get_lines(self, case_id: str) -> List[RFQLineItem]:
        return self._lines_by_case.get(case_id, [])

    def get_audit_trail(self, case_id: str) -> List[AuditEvent]:
        return self._audit_events.get(case_id, [])

    def create_case_from_upload(
        self,
        filename: str,
        content: bytes,
        title: Optional[str] = None,
        customer_label: Optional[str] = None,
        actor: str = "Inside Sales",
        _defer_processing: bool = False,
        _existing_case_id: Optional[str] = None,
        _job_id: Optional[str] = None,
        _worker_id: Optional[str] = None,
        _queue_wait_ms: Optional[float] = None,
    ) -> RFQCase:
        """Validates, stores, parses, and matches an uploaded RFQ document.

        The underscored options are internal worker hooks: defer leaves a durable
        PROCESSING case for the queue; existing_case_id resumes that exact case.
        """
        total_started = time.perf_counter()
        timings = {"validate_ms": 0.0, "store_ms": 0.0, "parse_ms": 0.0, "llm_ms": 0.0, "match_ms": 0.0}
        if _queue_wait_ms is not None:
            timings["queue_wait_ms"] = max(0.0, float(_queue_wait_ms))
        if bool(_job_id) != bool(_worker_id):
            raise ValueError("Both ingestion job ID and worker ID are required for a fenced processing attempt.")

        def require_lease() -> None:
            if (
                _job_id
                and self.state_store
                and (
                    not _worker_id
                    or not self.state_store.owns_ingestion_job(_job_id, _worker_id)
                )
            ):
                raise IngestionLeaseLostError("This worker no longer owns the RFQ processing lease.")

        stage_started = time.perf_counter()
        clean_name, src_type, digest = validate_file_upload(filename, content)
        self._validate_intake_regions(clean_name, src_type, content)
        timings["validate_ms"] = (time.perf_counter() - stage_started) * 1000
        if _existing_case_id:
            case_id = _existing_case_id
            case = self._cases.get(case_id)
            if case is None:
                raise DocumentParserError("The queued RFQ case no longer exists.")
            if case.status != CaseStatus.PROCESSING:
                return case
            if not case.source_file or case.source_file.sha256_digest != digest:
                raise DocumentParserError("Stored upload digest does not match the queued RFQ source.")
        else:
            case_id = f"RFQ-{uuid.uuid4().hex[:8].upper()}"
            stage_started = time.perf_counter()
            self.storage.save_file(case_id, clean_name, content)
            timings["store_ms"] = (time.perf_counter() - stage_started) * 1000
            file_meta = SourceFileMetadata(
                file_id=f"file-{uuid.uuid4().hex[:6]}",
                file_name=clean_name,
                source_type=src_type,
                mime_type="application/octet-stream",
                size_bytes=len(content),
                sha256_digest=digest,
            )
            case = RFQCase(
                case_id=case_id,
                title=title or f"RFQ Intake - {clean_name}",
                customer_label=customer_label,
                status=CaseStatus.PROCESSING,
                source_type=src_type,
                source_file=file_meta,
            )
            self._cases[case_id] = case
            self._audit_events[case_id] = []
            self._record_audit(
                case_id=case_id,
                actor=actor,
                action=AuditAction.CASE_CREATED,
                notes=f"Uploaded document '{clean_name}' (SHA256: {digest[:8]}...)",
            )

        if _defer_processing:
            self._persist_case(case_id)
            return case

        try:
            require_lease()
            # Parse document
            parser = get_parser(src_type)
            parser_profile = {
                **parser.cache_profile(),
                "source_type": src_type.value,
                "source_segmenter_version": "source-segments-v1",
            }
            dependencies = parser.cache_dependencies if src_type != SourceType.CSV else ()
            for package_name in dependencies:
                try:
                    parser_profile.setdefault("dependencies", {})[package_name] = package_metadata.version(package_name)
                except package_metadata.PackageNotFoundError:
                    continue
            profile_digest = hashlib.sha256(
                json.dumps(parser_profile, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            case.parser_version = str(parser_profile["version"])
            case.processing_profile_sha256 = profile_digest
            cached_parse = None
            if _existing_case_id and self.state_store:
                cached_parse = self.state_store.load_processing_artifact(
                    case_id, "parsed_document", digest, profile_digest
                )
            case.parse_cache_hit = cached_parse is not None
            stage_started = time.perf_counter()
            if cached_parse is not None:
                parse_result = ParsedDocumentResult.model_validate(cached_parse)
                case.parse_cache_hit = True
            else:
                try:
                    parse_result = parser.parse(content, clean_name)
                finally:
                    timings["parse_ms"] = (time.perf_counter() - stage_started) * 1000
                if _existing_case_id and self.state_store:
                    require_lease()
                    self.state_store.save_processing_artifact(
                        case_id, "parsed_document", digest, profile_digest,
                        parse_result.model_dump(mode="json"),
                        job_id=_job_id, worker_id=_worker_id,
                    )
            if case.parse_cache_hit:
                timings["parse_ms"] = (time.perf_counter() - stage_started) * 1000
            require_lease()
            if self.llm_extractor and self._needs_llm_fallback(parse_result):
                case.llm_cache_hit = False
                stage_started = time.perf_counter()
                try:
                    require_lease()
                    segments = self._llm_segments(
                        parse_result.lines, content, clean_name, src_type,
                        parse_result.evidence_segments,
                        parse_result.candidate_segments,
                    )
                    cache_profile_fn = getattr(self.llm_extractor, "cache_profile", None)
                    llm_profile = cache_profile_fn() if callable(cache_profile_fn) else None
                    llm_profile_digest = None
                    if llm_profile:
                        llm_profile_digest = hashlib.sha256(json.dumps({
                            "profile": llm_profile,
                            "segments": [segment.model_dump(mode="json") for segment in segments],
                        }, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
                    cached_llm = None
                    if llm_profile_digest and _existing_case_id and self.state_store:
                        cached_llm = self.state_store.load_processing_artifact(
                            case_id, "llm_result", digest, llm_profile_digest
                        )
                    llm_result = (
                        ParsedDocumentResult.model_validate(cached_llm)
                        if cached_llm is not None else self.llm_extractor.extract(segments)
                    )
                    require_lease()
                    case.llm_cache_hit = cached_llm is not None
                    previous_llm_calls = case.llm_call_count
                    case.llm_model = llm_result.llm_model
                    case.llm_deployment_version = llm_result.llm_deployment_version
                    case.llm_prompt_sha256 = llm_result.llm_prompt_sha256
                    case.llm_schema_version = LLM_SCHEMA_VERSION
                    case.llm_validator_version = LLM_VALIDATOR_VERSION
                    if cached_llm is None:
                        case.llm_call_count += llm_result.llm_call_count
                        case.llm_repair_call_count += llm_result.llm_repair_call_count
                        case.llm_review_call_count += llm_result.llm_review_call_count
                        if llm_result.llm_input_tokens is None:
                            case.llm_input_tokens = None
                        elif previous_llm_calls == 0:
                            case.llm_input_tokens = llm_result.llm_input_tokens
                        elif case.llm_input_tokens is not None:
                            case.llm_input_tokens += llm_result.llm_input_tokens
                        if llm_result.llm_output_tokens is None:
                            case.llm_output_tokens = None
                        elif previous_llm_calls == 0:
                            case.llm_output_tokens = llm_result.llm_output_tokens
                        elif case.llm_output_tokens is not None:
                            case.llm_output_tokens += llm_result.llm_output_tokens
                    elif previous_llm_calls == 0:
                        # Recover telemetry if a crash happened after the
                        # artifact write but before the case snapshot.
                        case.llm_call_count = llm_result.llm_call_count
                        case.llm_repair_call_count = llm_result.llm_repair_call_count
                        case.llm_review_call_count = llm_result.llm_review_call_count
                        case.llm_input_tokens = llm_result.llm_input_tokens
                        case.llm_output_tokens = llm_result.llm_output_tokens
                    timings["llm_ms"] = (time.perf_counter() - stage_started) * 1000
                    case.stage_timings_ms = dict(timings)
                    self._persist_case(case_id, job_id=_job_id, worker_id=_worker_id)
                    if (cached_llm is None and llm_profile_digest and self.state_store
                            and llm_result.lines
                            and not any(w.severity.lower() == "error" for w in llm_result.warnings)
                            and not any(w.code == "LLM_VALIDATION_UNAVAILABLE"
                                        for line in llm_result.lines for w in line.extraction_warnings)):
                        require_lease()
                        self.state_store.save_processing_artifact(
                            case_id, "llm_result", digest, llm_profile_digest,
                            llm_result.model_dump(mode="json"),
                            job_id=_job_id, worker_id=_worker_id,
                        )
                    if llm_result.lines or parse_result.candidate_segments:
                        parse_result = self._merge_llm_proposals(
                            parse_result, llm_result, parse_result.candidate_segments
                        )
                    elif parse_result.lines:
                        # Preserve deterministic rows and surface the model
                        # failure on unresolved rows; never silently downgrade.
                        for draft in parse_result.lines:
                            if self._draft_needs_llm(draft):
                                draft.extraction_warnings.extend(llm_result.warnings)
                    else:
                        parse_result.warnings.extend(llm_result.warnings)
                except Exception:
                    # Provider/network failures do not discard deterministic
                    # output. Unresolved rows remain flagged for manual work.
                    warning = ExtractionWarning(
                        code="LLM_FALLBACK_UNAVAILABLE",
                        message="The extraction assistant could not be reached. Verify unresolved fields against the original source.",
                        severity="warning",
                    )
                    if parse_result.candidate_segments:
                        failed = ParsedDocumentResult(lines=[], warnings=[warning])
                        parse_result = self._merge_llm_proposals(
                            parse_result, failed, parse_result.candidate_segments
                        )
                    else:
                        for draft in parse_result.lines:
                            if self._draft_needs_llm(draft):
                                draft.extraction_warnings.append(warning)
                    if not parse_result.lines:
                        parse_result.warnings.append(warning)
                finally:
                    timings["llm_ms"] = (time.perf_counter() - stage_started) * 1000
            elif parse_result.candidate_segments:
                # Never silently discard a non-empty source region that the
                # deterministic parser could not classify. Without an enabled
                # model, preserve it as a human-review exception.
                parse_result = self._merge_llm_proposals(
                    parse_result,
                    ParsedDocumentResult(lines=[]),
                    parse_result.candidate_segments,
                )
            case.source_coverage = parse_result.source_coverage
            # A "successful" empty RFQ is worse than an explicit parse failure:
            # operators might otherwise export an empty worksheet as complete.
            if not parse_result.lines:
                raise DocumentParserError(
                    "No RFQ line items could be extracted. Please correct the document or paste items manually.",
                    source_coverage=parse_result.source_coverage,
                )
            fatal_warnings = [w for w in parse_result.warnings if w.severity.lower() == "error"]
            if fatal_warnings:
                raise DocumentParserError(
                    "Document extraction failed: " + "; ".join(w.message for w in fatal_warnings),
                    source_coverage=parse_result.source_coverage,
                )
            require_lease()
            case.document_warnings = parse_result.warnings

            # Match lines against catalog
            lines: List[RFQLineItem] = []
            stage_started = time.perf_counter()
            for draft in parse_result.lines:
                line_id = f"line-{uuid.uuid4().hex[:8]}"
                match_res = self.matcher.match_line(draft.requested_mpn, draft.requested_manufacturer)

                reviewable_warnings = [
                    warning for warning in draft.extraction_warnings
                    if warning.code != "LLM_PROPOSED_EXTRACTION"
                ]
                extract_status = (
                    ExtractionStatus.NEEDS_CORRECTION
                    if reviewable_warnings or draft.quantity is None
                    else ExtractionStatus.EXTRACTED
                )

                line_item = RFQLineItem(
                    line_id=line_id,
                    case_id=case_id,
                    line_number=draft.line_number,
                    raw_text=draft.raw_text,
                    source_locator=draft.source_locator,
                    requested_manufacturer=draft.requested_manufacturer,
                    requested_mpn=draft.requested_mpn,
                    description=draft.description,
                    quantity=draft.quantity,
                    unit=draft.unit,
                    notes=draft.notes,
                    extraction_status=extract_status,
                    extraction_warnings=draft.extraction_warnings,
                    match_status=match_res.match_status,
                    selected_catalog_sku=match_res.selected_sku,
                    candidates=match_res.candidates,
                    review_decision=ReviewDecision.PENDING,
                )
                lines.append(line_item)
            timings["match_ms"] = (time.perf_counter() - stage_started) * 1000

            self._lines_by_case[case_id] = lines
            self._record_audit(
                case_id=case_id,
                actor=actor,
                action=AuditAction.PARSED,
                notes=f"Extracted {len(lines)} line items with {len(parse_result.warnings)} document-level warnings.",
            )

            self._refresh_case_metrics(case_id, job_id=_job_id, worker_id=_worker_id)
            case.stage_timings_ms = dict(timings)
            self._persist_case(case_id, job_id=_job_id, worker_id=_worker_id)
            log.info(
                "[rfq_timing] source_type=%s outcome=parsed lines=%d queue_wait_ms=%.1f validate_ms=%.1f store_ms=%.1f parse_ms=%.1f llm_ms=%.1f match_ms=%.1f total_ms=%.1f",
                src_type.value, len(lines), timings.get("queue_wait_ms", 0.0),
                timings["validate_ms"], timings["store_ms"], timings["parse_ms"],
                timings["llm_ms"], timings["match_ms"],
                (time.perf_counter() - total_started) * 1000,
            )
            return self._cases[case_id]
        except DocumentParserError as exc:
            # Keep the original upload and a failed case so a reviewer can
            # inspect it or use the manual-entry path after OCR/model/parser
            # failures. Do not turn a processing failure into a lost upload.
            failed_case = self._cases[case_id]
            failed_case.status = CaseStatus.FAILED
            failed_case.source_coverage = exc.source_coverage or failed_case.source_coverage or [SourceCoverageUnit(
                unit_id="document",
                locator=SourceLocator(file_name=clean_name),
                unit_kind="document",
                processing_status="failed",
                error_code="DOCUMENT_PARSER_ERROR",
            )]
            failed_case.document_warnings.append(ExtractionWarning(
                code="DOCUMENT_EXTRACTION_FAILED",
                message=str(exc),
                severity="error",
            ))
            failed_case.stage_timings_ms = dict(timings)
            self._lines_by_case[case_id] = []
            self._record_audit(
                case_id=case_id,
                actor=actor,
                action=AuditAction.PARSED,
                notes="Document extraction failed; original upload retained for manual review.",
            )
            self._persist_case(case_id, job_id=_job_id, worker_id=_worker_id)
            log.info(
                "[rfq_timing] source_type=%s outcome=failed queue_wait_ms=%.1f validate_ms=%.1f store_ms=%.1f parse_ms=%.1f llm_ms=%.1f total_ms=%.1f",
                src_type.value, timings.get("queue_wait_ms", 0.0), timings["validate_ms"],
                timings["store_ms"], timings["parse_ms"], timings["llm_ms"],
                (time.perf_counter() - total_started) * 1000,
            )
            return failed_case
        except Exception:
            # Preserve the original for unexpected parser/provider failures. A
            # queued attempt may be retried; direct callers receive a visible
            # failed case rather than losing the RFQ bytes.
            if _existing_case_id:
                raise
            failed_case = self._cases[case_id]
            failed_case.status = CaseStatus.FAILED
            if not failed_case.source_coverage:
                failed_case.source_coverage = [SourceCoverageUnit(
                    unit_id="document",
                    locator=SourceLocator(file_name=clean_name),
                    unit_kind="document",
                    processing_status="failed",
                    error_code="PROCESSING_UNEXPECTED_ERROR",
                )]
            failed_case.document_warnings.append(ExtractionWarning(
                code="PROCESSING_UNEXPECTED_ERROR",
                message="The document could not be processed safely. The original upload is retained for manual review.",
                severity="error",
            ))
            failed_case.stage_timings_ms = dict(timings)
            self._lines_by_case[case_id] = []
            self._record_audit(case_id, actor, AuditAction.PARSED, notes="Unexpected processing failure; original upload retained.")
            self._persist_case(case_id, job_id=_job_id, worker_id=_worker_id)
            log.exception("[rfq_timing] processing failed unexpectedly case_id=%s", case_id)
            return failed_case

    def enqueue_case_from_upload(
        self, filename: str, content: bytes, title: Optional[str] = None,
        customer_label: Optional[str] = None, actor: str = "Inside Sales",
    ) -> RFQCase:
        """Persist the source and case immediately, then enqueue durable processing."""
        if self.state_store is None:
            raise RuntimeError("Asynchronous RFQ processing requires the SQLite state store.")
        case = self.create_case_from_upload(
            filename, content, title=title, customer_label=customer_label,
            actor=actor, _defer_processing=True,
        )
        self.state_store.enqueue_ingestion_job(case.case_id, case.source_file.sha256_digest)
        return case

    def enqueue_case_from_text(
        self, raw_text: str, title: Optional[str] = None,
        customer_label: Optional[str] = None, actor: str = "Inside Sales",
    ) -> RFQCase:
        """Durably store pasted email text as a case-scoped source before queueing it."""
        content = self._preflight_text_input(raw_text)
        case = self.enqueue_case_from_upload(
            "pasted_inquiry.txt", content, title=title or "RFQ Intake - Pasted Email",
            customer_label=customer_label, actor=actor,
        )
        case.source_type = SourceType.EMAIL_TEXT
        case.raw_text = raw_text
        self._persist_case(case.case_id)
        return case

    def process_pending_case(
        self, case_id: str, *, job_id: str, worker_id: str,
        queue_wait_ms: Optional[float] = None,
    ) -> RFQCase:
        """Resume a persisted case only while its state is still PROCESSING."""
        with self._processing_locks_guard:
            case_lock = self._processing_locks.setdefault(case_id, threading.Lock())
        # A job can be reclaimed after a lease expires while its old parser is
        # still unwinding. Serialize the case in memory, then recheck ownership
        # before starting or committing the second attempt.
        with case_lock:
            if self.state_store and not self.state_store.owns_ingestion_job(job_id, worker_id):
                raise IngestionLeaseLostError("This worker no longer owns the RFQ processing lease.")
            return self._process_pending_case_locked(
                case_id, job_id=job_id, worker_id=worker_id,
                queue_wait_ms=queue_wait_ms,
            )

    def _process_pending_case_locked(
        self, case_id: str, *, job_id: str, worker_id: str,
        queue_wait_ms: Optional[float] = None,
    ) -> RFQCase:
        case = self._cases.get(case_id)
        if case is None or not case.source_file:
            raise DocumentParserError("Queued RFQ source is missing.")
        if case.status != CaseStatus.PROCESSING:
            return case
        content = self.storage.get_file(case_id, case.source_file.file_name)
        if content is None:
            raise DocumentParserError("Queued RFQ upload is missing from local storage.")
        result = self.create_case_from_upload(
            filename=case.source_file.file_name,
            content=content,
            title=case.title,
            customer_label=case.customer_label,
            actor="RFQ ingestion worker",
            _existing_case_id=case_id,
            _job_id=job_id,
            _worker_id=worker_id,
            _queue_wait_ms=queue_wait_ms,
        )
        if result.source_type == SourceType.EMAIL_TEXT:
            result.raw_text = content.decode("utf-8", errors="replace")
            self._persist_case(case_id, job_id=job_id, worker_id=worker_id)
        return result

    def mark_case_processing_failed(self, case_id: str, error_code: str = "WORKER_RETRIES_EXHAUSTED") -> None:
        case = self._cases.get(case_id)
        if case is None or case.status != CaseStatus.PROCESSING:
            return
        case.status = CaseStatus.FAILED
        case.document_warnings.append(ExtractionWarning(
            code=error_code,
            message="Background document processing stopped after its retry limit. The original upload is retained for manual review.",
            severity="error",
        ))
        self._lines_by_case[case_id] = []
        self._record_audit(case_id, "RFQ ingestion worker", AuditAction.PARSED,
                           notes="Background processing stopped; source retained for manual review.")
        self._persist_case(case_id)

    @staticmethod
    def _draft_needs_llm(draft) -> bool:
        return not draft.requested_mpn or not draft.requested_manufacturer or draft.quantity is None

    @classmethod
    def _needs_llm_fallback(cls, parse_result) -> bool:
        return (
            not parse_result.lines
            or bool(parse_result.candidate_segments)
            or any(cls._draft_needs_llm(draft) for draft in parse_result.lines)
        )

    @staticmethod
    def _llm_segments(
        drafts, content: bytes, filename: str, source_type: SourceType,
        evidence_segments: Optional[List[EvidenceSegment]] = None,
        candidate_segments: Optional[List[EvidenceSegment]] = None,
    ) -> List[EvidenceSegment]:
        if not drafts:
            if candidate_segments:
                return candidate_segments
            if evidence_segments:
                return evidence_segments
            return source_segments(content, filename, source_type)
        # Send only uncertain rows to the model. This limits latency and data
        # disclosure while preserving the exact row/page location.
        unresolved = [
            EvidenceSegment(
                segment_id=f"draft-line-{draft.line_number}",
                locator=draft.source_locator,
                text=draft.raw_text,
            )
            for draft in drafts if CaseManager._draft_needs_llm(draft)
        ]
        return [*unresolved, *(candidate_segments or [])]

    @staticmethod
    def _merge_llm_proposals(parse_result, llm_result, candidate_segments=None):
        output = []
        candidate_segments = candidate_segments or []
        candidates_by_id = {segment.segment_id: segment for segment in candidate_segments}
        represented_candidates = set()
        repair_warning = next(
            (warning for warning in llm_result.warnings if warning.code == "LLM_REPAIR_USED"),
            None,
        )
        drafts_by_segment = {
            f"draft-line-{draft.line_number}": draft for draft in parse_result.lines
        }
        for proposal in llm_result.lines:
            if repair_warning:
                proposal.extraction_warnings.append(repair_warning.model_copy(deep=True))
            target = drafts_by_segment.get(proposal.source_segment_id or "")
            if target is not None:
                for field in ("requested_mpn", "requested_manufacturer", "description", "quantity", "unit"):
                    if getattr(target, field) in (None, "") and getattr(proposal, field) not in (None, ""):
                        setattr(target, field, getattr(proposal, field))
                target.extraction_warnings.extend(proposal.extraction_warnings)
            elif proposal.source_segment_id in candidates_by_id:
                proposal.line_number = max(
                    [draft.line_number for draft in parse_result.lines] +
                    [draft.line_number for draft in output] + [0]
                ) + 1
                output.append(proposal)
                represented_candidates.add(proposal.source_segment_id)
            elif parse_result.lines:
                # A focused fallback cannot create a duplicate row when its
                # evidence quote does not map back to the unresolved source row.
                continue
            else:
                # Whole-document fallback: model lines are accepted only with
                # verified source quotes and retain the LLM review warning.
                output.append(proposal)
        for segment in candidate_segments:
            if segment.segment_id in represented_candidates:
                continue
            next_line_number = max(
                [draft.line_number for draft in parse_result.lines] +
                [draft.line_number for draft in output] + [0]
            ) + 1
            output.append(ParsedLineDraft(
                line_number=next_line_number,
                raw_text=segment.text,
                source_locator=segment.locator.model_copy(
                    update={"text_snippet": segment.text[:120]}
                ),
                unit="EA",
                extraction_warnings=[
                    *[warning.model_copy(deep=True) for warning in segment.warnings],
                    *[warning.model_copy(deep=True) for warning in llm_result.warnings],
                    ExtractionWarning(
                        code="SOURCE_REGION_UNCLASSIFIED",
                        message="This non-empty source region was not confidently converted into a line item. Review it against the original before exporting.",
                        severity="warning",
                    ),
                ],
            ))
            parse_result.warnings.append(ExtractionWarning(
                code="SOURCE_COVERAGE_REQUIRES_REVIEW",
                message="One or more non-empty source regions could not be classified automatically and were added to the individual review list.",
                severity="warning",
            ))
        parse_result.lines.extend(output)
        if parse_result.lines:
            # Parsers may report that deterministic extraction found no rows
            # before the grounded fallback has processed candidate regions.
            # Once those regions are either recovered or retained for review,
            # that earlier empty-result error is stale.
            parse_result.warnings = [
                warning for warning in parse_result.warnings
                if warning.code != "NO_LINES_EXTRACTED"
            ]
        # A failed LLM fallback is attached to unresolved/coverage rows, but it
        # must not erase structured rows that already passed deterministic
        # extraction. Whole-document failure remains visible when no rows exist.
        parse_result.warnings.extend(
            warning for warning in llm_result.warnings
            if warning.severity.lower() != "error" or not parse_result.lines
        )
        parse_result.total_lines_detected = len(parse_result.lines)
        return parse_result


    def create_case_from_text(
        self,
        raw_text: str,
        title: Optional[str] = None,
        customer_label: Optional[str] = None,
        actor: str = "Inside Sales",
    ) -> RFQCase:
        """Parses and matches plain pasted email or inquiry text."""
        content = self._preflight_text_input(raw_text)
        case = self.create_case_from_upload(
            filename="pasted_inquiry.txt",
            content=content,
            title=title or "RFQ Intake - Pasted Email",
            customer_label=customer_label,
            actor=actor,
        )
        case.source_type = SourceType.EMAIL_TEXT
        case.raw_text = raw_text
        self._persist_case(case.case_id)
        return case

    @staticmethod
    def _preflight_text_input(raw_text: str) -> bytes:
        """Reject empty, oversized, or header-only pasted input before persistence."""
        content = raw_text.encode("utf-8")
        if not raw_text.strip():
            raise DocumentParserError("Pasted RFQ text is empty. Add inquiry text or line items before creating a case.")
        validate_file_upload("pasted_inquiry.txt", content)
        parsed = get_parser(SourceType.EMAIL_TEXT).parse(content, "pasted_inquiry.txt")
        nonempty_regions = [line for line in raw_text.splitlines() if line.strip()]
        if len(nonempty_regions) > MAX_TEXT_INTAKE_REGIONS:
            raise DocumentParserError(
                f"This RFQ contains more than {MAX_TEXT_INTAKE_REGIONS} non-empty text regions. Split it into smaller requests."
            )
        if parsed.lines or not parsed.candidate_segments:
            return content

        def looks_like_header(text: str) -> bool:
            normalized = text.strip()
            for delimiter in ("|", ",", ";", "\t"):
                if delimiter in normalized:
                    mapping = identify_columns([part.strip() for part in normalized.split(delimiter)])
                    if "mpn" in mapping and len(mapping) >= 2:
                        return True
            return False

        if all(looks_like_header(segment.text) for segment in parsed.candidate_segments):
            raise DocumentParserError("The pasted text contains only table headers. Add at least one item row.")
        return content

    @staticmethod
    def _validate_intake_regions(filename: str, source_type: SourceType, content: bytes) -> None:
        """Reject clearly empty or unbounded intake before writing case state/files."""
        if source_type == SourceType.EMAIL_TEXT:
            text = content.decode("utf-8", errors="replace")
            regions = [line for line in text.splitlines() if line.strip()]
            if not regions:
                raise DocumentParserError("Pasted RFQ text is empty. Add non-whitespace content before creating a case.")
            if len(regions) > MAX_TEXT_INTAKE_REGIONS:
                raise DocumentParserError(
                    f"This RFQ contains more than {MAX_TEXT_INTAKE_REGIONS} non-empty text regions. Split it into smaller requests."
                )
        elif filename.lower().endswith(".csv"):
            try:
                rows = [row for row in csv.reader(StringIO(content.decode("utf-8-sig"))) if any(cell.strip() for cell in row)]
            except (UnicodeDecodeError, csv.Error) as exc:
                raise DocumentParserError("CSV could not be read safely. Check its encoding and contents.") from exc
            if len(rows) == 1 and any(token in " ".join(rows[0]).lower() for token in ("mpn", "part number", "manufacturer", "quantity", "qty", "description")):
                raise DocumentParserError("This CSV contains headers but no RFQ line items.")
        elif filename.lower().endswith(".xlsx"):
            workbook = load_workbook(BytesIO(content), read_only=True, data_only=False)
            nonempty_rows = 0
            header_rows = 0
            header_terms = ("mpn", "part number", "manufacturer", "quantity", "qty", "description")
            try:
                for worksheet in workbook.worksheets:
                    first_content_row = True
                    for row in worksheet.iter_rows(values_only=True):
                        values = [str(value).strip() for value in row if value is not None and str(value).strip()]
                        if not values:
                            continue
                        nonempty_rows += 1
                        if first_content_row:
                            first_content_row = False
                            if any(term in " ".join(values).lower() for term in header_terms):
                                header_rows += 1
            finally:
                workbook.close()
            if not nonempty_rows:
                raise DocumentParserError("This spreadsheet contains no non-empty cells.")
            if header_rows and nonempty_rows == header_rows:
                raise DocumentParserError("This workbook contains headers but no RFQ line items.")

    def update_line(
        self, case_id: str, line_id: str, update: RFQLineItemUpdate
    ) -> Optional[RFQLineItem]:
        """Applies a human reviewer edit or decision to a line item with full audit trail."""
        lines = self._lines_by_case.get(case_id, [])
        line = next((l for l in lines if l.line_id == line_id), None)
        if not line:
            return None

        # Optimistic concurrency check
        if update.expected_version != line.version:
            raise ValueError(
                f"Stale state / conflict: Line item version is {line.version}, but client expected version {update.expected_version}. Please refresh."
            )

        material_changes = []

        # Validate quantity strictly
        if update.quantity is not None:
            import math
            try:
                q_val = float(update.quantity)
            except (ValueError, TypeError):
                raise ValueError(f"Quantity must be a numeric value, got '{update.quantity}'")
            if math.isnan(q_val) or math.isinf(q_val):
                raise ValueError(f"Quantity cannot be NaN or Infinite: {update.quantity}")
            if q_val <= 0:
                raise ValueError(f"Quantity must be strictly positive (> 0), got {update.quantity}")

            if update.quantity != line.quantity:
                material_changes.append("quantity")
                self._record_audit(
                    case_id=case_id,
                    line_id=line_id,
                    actor=update.actor,
                    action=AuditAction.LINE_EDITED,
                    field_name="quantity",
                    old_value=str(line.quantity),
                    new_value=str(update.quantity),
                    notes=update.reviewer_notes,
                )
                line.quantity = update.quantity
                # Clear missing quantity warning if fixed
                line.extraction_warnings = [w for w in line.extraction_warnings if w.code != "MISSING_QUANTITY"]

        if update.requested_mpn is not None and update.requested_mpn != line.requested_mpn:
            material_changes.append("requested_mpn")
            self._record_audit(
                case_id=case_id,
                line_id=line_id,
                actor=update.actor,
                action=AuditAction.LINE_EDITED,
                field_name="requested_mpn",
                old_value=line.requested_mpn,
                new_value=update.requested_mpn,
            )
            line.requested_mpn = update.requested_mpn
            # Re-match against catalog
            rematch = self.matcher.match_line(line.requested_mpn, line.requested_manufacturer)
            line.match_status = rematch.match_status
            line.selected_catalog_sku = rematch.selected_sku
            line.candidates = rematch.candidates

        if update.requested_manufacturer is not None and update.requested_manufacturer != line.requested_manufacturer:
            material_changes.append("requested_manufacturer")
            self._record_audit(
                case_id=case_id,
                line_id=line_id,
                actor=update.actor,
                action=AuditAction.LINE_EDITED,
                field_name="requested_manufacturer",
                old_value=line.requested_manufacturer,
                new_value=update.requested_manufacturer,
            )
            line.requested_manufacturer = update.requested_manufacturer
            rematch = self.matcher.match_line(line.requested_mpn, line.requested_manufacturer)
            line.match_status = rematch.match_status
            line.selected_catalog_sku = rematch.selected_sku
            line.candidates = rematch.candidates

        if update.selected_catalog_sku is not None and update.selected_catalog_sku != line.selected_catalog_sku:
            material_changes.append("selected_catalog_sku")
            self._record_audit(
                case_id=case_id,
                line_id=line_id,
                actor=update.actor,
                action=AuditAction.LINE_EDITED,
                field_name="selected_catalog_sku",
                old_value=line.selected_catalog_sku,
                new_value=update.selected_catalog_sku,
            )
            line.selected_catalog_sku = update.selected_catalog_sku
            line.match_status = MatchStatus.MANUAL_OVERRIDE

        if update.unit is not None and update.unit != line.unit:
            material_changes.append("unit")
            line.unit = update.unit

        if update.description is not None and update.description != line.description:
            material_changes.append("description")
            line.description = update.description

        if update.notes is not None and update.notes != line.notes:
            material_changes.append("notes")
            line.notes = update.notes

        # Contradiction check: verify selected SKU against requested OEM
        if line.selected_catalog_sku:
            cat_item = self.catalog.get_by_sku(line.selected_catalog_sku)
            if cat_item and line.requested_manufacturer:
                req_oem = line.requested_manufacturer.strip().lower()
                cat_oem = cat_item.manufacturer.strip().lower()
                if req_oem not in cat_oem and cat_oem not in req_oem:
                    # Remove any existing contradiction warning then add high severity alert
                    line.extraction_warnings = [w for w in line.extraction_warnings if w.code != "CONTRADICTION"]
                    line.extraction_warnings.append(
                        ExtractionWarning(
                            code="CONTRADICTION",
                            message=(
                                f"Selected SKU '{line.selected_catalog_sku}' ({cat_item.manufacturer}) "
                                f"contradicts requested manufacturer '{line.requested_manufacturer}'."
                            ),
                            severity="error",
                        )
                    )

                else:
                    line.extraction_warnings = [w for w in line.extraction_warnings if w.code != "CONTRADICTION"]

        # Invariant: If line was previously approved and any material field was changed,
        # approval is revoked unless the update explicitly re-approves with APPROVED.
        if line.review_decision == ReviewDecision.APPROVED and material_changes:
            if update.review_decision != ReviewDecision.APPROVED:
                self._record_audit(
                    case_id=case_id,
                    line_id=line_id,
                    actor=update.actor,
                    action=AuditAction.LINE_FLAGGED,
                    field_name="review_decision",
                    old_value=ReviewDecision.APPROVED.value,
                    new_value=ReviewDecision.PENDING.value,
                    notes=f"Material changes to {', '.join(material_changes)} invalidated prior approval. Re-approval required.",
                )
                line.review_decision = ReviewDecision.PENDING
                line.reviewed_by = None
                line.reviewed_at = None

        if update.review_decision is not None and update.review_decision != line.review_decision:
            action_map = {
                ReviewDecision.APPROVED: AuditAction.LINE_APPROVED,
                ReviewDecision.REJECTED: AuditAction.LINE_REJECTED,
                ReviewDecision.NEEDS_CLARIFICATION: AuditAction.LINE_FLAGGED,
            }
            self._record_audit(
                case_id=case_id,
                line_id=line_id,
                actor=update.actor,
                action=action_map.get(update.review_decision, AuditAction.LINE_EDITED),
                field_name="review_decision",
                old_value=line.review_decision.value,
                new_value=update.review_decision.value,
                notes=update.reviewer_notes,
            )
            line.review_decision = update.review_decision
            line.reviewed_by = update.actor
            line.reviewed_at = datetime.utcnow()

        if update.reviewer_notes is not None:
            line.reviewer_notes = update.reviewer_notes

        line.version += 1
        self._refresh_case_metrics(case_id)
        return line


    def batch_review(self, case_id: str, request: BatchReviewRequest) -> int:
        """Batch decisions are limited to the server-selected clean sample."""
        if request.decision == ReviewDecision.APPROVED:
            plan = self.get_review_plan(case_id)
            allowed = set(plan.sample_line_ids)
            if not set(request.line_ids) <= allowed:
                raise ValueError(
                    "Batch approval may only cover the current review sample. Review exceptions individually."
                )
        updated = 0
        for lid in request.line_ids:
            line = next((item for item in self.get_lines(case_id) if item.line_id == lid), None)
            if line is None:
                continue
            upd = RFQLineItemUpdate(
                expected_version=line.version,
                review_decision=request.decision,
                actor=request.actor,
                reviewer_notes=request.notes,
            )
            if self.update_line(case_id, lid, upd):
                updated += 1
        return updated

    @staticmethod
    def _is_sample_eligible(line: RFQLineItem, catalog: CatalogRepository) -> bool:
        """Rows may enter the sample only after deterministic evidence gates pass."""
        try:
            quantity_ok = line.quantity is not None and math.isfinite(float(line.quantity)) and line.quantity > 0
        except (TypeError, ValueError, OverflowError):
            quantity_ok = False
        if not quantity_ok or not line.unit or not line.unit.strip():
            return False
        if not line.requested_mpn or not line.requested_manufacturer:
            return False
        if line.match_status != MatchStatus.EXACT_MATCH or not line.selected_catalog_sku:
            return False
        if catalog.get_by_sku(line.selected_catalog_sku) is None:
            return False
        if line.extraction_status != ExtractionStatus.EXTRACTED:
            return False
        # A schema- and source-grounded model proposal is eligible for sampling;
        # OCR, guessed layouts, formulas, and unresolved warnings remain exceptions.
        return all(w.code == "LLM_PROPOSED_EXTRACTION" for w in line.extraction_warnings)

    @staticmethod
    def _sample_group(line: RFQLineItem) -> str:
        locator = line.source_locator
        location = locator.sheet_name or (f"page-{locator.page_number}" if locator.page_number else "text")
        extraction_path = (
            "llm" if any(w.code == "LLM_PROPOSED_EXTRACTION" for w in line.extraction_warnings)
            else "structured"
        )
        return f"{extraction_path}|{location}"

    def get_review_plan(self, case_id: str) -> ReviewPlan:
        case = self._cases.get(case_id)
        if case is None:
            raise ValueError("RFQ case not found.")
        lines = self._lines_by_case.get(case_id, [])
        eligible = [line for line in lines if self._is_sample_eligible(line, self.catalog)]
        eligible_ids = {line.line_id for line in eligible}

        sample_size = min(5, len(eligible))
        groups: Dict[str, List[RFQLineItem]] = {}
        for line in eligible:
            groups.setdefault(self._sample_group(line), []).append(line)
        for group_lines in groups.values():
            # Rank rows by a per-case pseudorandom key. The case ID is freshly
            # generated for each intake, so separate RFQs get different samples;
            # the ranking stays fixed while this case is reviewed. This avoids
            # repeatedly sampling only the middle rows of similarly shaped files.
            group_lines.sort(key=lambda line: hashlib.sha256(
                f"{case.case_id}:{line.line_id}".encode("utf-8")
            ).digest())

        # Allocate at least one sample to every location/path stratum where
        # possible; distribute remaining picks across larger strata.
        group_keys = sorted(groups)
        allocation = {key: 0 for key in group_keys}
        if len(group_keys) <= sample_size:
            for key in group_keys:
                allocation[key] = 1
            while sum(allocation.values()) < sample_size:
                available = [key for key in group_keys if allocation[key] < len(groups[key])]
                if not available:
                    break
                key = max(available, key=lambda item: (len(groups[item]) / (allocation[item] + 1), item))
                allocation[key] += 1
        elif sample_size:
            # More strata than slots: spread picks across the stable stratum order.
            indexes = [min(len(group_keys) - 1, int((slot + 0.5) * len(group_keys) / sample_size))
                       for slot in range(sample_size)]
            for index in indexes:
                allocation[group_keys[index]] = 1

        sample_ids: List[str] = []
        covered_group_keys = {key for key, count in allocation.items() if count > 0}
        covered_eligible_ids = {
            line.line_id
            for key in covered_group_keys
            for line in groups[key]
        }
        for key in group_keys:
            group_lines = groups[key]
            count = allocation[key]
            sample_ids.extend(line.line_id for line in group_lines[:count])
        sample_ids = sample_ids[:sample_size]
        # A clean row from a source stratum that could not fit into the five
        # sample slots has not been represented by the sample. Keep those rows
        # as individual-review exceptions instead of silently batch-approving
        # an unseen extraction path/location.
        exceptions = [
            line.line_id for line in lines
            if line.line_id not in eligible_ids or line.line_id not in covered_eligible_ids
        ]
        lines_by_id = {line.line_id: line for line in eligible}
        sample_rationale = {}
        for line_id in sample_ids:
            line = lines_by_id[line_id]
            path = "Luna-assisted" if any(
                warning.code == "LLM_PROPOSED_EXTRACTION" for warning in line.extraction_warnings
            ) else "structured extraction"
            locator = line.source_locator
            location = (
                f"sheet {locator.sheet_name}" if locator.sheet_name
                else f"PDF page {locator.page_number}" if locator.page_number
                else "text/document"
            )
            sample_rationale[line_id] = f"Representative clean row from {path} · {location}"
        sampled = set(sample_ids)
        remaining = [
            line.line_id for line in eligible
            if line.line_id in covered_eligible_ids
            and line.line_id not in sampled
            and line.review_decision != ReviewDecision.APPROVED
        ]
        sample_approved = bool(sample_ids) and all(
            next(line for line in eligible if line.line_id == line_id).review_decision == ReviewDecision.APPROVED
            for line_id in sample_ids
        )
        sample_set = set(sample_ids)
        sample_correction_found = any(
            event.line_id in sample_set and event.action == AuditAction.LINE_EDITED
            for event in self._audit_events.get(case_id, [])
        )
        return ReviewPlan(
            case_id=case_id,
            total_lines=len(lines),
            exception_line_ids=exceptions,
            sample_line_ids=sample_ids,
            sample_rationale=sample_rationale,
            remaining_line_ids=remaining,
            sample_approved=sample_approved,
            sample_correction_found=sample_correction_found,
            can_batch_approve=sample_approved and not sample_correction_found and bool(remaining),
        )

    def approve_remaining_clean(self, case_id: str, actor: str) -> int:
        """Approve only clean non-sample rows after every sampled row is approved."""
        plan = self.get_review_plan(case_id)
        if plan.sample_correction_found:
            raise ValueError("A sampled row needed correction. Review the remaining clean rows individually.")
        if not plan.sample_approved:
            raise ValueError("Approve every sampled row before batch-approving the remaining validated rows.")
        now = datetime.utcnow()
        remaining_ids = set(plan.remaining_line_ids)
        updated = 0
        for line in self._lines_by_case.get(case_id, []):
            if line.line_id not in remaining_ids:
                continue
            old_decision = line.review_decision
            line.review_decision = ReviewDecision.APPROVED
            line.reviewed_by = actor
            line.reviewed_at = now
            line.version += 1
            self._record_audit(
                case_id=case_id,
                line_id=line.line_id,
                actor=actor,
                action=AuditAction.LINE_APPROVED,
                field_name="review_decision",
                old_value=old_decision.value,
                new_value=ReviewDecision.APPROVED.value,
                notes="Batch-approved after the case's risk-based review sample was approved.",
            )
            updated += 1
        if updated:
            self._refresh_case_metrics(case_id)
        return updated

    def delete_case(self, case_id: str) -> bool:
        """Deletes case and its associated files."""
        if case_id in self._cases:
            del self._cases[case_id]
            self._lines_by_case.pop(case_id, None)
            self._audit_events.pop(case_id, None)
            self.storage.delete_case(case_id)
            if self.state_store:
                self.state_store.delete_case(case_id)
            return True
        return False

    def _refresh_case_metrics(
        self, case_id: str, *, job_id: Optional[str] = None, worker_id: Optional[str] = None
    ):
        case = self._cases.get(case_id)
        if not case:
            return

        lines = self._lines_by_case.get(case_id, [])
        case.line_count = len(lines)
        case.updated_at = datetime.utcnow()

        # Keep case readiness consistent with the final export gate.
        unresolved = sum(1 for line in lines if blocking_line_issues(line, self.catalog))
        case.unresolved_count = unresolved

        if unresolved == 0 and len(lines) > 0:
            case.status = CaseStatus.READY_TO_EXPORT
        else:
            case.status = CaseStatus.NEEDS_REVIEW
        self._persist_case(case_id, job_id=job_id, worker_id=worker_id)

    def _persist_case(
        self, case_id: str, *, job_id: Optional[str] = None, worker_id: Optional[str] = None
    ) -> None:
        if self.state_store and case_id in self._cases:
            case = self._cases[case_id]
            lines = self._lines_by_case.get(case_id, [])
            events = self._audit_events.get(case_id, [])
            if job_id and worker_id:
                saved = self.state_store.save_case_snapshot_if_job_owned(
                    case, lines, events, job_id, worker_id
                )
                if not saved:
                    snapshot = self.state_store.load_case_snapshot(case_id)
                    if snapshot:
                        self._cases[case_id] = RFQCase.model_validate(snapshot["case"])
                        self._lines_by_case[case_id] = [
                            RFQLineItem.model_validate(item) for item in snapshot["lines"]
                        ]
                        self._audit_events[case_id] = [
                            AuditEvent.model_validate(item) for item in snapshot["events"]
                        ]
                    raise IngestionLeaseLostError(
                        "This worker lost its RFQ lease before it could commit the result."
                    )
            else:
                self.state_store.save_case_snapshot(case, lines, events)

    def _record_audit(
        self,
        case_id: str,
        actor: str,
        action: AuditAction,
        line_id: Optional[str] = None,
        field_name: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        notes: Optional[str] = None,
    ):
        event = AuditEvent(
            event_id=f"evt-{uuid.uuid4().hex[:8]}",
            case_id=case_id,
            line_id=line_id,
            actor=actor,
            action=action,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            notes=notes,
        )
        if case_id not in self._audit_events:
            self._audit_events[case_id] = []
        self._audit_events[case_id].append(event)
