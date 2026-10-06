"""Scanned-PDF assembly: BGR pages -> one PDF with uniform pages.

Design decisions (kept from the original implementation):

    * one image per page, aspect-fit, centred — ``margin=0`` means
      full-bleed, so landscape photos get landscape pages and no white bands;
    * a thin black frame is drawn into the JPEG bytes (not a vector
      rectangle) so the server and browser paths produce the same look;
    * pages are JPEG-encoded at ``jpeg_quality`` (78 default) into a temp
      directory and embedded from file, which keeps memory flat on big jobs;
    * ``page_size=None`` keeps the legacy variable-size behaviour (one PDF
      point per image pixel) for callers that rely on it.

PyMuPDF only — no extra dependencies, which matters for the serverless
bundle. The browser path mirrors this file in
``static/js/features/pdf-scan/pdf-export.js``.
"""

from __future__ import annotations

import os
import tempfile
from typing import List, Sequence, Union

import cv2 as cv
import numpy as np

try:  # PyMuPDF >= 1.23
    import pymupdf
except ImportError:  # pragma: no cover - import error surfaces on use
    pymupdf = None

#: Standard page sizes in PDF points (1 pt = 1/72 inch).
PAGE_SIZES = {
    "A4": (595.0, 842.0),
    "Letter": (612.0, 792.0),
}

PageSize = Union[str, Sequence[float], None]


def draw_page_border(bgr: np.ndarray, thickness: int | None = None,
                     inset: int | None = None) -> np.ndarray:
    """Draw a thin square black frame just inside the image edges.

    Gives every note page a crisp, uniform A4 frame. Thickness scales with
    resolution (~0.3% of the short side, min 3px); inset defaults to one
    stroke width so the full frame stays visible.
    """
    h, w = bgr.shape[:2]
    th = thickness or max(3, round(min(h, w) * 0.003))
    ins = inset if inset is not None else th
    return cv.rectangle(bgr, (ins, ins), (w - 1 - ins, h - 1 - ins),
                        (0, 0, 0), th, cv.LINE_8)


def save_bgr_pages_as_pdf(pages_bgr: List[np.ndarray], output_pdf: str,
                          jpeg_quality: int = 78, page_size: PageSize = "A4",
                          margin: float = 0.0, page_border: bool = True) -> str:
    """Write BGR pages to a PDF, one page per image, on uniform note pages.

    ``page_size`` is "A4"/"Letter" (matched to each image's orientation, so
    landscape photos get landscape pages with no white bands), an explicit
    ``(w, h)`` point tuple, or None for the legacy behaviour (one PDF point
    per image pixel, variable page dimensions). The scanned image is
    aspect-fit to fill the page (``margin=0`` default: no white frame).
    Increase ``margin`` only if a white frame is wanted.
    """
    if pymupdf is None:
        raise ImportError("pymupdf is required for PDF output (pip install pymupdf)")
    if not pages_bgr:
        raise ValueError("no pages to write")
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf)), exist_ok=True)
    doc = pymupdf.open()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for i, page in enumerate(pages_bgr):
                if page_border:
                    page = draw_page_border(page.copy())
                ok, buf = cv.imencode(
                    ".jpg", page, [int(cv.IMWRITE_JPEG_QUALITY), jpeg_quality]
                )
                if not ok:
                    raise RuntimeError(f"JPEG encoding failed for page {i}")
                tmp_path = os.path.join(tmp, f"page_{i:04d}.jpg")
                with open(tmp_path, "wb") as fh:
                    fh.write(buf.tobytes())
                h, w = page.shape[:2]
                if page_size is None:
                    # Legacy: 1 image pixel == 1 PDF point (variable page size).
                    pdf_page = doc.new_page(width=w, height=h)
                    pdf_page.insert_image(
                        pymupdf.Rect(0, 0, w, h), filename=tmp_path
                    )
                    continue
                if isinstance(page_size, str):
                    base = PAGE_SIZES.get(page_size, PAGE_SIZES["A4"])
                    # Match page orientation to the image: landscape photos
                    # get landscape pages, so aspect-fit never leaves white
                    # bands on two sides.
                    pw, ph = base if h >= w else (base[1], base[0])
                else:
                    pw, ph = page_size
                max_w, max_h = pw - 2 * margin, ph - 2 * margin
                s = min(max_w / w, max_h / h)
                dw, dh = w * s, h * s
                x0, y0 = (pw - dw) / 2, (ph - dh) / 2
                pdf_page = doc.new_page(width=pw, height=ph)
                pdf_page.insert_image(
                    pymupdf.Rect(x0, y0, x0 + dw, y0 + dh), filename=tmp_path
                )
        doc.save(output_pdf, garbage=4, deflate=True)
    finally:
        doc.close()
    return output_pdf


__all__ = ["PAGE_SIZES", "draw_page_border", "save_bgr_pages_as_pdf"]
