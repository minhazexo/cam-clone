"""PDF service facade: one call to scan a PDF/image/directory to a PDF.

This is the synchronous, whole-file path (used by ``/api/scan-pdf`` and by
the CLI shim). The progress-streaming path used by the background job lives
in ``rscan.services.pdf_scan_service`` and reuses the same renderer,
scanner and assembler modules.

Defaults come from ``rscan.config.settings`` so the web layer, the CLI and
the docs never disagree about DPI/quality/page size.
"""

from __future__ import annotations

import logging
import os
import time
from typing import List, Optional

import cv2 as cv
import numpy as np

from rscan.pdf.assembler import PageSize, save_bgr_pages_as_pdf
from rscan.pdf.renderer import collect_pages
from rscan.scanner.pipeline import scan_photo_to_reference

logger = logging.getLogger(__name__)


def scan_pdf_to_reference(input_path: str, output_pdf: str, dpi: int = 200,
                          images_out: str | None = None,
                          jpeg_quality: int = 78,
                          no_trim: bool = False, page_limit: int | None = None,
                          output_scale: float = 1.0,
                          page_size: PageSize = "A4",
                          margin: float = 0.0,
                          page_border: bool = True,
                          **scan_kwargs) -> str:
    """Scan ``input_path`` (PDF / image / dir) to reference quality.

    Returns the output PDF path. When ``images_out`` is given, each scanned
    page is also written there as ``page_0001.jpg`` etc. When ``page_limit``
    is provided, only the first ``page_limit`` pages are scanned.

    Defaults (Tier-1 balanced) mirror ``rscan.config.settings`` and are kept
    literal here on purpose: the web layer passes the configured values
    explicitly, while the CLI passes exactly what the user asked for — and
    ``page_size=None`` must keep meaning "legacy variable page size", not
    "use the default".

    Defaults: 200 DPI render, no fake upscale (``output_scale=1.0`` — the
    old 2.0 Lanczos upscale blurs text while quadrupling pixels), JPEG q78,
    uniform A4 pages with zero margin. ``page_size`` accepts "A4",
    "Letter", an explicit ``(w, h)`` point tuple, or None for the legacy
    variable-size behaviour.
    """
    scan_kwargs.setdefault("output_scale", output_scale)
    started = time.time()
    logger.info("pdf scan start input=%s output=%s dpi=%s page_limit=%s",
                input_path, output_pdf, dpi, page_limit)
    pages = collect_pages(input_path, dpi=dpi)
    if not pages:
        raise ValueError(f"no pages found in: {input_path}")
    total_pages = len(pages)
    if page_limit is not None:
        pages = pages[:page_limit]
        logger.info("pdf scan page_limit applied requested=%s kept=%d of %d",
                    page_limit, len(pages), total_pages)
    logger.info("pdf scan loaded pages=%d", len(pages))

    scanned: List[np.ndarray] = []
    for i, page in enumerate(pages):
        page_started = time.time()
        logger.info("scanning page %d/%d (%dx%d) ...",
                    i + 1, len(pages), page.shape[1], page.shape[0])
        out = scan_photo_to_reference(page, trim=not no_trim, **scan_kwargs)
        logger.info("pdf scan page %d done elapsed=%.2fs dims=%dx%d",
                    i + 1, time.time() - page_started, out.shape[1], out.shape[0])
        scanned.append(out)
        if images_out:
            os.makedirs(images_out, exist_ok=True)
            cv.imwrite(
                os.path.join(images_out, f"page_{i + 1:04d}.jpg"),
                out,
                [int(cv.IMWRITE_JPEG_QUALITY), jpeg_quality],
            )
    save_started = time.time()
    logger.info("pdf scan saving pages=%d output=%s", len(scanned), output_pdf)
    save_bgr_pages_as_pdf(scanned, output_pdf, jpeg_quality=jpeg_quality,
                          page_size=page_size, margin=margin,
                          page_border=page_border)
    logger.info("pdf scan saved elapsed=%.2fs", time.time() - save_started)
    logger.info("pdf scan done pages=%d elapsed=%.2fs output=%s",
                len(scanned), time.time() - started, output_pdf)
    return output_pdf


def scan_pdf_page_images(pages: List[np.ndarray], output_scale: float = 1.0,
                         no_trim: bool = False) -> List[np.ndarray]:
    """Scan an in-memory list of BGR pages with the shared pipeline.

    Small helper so the streaming service and future callers do not repeat
    the ``trim=not no_trim, output_scale=...`` incantation.
    """
    return [
        scan_photo_to_reference(page, trim=not no_trim, output_scale=output_scale)
        for page in pages
    ]


__all__ = ["scan_pdf_to_reference", "scan_pdf_page_images"]
