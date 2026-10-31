"""Safe document upload validation and security defenses."""

import hashlib
import os
import re
import zipfile
from io import BytesIO
from typing import Tuple

from rfq_assistant.schemas.enums import SourceType

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB default limit
ALLOWED_EXTENSIONS = {".csv", ".xls", ".xlsx", ".pdf", ".txt"}


class UploadValidationError(Exception):
    """Raised when an uploaded file violates security or format requirements."""
    pass


def sanitize_filename(filename: str) -> str:
    """Sanitizes filename against path traversal and dangerous characters."""
    normalized = filename.replace("\\", "/")
    base = os.path.basename(normalized)
    # Remove null bytes and non-safe characters
    cleaned = re.sub(r"[^\w\.\-\_]", "_", base)
    if not cleaned or cleaned.startswith("."):
        cleaned = f"upload_{cleaned}"
    return cleaned


def compute_sha256(content: bytes) -> str:
    """Computes SHA-256 hexadecimal digest of file content."""
    hasher = hashlib.sha256()
    hasher.update(content)
    return hasher.hexdigest()


def validate_file_upload(filename: str, content: bytes) -> Tuple[str, SourceType, str]:
    """
    Validates uploaded file against size, extension, macro presence, and structure.
    Returns: (sanitized_filename, source_type, sha256_digest)
    """
    if not content:
        raise UploadValidationError("Uploaded file is empty (0 bytes).")

    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadValidationError(
            f"File size exceeds maximum permitted limit ({len(content)} bytes > {MAX_UPLOAD_BYTES} bytes)."
        )

    clean_name = sanitize_filename(filename)
    _, ext = os.path.splitext(clean_name.lower())

    if ext not in ALLOWED_EXTENSIONS:
        if ext in {".xlsm", ".xltm", ".docm"}:
            raise UploadValidationError(
                f"Macro-enabled spreadsheets ('{ext}') are prohibited for security reasons. Please upload a standard .xlsx or .csv without macros."
            )
        raise UploadValidationError(
            f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}."
        )

    # Inspect zip contents for XLSX to detect embedded VBA macros or decompression bombs
    if ext == ".xls" and not content.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        raise UploadValidationError("File does not have a valid legacy Excel (OLE/BIFF) header.")

    if ext == ".xlsx":
        try:
            with zipfile.ZipFile(BytesIO(content)) as z:
                # Check for macro components
                for member in z.namelist():
                    if "vbaProject.bin" in member or "macros" in member.lower():
                        raise UploadValidationError(
                            "Embedded VBA macros detected inside spreadsheet. Macro-enabled files are rejected by security policy."
                        )
                # Check compression ratio to prevent zip bombs
                total_uncompressed = sum(info.file_size for info in z.infolist())
                if total_uncompressed > 50 * 1024 * 1024:  # 50 MB expanded cap
                    raise UploadValidationError("Spreadsheet uncompressed size exceeds security threshold.")
        except zipfile.BadZipFile:
            raise UploadValidationError("File appears to be a corrupted or invalid Excel workbook.")

    # PDF validation: check magic header
    if ext == ".pdf":
        if not content.startswith(b"%PDF-"):
            raise UploadValidationError("File does not have a valid PDF header.")

    digest = compute_sha256(content)

    source_type_map = {
        ".csv": SourceType.CSV,
        ".xls": SourceType.XLSX,
        ".xlsx": SourceType.XLSX,
        ".pdf": SourceType.PDF_NATIVE,
        ".txt": SourceType.EMAIL_TEXT,
    }

    return clean_name, source_type_map[ext], digest
