"""Fast, synthetic tests for bounded local PDF OCR behavior."""

import subprocess
from types import SimpleNamespace

import pytest

from rfq_assistant.ingestion.ocr import local_tesseract as ocr


class _Page:
    rect = SimpleNamespace(width=1000, height=2000)

    def __init__(self, pixmap=None):
        self.pixmap = pixmap or SimpleNamespace(
            width=100, height=200, tobytes=lambda _: b"png"
        )
        self.matrix = None

    def get_pixmap(self, *, matrix, alpha):
        self.matrix = matrix
        assert alpha is False
        return self.pixmap


class _Document:
    def __init__(self, page):
        self.pages = [page]

    def __len__(self):
        return len(self.pages)

    def __getitem__(self, index):
        return self.pages[index]


def _completed(stdout=b"", *, returncode=0):
    return subprocess.CompletedProcess(
        args=[], returncode=returncode, stdout=stdout, stderr=b""
    )


def _tsv(rows):
    header = "level\tblock_num\tpar_num\tline_num\tleft\ttop\twidth\theight\tconf\ttext"
    return (header + "\n" + "\n".join(rows) + "\n").encode()


def test_engine_profile_is_cached_and_reports_missing_or_unknown(monkeypatch):
    ocr.engine_profile.cache_clear()
    monkeypatch.setattr(ocr.shutil, "which", lambda _binary: None)
    assert ocr.engine_profile() == "unavailable"

    ocr.engine_profile.cache_clear()
    monkeypatch.setattr(ocr.shutil, "which", lambda _binary: "/bin/tesseract")
    monkeypatch.setattr(
        ocr.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=0, stdout="Tesseract 5.4.0\n", stderr=""
        ),
    )
    assert ocr.engine_profile() == "Tesseract 5.4.0"
    monkeypatch.setattr(
        ocr.subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(OSError())
    )
    ocr.engine_profile.cache_clear()
    assert ocr.engine_profile() == "unknown"
    ocr.engine_profile.cache_clear()


def test_image_coverage_and_ocr_triage_handle_empty_and_sparse_pages():
    page = SimpleNamespace(
        rect=ocr.pymupdf.Rect(0, 0, 100, 100),
        get_image_info=lambda **_kwargs: [{"bbox": (-10, 0, 30, 40)}, {"bbox": None}],
    )
    assert ocr.image_coverage(page) == pytest.approx(0.12)
    assert not ocr.page_needs_ocr(page, "x" * 180)
    assert not ocr.page_needs_ocr(page, "sparse")
    page.rect = ocr.pymupdf.Rect(0, 0, 0, 100)
    assert ocr.image_coverage(page) == 0


def test_render_page_enforces_page_bounds_pixel_and_png_caps(monkeypatch):
    page = _Page()
    document = _Document(page)
    matrices = []
    monkeypatch.setattr(
        ocr.pymupdf, "Matrix", lambda x, y: matrices.append((x, y)) or (x, y)
    )

    rendered = ocr.render_page(document, 1, max_pixels=1_000_000)
    assert rendered.png == b"png"
    assert rendered.width == 100 and rendered.height == 200
    assert matrices[0][0] < 180 / 72

    with pytest.raises(ocr.LocalOCRError, match="outside"):
        ocr.render_page(document, 0)
    too_large = _Document(
        _Page(SimpleNamespace(width=1, height=1, tobytes=lambda _: b"12345"))
    )
    with pytest.raises(ocr.LocalOCRError, match="size limit"):
        ocr.render_page(too_large, 1, max_png_bytes=4)


@pytest.mark.parametrize(
    ("which", "run", "message"),
    [
        (None, None, "not installed"),
        ("/bin/tesseract", subprocess.TimeoutExpired("tesseract", 1), "time limit"),
        ("/bin/tesseract", OSError("missing executable"), "could not be started"),
        ("/bin/tesseract", _completed(returncode=2), "could not read"),
    ],
)
def test_rendered_ocr_converts_engine_failures_to_clear_errors(
    monkeypatch, which, run, message
):
    monkeypatch.setattr(ocr.shutil, "which", lambda _binary: which)
    if which and isinstance(run, BaseException):
        monkeypatch.setattr(
            ocr.subprocess, "run", lambda *_a, **_k: (_ for _ in ()).throw(run)
        )
    elif which:
        monkeypatch.setattr(ocr.subprocess, "run", lambda *_a, **_k: run)
    with pytest.raises(ocr.LocalOCRError, match=message):
        ocr.recognize_rendered_page(ocr.RenderedOCRPage(b"png", 100, 200))


def test_rendered_ocr_parses_words_into_bounded_line_boxes(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda _binary: "/bin/tesseract")
    output = _tsv(
        [
            "5\t1\t1\t1\t10\t20\t30\t10\t80\tHello",
            "5\t1\t1\t1\t45\t15\t20\t20\t100\tworld",
            "5\t1\t1\t2\t0\t0\t0\t10\t90\tzero-width",
            "5\t1\t1\t2\t0\t0\t10\t10\tbad\tbad-confidence",
            "5\t1\t1\t3\t0\t0\tbroken\t10\t90\tbad-geometry",
            "4\t1\t1\t1\t0\t0\t100\t20\t90\tnot-a-word",
        ]
    )
    monkeypatch.setattr(ocr.subprocess, "run", lambda *_a, **_k: _completed(output))

    result = ocr.recognize_rendered_page(ocr.RenderedOCRPage(b"png", 100, 100))

    assert result.text == "Hello world\nbad-confidence"
    assert len(result.lines) == 2
    assert result.lines[0].bbox == pytest.approx((0.1, 0.15, 0.65, 0.35))
    assert result.lines[0].confidence == 90
    assert result.lines[1].confidence is None


def test_rendered_ocr_rejects_oversized_tsv(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda _binary: "/bin/tesseract")
    monkeypatch.setattr(
        ocr.subprocess,
        "run",
        lambda *_a, **_k: _completed(b"x" * (16 * 1024 * 1024 + 1)),
    )
    with pytest.raises(ocr.LocalOCRError, match="output exceeds"):
        ocr.recognize_rendered_page(ocr.RenderedOCRPage(b"png", 1, 1))


def test_single_page_api_closes_document_and_wraps_open_errors(monkeypatch):
    monkeypatch.setattr(ocr.shutil, "which", lambda _binary: "/bin/tesseract")
    page = _Page()

    class ClosableDocument(_Document):
        closed = False

        def close(self):
            self.closed = True

    document = ClosableDocument(page)
    monkeypatch.setattr(ocr.pymupdf, "open", lambda **_kwargs: document)
    monkeypatch.setattr(
        ocr,
        "recognize_rendered_page",
        lambda rendered, **_kwargs: ocr.OCRPageResult("ok", ()),
    )
    assert ocr.recognize_page(b"pdf", 1).text == "ok"
    assert document.closed

    monkeypatch.setattr(
        ocr.pymupdf, "open", lambda **_kwargs: (_ for _ in ()).throw(ValueError())
    )
    with pytest.raises(ocr.LocalOCRError, match="could not be opened"):
        ocr.recognize_page(b"bad", 1)
