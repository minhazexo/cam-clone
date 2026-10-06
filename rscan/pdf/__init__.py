"""PDF domain — page rendering and scanned-PDF assembly (PyMuPDF + OpenCV).

Module map:

    renderer.py    PDF/image pages -> BGR ndarrays (the "page source" layer)
    assembler.py   scanned BGR pages -> a uniform scanned PDF (A4/Letter/keep)

Both modules are pure domain code: no Flask, no HTTP, no job state. The
orchestration that connects them to the scanner and to progress events lives
in ``rscan.services.pdf_scan_service``.

Why PyMuPDF: it renders pages (``get_pixmap``) and writes PDFs
(``insert_image`` + ``save``) without extra native dependencies, which keeps
the Vercel bundle small. Documented in ``docs/PDF_PIPELINE.md``.
"""

from rscan.pdf.assembler import PAGE_SIZES, save_bgr_pages_as_pdf
from rscan.pdf.renderer import collect_pages

__all__ = ["PAGE_SIZES", "save_bgr_pages_as_pdf", "collect_pages"]
