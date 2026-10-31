"""Bounded, page-level local OCR for image-heavy PDF pages.

This adapter does not upload document bytes. PyMuPDF renders only pages selected
by the caller; the Tesseract subprocess has page and output limits.
"""

from __future__ import annotations

import csv
import io
import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional, Tuple

import pymupdf


class LocalOCRError(RuntimeError):
    """Local OCR could not be completed for a page."""


@dataclass(frozen=True)
class OCRTextLine:
    text: str
    # Normalized coordinates in the rotated, user-visible PDF page: x0,y0,x1,y1.
    bbox: Tuple[float, float, float, float]
    confidence: Optional[float]


@dataclass(frozen=True)
class OCRPageResult:
    text: str
    lines: Tuple[OCRTextLine, ...]


@dataclass(frozen=True)
class RenderedOCRPage:
    png: bytes
    width: int
    height: int


@lru_cache(maxsize=1)
def engine_profile() -> str:
    """Return a bounded, content-free identity for the installed OCR binary."""
    executable = shutil.which("tesseract")
    if not executable:
        return "unavailable"
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
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
            clipped = pymupdf.Rect(bbox) & rect
            image_area += max(0.0, float(clipped.width * clipped.height))
    return min(1.0, image_area / area)


def page_needs_ocr(
    page: Any,
    native_text: str,
    *,
    max_native_chars: int = 180,
    min_image_coverage: float = 0.18,
) -> bool:
    """Flag sparse-text pages only when page imagery suggests rasterized content."""
    if len(native_text.strip()) >= max_native_chars:
        return False
    return image_coverage(page) >= min_image_coverage


def render_page(
    document: Any,
    page_number: int,
    *,
    dpi: int = 180,
    max_pixels: int = 20_000_000,
    max_png_bytes: int = 32 * 1024 * 1024,
) -> RenderedOCRPage:
    """Render one page from an already-open document under strict size bounds."""
    try:
        if page_number < 1 or page_number > len(document):
            raise LocalOCRError("Requested OCR page is outside the document.")
        page = document[page_number - 1]
        scale = dpi / 72.0
        estimated_pixels = page.rect.width * page.rect.height * scale * scale
        if estimated_pixels > max_pixels:
            scale *= (max_pixels / estimated_pixels) ** 0.5
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        png = pixmap.tobytes("png")
        rendered_width, rendered_height = pixmap.width, pixmap.height
    except LocalOCRError:
        raise
    except Exception as exc:
        raise LocalOCRError("PDF page could not be rendered for OCR.") from exc
    if len(png) > max_png_bytes:
        raise LocalOCRError("Rendered page exceeds the OCR image size limit.")
    return RenderedOCRPage(png, rendered_width, rendered_height)


def recognize_rendered_page(
    rendered: RenderedOCRPage, *, timeout_seconds: float = 15.0
) -> OCRPageResult:
    """OCR a pre-rendered page and retain bounded normalized line geometry."""
    executable = shutil.which("tesseract")
    if not executable:
        raise LocalOCRError("Tesseract is not installed; local OCR is unavailable.")
    try:
        completed = subprocess.run(
            [executable, "stdin", "stdout", "--psm", "6", "tsv"],
            input=rendered.png,
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
    if len(completed.stdout) > 16 * 1024 * 1024:
        raise LocalOCRError("OCR output exceeds the per-page text limit.")

    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    reader = csv.DictReader(
        io.StringIO(completed.stdout.decode("utf-8", errors="replace")), delimiter="\t"
    )
    for row in reader:
        if row.get("level") != "5":
            continue
        word = (row.get("text") or "").strip()
        if not word:
            continue
        try:
            left = int(row["left"])
            top = int(row["top"])
            width = int(row["width"])
            height = int(row["height"])
        except (KeyError, TypeError, ValueError):
            continue
        if width <= 0 or height <= 0:
            continue
        key = (
            row.get("block_num", ""),
            row.get("par_num", ""),
            row.get("line_num", ""),
        )
        group = groups.setdefault(key, {"words": [], "bounds": [], "confidences": []})
        group["words"].append(word)
        group["bounds"].append((left, top, left + width, top + height))
        try:
            confidence = float(row.get("conf", ""))
        except (TypeError, ValueError):
            confidence = -1
        if confidence >= 0:
            group["confidences"].append(confidence)

    lines = []
    for group in groups.values():
        bounds = group["bounds"]
        confidence_values = group["confidences"]
        lines.append(
            OCRTextLine(
                text=" ".join(group["words"]),
                bbox=(
                    max(0.0, min(1.0, min(box[0] for box in bounds) / rendered.width)),
                    max(0.0, min(1.0, min(box[1] for box in bounds) / rendered.height)),
                    max(0.0, min(1.0, max(box[2] for box in bounds) / rendered.width)),
                    max(0.0, min(1.0, max(box[3] for box in bounds) / rendered.height)),
                ),
                confidence=(sum(confidence_values) / len(confidence_values))
                if confidence_values
                else None,
            )
        )
    return OCRPageResult(
        text="\n".join(line.text for line in lines), lines=tuple(lines)
    )


def recognize_page(
    pdf_bytes: bytes,
    page_number: int,
    *,
    dpi: int = 180,
    timeout_seconds: float = 15.0,
    max_pixels: int = 20_000_000,
    max_png_bytes: int = 32 * 1024 * 1024,
) -> OCRPageResult:
    """Convenience API that renders and recognizes one PDF page."""
    if not shutil.which("tesseract"):
        raise LocalOCRError("Tesseract is not installed; local OCR is unavailable.")
    try:
        document = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise LocalOCRError("PDF could not be opened for OCR rendering.") from exc
    try:
        rendered = render_page(
            document,
            page_number,
            dpi=dpi,
            max_pixels=max_pixels,
            max_png_bytes=max_png_bytes,
        )
    finally:
        document.close()
    return recognize_rendered_page(rendered, timeout_seconds=timeout_seconds)
