"""Page sources: turn PDFs, images and image folders into BGR pages.

Used by the server PDF flow (``services/pdf_scan_service``) and by the CLI
shim (``RScan/Python/scan/scan_pdf.py``). Every function here is a generator
or a list builder over BGR ndarrays, so the same page list feeds both the
scanner pipeline and the PDF assembler.

Rendering DPI matters for quality/bytes (200 DPI is the tuned default; see
``rscan.config.settings``), and CMYK JPEGs embedded in PDFs are converted the
coarse way (``255 - value``) which is correct for photo pages.
"""

from __future__ import annotations

import os
import sys
from typing import Iterator, List

import cv2 as cv
import numpy as np

try:  # PyMuPDF >= 1.23
    import pymupdf
except ImportError:  # pragma: no cover - import error surfaces on use
    pymupdf = None

from rscan.config import get_settings


def pixmap_to_bgr(pix) -> np.ndarray:
    """Convert a PyMuPDF pixmap to OpenCV BGR."""
    if pix.n - pix.alpha >= 4:
        mode = "CMYK"
    elif pix.n - pix.alpha == 3:
        mode = "RGB"
    else:  # gray / mask
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
        gray = arr[:, :, 0]
        return cv.cvtColor(gray, cv.COLOR_GRAY2BGR)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    rgb = arr[:, :, :3]
    if mode == "CMYK":
        rgb = 255 - rgb  # coarse CMYK -> RGB for photo pages
    return cv.cvtColor(rgb, cv.COLOR_RGB2BGR)


def iter_pdf_pages_as_bgr(pdf_path: str, dpi: int = 200) -> Iterator[tuple[int, np.ndarray]]:
    """Yield (page_number, bgr_image) rendering each PDF page at ``dpi``.

    200 DPI preserves note-page text crisply while keeping each page's
    pixel count (and hence JPEG bytes) far below the old 300 DPI default.
    """
    if pymupdf is None:
        raise ImportError("pymupdf is required for PDF input/output (pip install pymupdf)")
    doc = pymupdf.open(pdf_path)
    try:
        zoom = dpi / 72.0
        matrix = pymupdf.Matrix(zoom, zoom)
        for i, page in enumerate(doc):
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            yield i, pixmap_to_bgr(pix)
    finally:
        doc.close()


def iter_images_as_bgr(path: str) -> Iterator[tuple[int, np.ndarray]]:
    """Yield (index, bgr) for one image file or every image in a directory."""
    image_exts = get_settings().allowed_image_extensions
    if os.path.isdir(path):
        files = sorted(
            f for f in os.listdir(path)
            if os.path.splitext(f)[1].lower() in image_exts
        )
        if not files:
            raise ValueError(f"no images found in directory: {path}")
        for i, name in enumerate(files):
            full = os.path.join(path, name)
            img = cv.imread(full, cv.IMREAD_COLOR)
            if img is None:
                print(f"warning: could not read {full}, skipping", file=sys.stderr)
                continue
            yield i, img
    else:
        img = cv.imread(path, cv.IMREAD_COLOR)
        if img is None:
            raise ValueError(f"could not read image: {path}")
        yield 0, img


def collect_pages(source: str, dpi: int = 200) -> List[np.ndarray]:
    """Return a list of BGR pages from a PDF, image, or image directory."""
    if os.path.isdir(source):
        return [img for _, img in iter_images_as_bgr(source)]
    lower = source.lower()
    if lower.endswith(".pdf"):
        return [img for _, img in iter_pdf_pages_as_bgr(source, dpi=dpi)]
    if os.path.splitext(lower)[1] in get_settings().allowed_image_extensions:
        return [img for _, img in iter_images_as_bgr(source)]
    raise ValueError(f"unsupported input (need .pdf or image): {source}")


__all__ = [
    "pixmap_to_bgr",
    "iter_pdf_pages_as_bgr",
    "iter_images_as_bgr",
    "collect_pages",
]
