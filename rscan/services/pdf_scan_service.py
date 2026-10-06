"""PDF scan use-case: PDF file -> scanned PDF (sync + streaming variants).

Two entry points, one shared pipeline::

    scan_pdf_file(in_path, out_path, page_limit, settings)
        whole file, blocking. Backs POST /api/scan-pdf.

    scan_pdf_streaming(in_path, out_path, page_limit, settings, on_event)
        renders, then scans pages in parallel, emitting progress. Backs the
        background job (POST /api/scan-pdf-start -> SSE).

Both run the same stages in the same order:

    render pages at settings.pdf_dpi
      -> rscan.scanner.pipeline per page (output_scale=1.0)
      -> rscan.pdf.assembler on uniform A4 pages

``on_event`` receives the dicts built in ``rscan.jobs.events``; the service
itself never touches queues or HTTP. Because ``on_event`` is the only
feedback channel, tests can call this function with a plain list collector.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional

import numpy as np

from rscan.config import Settings
from rscan.errors import PdfProcessingError
from rscan.jobs import events
from rscan.pdf.assembler import save_bgr_pages_as_pdf
from rscan.pdf.renderer import collect_pages
from rscan.scanner.pipeline import scan_photo_to_reference

logger = logging.getLogger(__name__)

#: Progress callback signature: receives an event dict from ``rscan.jobs.events``.
ProgressCallback = Callable[[dict], None]


def _noop(_event: dict) -> None:  # pragma: no cover - default callback
    """Default progress callback (sync path has no stream to feed)."""


def scan_pdf_file(in_path: str, out_path: str, page_limit: Optional[int],
                  settings: Settings) -> str:
    """Scan a PDF/image file to ``out_path`` and return that path (blocking).

    Raises:
        PdfProcessingError: when rendering, scanning or assembly fails.
    """
    try:
        pages = collect_pages(in_path, dpi=settings.pdf_dpi)
        if page_limit is not None:
            pages = pages[:page_limit]
        scanned = [scan_photo_to_reference(page, output_scale=1.0) for page in pages]
        save_bgr_pages_as_pdf(
            scanned, out_path,
            jpeg_quality=settings.pdf_jpeg_quality,
            page_size=settings.pdf_page_size,
            margin=settings.pdf_margin,
            page_border=settings.pdf_draw_page_border,
        )
    except PdfProcessingError:
        raise
    except Exception as exc:  # noqa: BLE001 - converted to a domain error
        logger.exception("pdf scan failed input=%s error=%s", in_path, exc)
        raise PdfProcessingError(str(exc)) from exc
    return out_path


def scan_pdf_streaming(in_path: str, out_path: str, page_limit: Optional[int],
                       settings: Settings,
                       on_event: ProgressCallback = _noop) -> str:
    """Scan a PDF page-by-page, reporting progress; returns the output path.

    Emits (in order) ``loading``, ``detected``, ``scanning``/``page_done`` per
    page and ``assembling``. The caller emits the terminal ``done``/``error``
    event, because only the caller knows the download name and the job id.

    Pages are scanned in parallel across CPU cores (bounded by
    ``settings.pdf_max_workers``) but the emitted ``page_done`` counter is
    monotonic, so the progress bar never jumps backwards.
    """
    try:
        # Step 1: render every page to BGR. Done up-front so the total page
        # count is known before any progress is reported.
        on_event(events.loading())
        pages = collect_pages(in_path, dpi=settings.pdf_dpi)
        total_available = len(pages)
        if page_limit is not None:
            pages = pages[:page_limit]
        total_to_scan = len(pages)
        on_event(events.detected(total_to_scan))
        logger.info("pdf scan rendering done input=%s available=%d to_scan=%d",
                    in_path, total_available, total_to_scan)

        if not pages:
            raise PdfProcessingError("no pages found in the uploaded PDF")

        # Step 2: scan pages in parallel.
        on_event(events.scanning(1, total_to_scan))
        scanned_map: dict[int, np.ndarray] = {}
        completed = 0
        num_workers = min(max(1, settings.pdf_max_workers),
                          max(1, os.cpu_count() or 4))

        def _process(item: tuple[int, np.ndarray]) -> tuple[int, np.ndarray]:
            idx, page_img = item
            # output_scale=1.0: the 2.0 Lanczos upscale blurs text edges while
            # quadrupling pixels, and the 200-DPI render is already the target
            # resolution for A4 output.
            return idx, scan_photo_to_reference(page_img, output_scale=1.0)

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(_process, (i, page))
                       for i, page in enumerate(pages)]
            for future in as_completed(futures):
                idx, out = future.result()
                scanned_map[idx] = out
                completed += 1
                on_event(events.page_done(completed, total_to_scan))

        scanned: List[np.ndarray] = [scanned_map[i] for i in range(len(pages))]

        # Step 3: assemble on uniform output pages.
        on_event(events.assembling())
        save_bgr_pages_as_pdf(
            scanned, out_path,
            jpeg_quality=settings.pdf_jpeg_quality,
            page_size=settings.pdf_page_size,
            margin=settings.pdf_margin,
            page_border=settings.pdf_draw_page_border,
        )
    except PdfProcessingError:
        raise
    except Exception as exc:  # noqa: BLE001 - converted to a domain error
        logger.exception("pdf streaming scan failed input=%s error=%s", in_path, exc)
        raise PdfProcessingError(str(exc)) from exc

    return out_path


__all__ = ["ProgressCallback", "scan_pdf_file", "scan_pdf_streaming"]
