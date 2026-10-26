"""Parser factory for dispatching by source type."""

from typing import Optional
from rfq_assistant.ingestion.parsers.base import BaseDocumentParser, DocumentParserError, ParsedDocumentResult, ParsedLineDraft
from rfq_assistant.ingestion.parsers.pdf_parser import PDFParser
from rfq_assistant.ingestion.parsers.spreadsheet_parser import SpreadsheetParser
from rfq_assistant.ingestion.parsers.text_parser import TextParser
from rfq_assistant.schemas.enums import SourceType


def get_parser(source_type: SourceType, allow_ocr: bool = False) -> BaseDocumentParser:
    """Returns the appropriate parser instance for the given source type."""
    if source_type in (SourceType.CSV, SourceType.XLSX):
        return SpreadsheetParser()
    elif source_type in (SourceType.PDF_NATIVE, SourceType.PDF_SCANNED):
        return PDFParser(allow_ocr=allow_ocr)
    elif source_type == SourceType.EMAIL_TEXT:
        return TextParser()
    else:
        raise DocumentParserError(f"No parser available for source type: {source_type}")


__all__ = [
    "BaseDocumentParser",
    "DocumentParserError",
    "ParsedDocumentResult",
    "ParsedLineDraft",
    "PDFParser",
    "SpreadsheetParser",
    "TextParser",
    "get_parser",
]
