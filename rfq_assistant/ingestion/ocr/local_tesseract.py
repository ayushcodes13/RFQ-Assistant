"""Bounded, page-level local OCR for image-heavy PDF pages.

This adapter does not upload document bytes. PyMuPDF renders only pages selected
by the caller; the Tesseract subprocess has page and output limits.
"""

from __future__ import annotations

import shutil
import subprocess
from functools import lru_cache
from typing import Any

import fitz


class LocalOCRError(RuntimeError):
    """Local OCR could not be completed for a page."""


@lru_cache(maxsize=1)
def engine_profile() -> str:
    """Return a bounded, content-free identity for the installed OCR binary."""
    executable = shutil.which("tesseract")
    if not executable:
        return "unavailable"
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True,
            timeout=2.0, check=False,
        )
        first_line = (result.stdout or result.stderr).splitlines()[0].strip()
        return first_line[:120] if result.returncode == 0 and first_line else "unknown"
    except (OSError, subprocess.TimeoutExpired, IndexError):
        return "unknown"


def image_coverage(page: Any) -> float:
    """Approximate the proportion of a page covered by embedded images."""
    rect = page.rect
    area = float(rect.width * rect.height)
    if area <= 0:
        return 0.0
    image_area = 0.0
    for info in page.get_image_info(xrefs=True):
        bbox = info.get("bbox")
        if bbox:
            clipped = fitz.Rect(bbox) & rect
            image_area += max(0.0, float(clipped.width * clipped.height))
    return min(1.0, image_area / area)


def page_needs_ocr(page: Any, native_text: str, *, max_native_chars: int = 180,
                    min_image_coverage: float = 0.18) -> bool:
    """Flag sparse-text pages only when page imagery suggests rasterized content."""
    if len(native_text.strip()) >= max_native_chars:
        return False
    return image_coverage(page) >= min_image_coverage


def recognize_page(
    pdf_bytes: bytes,
    page_number: int,
    *,
    dpi: int = 180,
    timeout_seconds: float = 15.0,
    max_pixels: int = 20_000_000,
    max_png_bytes: int = 32 * 1024 * 1024,
) -> str:
    """Rasterize and OCR one 1-based PDF page, with strict resource bounds."""
    executable = shutil.which("tesseract")
    if not executable:
        raise LocalOCRError("Tesseract is not installed; local OCR is unavailable.")
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise LocalOCRError("PDF could not be opened for OCR rendering.") from exc
    try:
        if page_number < 1 or page_number > len(document):
            raise LocalOCRError("Requested OCR page is outside the document.")
        page = document[page_number - 1]
        scale = dpi / 72.0
        estimated_pixels = page.rect.width * page.rect.height * scale * scale
        if estimated_pixels > max_pixels:
            scale *= (max_pixels / estimated_pixels) ** 0.5
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        png = pixmap.tobytes("png")
    except LocalOCRError:
        raise
    except Exception as exc:
        raise LocalOCRError("PDF page could not be rendered for OCR.") from exc
    finally:
        document.close()

    if len(png) > max_png_bytes:
        raise LocalOCRError("Rendered page exceeds the OCR image size limit.")
    try:
        completed = subprocess.run(
            [executable, "stdin", "stdout", "--psm", "6"],
            input=png,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LocalOCRError("OCR exceeded the per-page time limit.") from exc
    except OSError as exc:
        raise LocalOCRError("Tesseract could not be started.") from exc
    if completed.returncode != 0:
        raise LocalOCRError("Tesseract could not read the rendered page.")
    return completed.stdout.decode("utf-8", errors="replace").strip()
