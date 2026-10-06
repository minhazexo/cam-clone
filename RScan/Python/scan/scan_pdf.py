"""DEPRECATED MODULE — compatibility shim + CLI for ``rscan.pdf`` / ``rscan.scanner``.

Status: **compatibility** (the CLI is the supported entry point; the module
path is kept so existing commands and imports keep working).

Canonical implementation:

    rscan/pdf/renderer.py     PDF/image pages -> BGR ndarrays
    rscan/pdf/assembler.py    BGR pages -> uniform scanned PDF
    rscan/pdf/pdf_service.py  whole-file scan (this shim's ``scan_pdf_to_reference``)

Usage (unchanged)::

    python RScan/Python/scan/scan_pdf.py input.pdf output_scanned.pdf
    python RScan/Python/scan/scan_pdf.py photo.jpg output_scanned.pdf
    python RScan/Python/scan/scan_pdf.py photos_dir/ out.pdf --images-out out_imgs/
    python RScan/Python/scan/scan_pdf.py in.pdf out.pdf --dpi 300 --no-trim

Requires: opencv-python, numpy, pymupdf.
"""

from __future__ import annotations

import argparse
import os

try:  # imported as a top-level module when run by path
    from _compat import ensure_project_root_on_path  # noqa: F401
except ModuleNotFoundError:  # imported as ``RScan.Python.scan.scan_pdf``
    from ._compat import ensure_project_root_on_path  # type: ignore[no-redef]

ensure_project_root_on_path()

from rscan.config import get_settings  # noqa: E402
from rscan.pdf.assembler import PAGE_SIZES, draw_page_border, save_bgr_pages_as_pdf  # noqa: E402
from rscan.pdf.pdf_service import scan_pdf_to_reference  # noqa: E402
from rscan.pdf.renderer import (  # noqa: E402
    collect_pages,
    iter_images_as_bgr,
    iter_pdf_pages_as_bgr,
    pixmap_to_bgr,
)

#: Image extensions accepted by ``collect_pages`` (from the central settings).
IMAGE_EXTS = tuple(sorted(get_settings().allowed_image_extensions))


def main(argv=None) -> None:
    """Command-line interface (see the module docstring for examples)."""
    parser = argparse.ArgumentParser(
        description="Convert PDF photos to reference-quality scans."
    )
    parser.add_argument("input", help="input .pdf, image, or image directory")
    parser.add_argument("output", help="output scanned .pdf path")
    parser.add_argument("--dpi", type=int, default=200,
                        help="render DPI for PDF input (default 200)")
    parser.add_argument("--images-out", default=None,
                        help="optional dir to also write scanned page images")
    parser.add_argument("--jpeg-quality", type=int, default=78,
                        help="JPEG quality for pages (default 78)")
    parser.add_argument("--page-size", default="A4",
                        help='"A4", "Letter", or "keep" for legacy variable size')
    parser.add_argument("--margin", type=float, default=0.0,
                        help="margin in PDF points around the image (default 0 = full-bleed)")
    parser.add_argument("--no-border", action="store_true",
                        help="skip the black A4 frame drawn around each page")
    parser.add_argument("--no-trim", action="store_true",
                        help="disable edge-trim fallback for full-frame photos")
    parser.add_argument("--no-reframe", action="store_true",
                        help="disable reference-margin re-framing")
    parser.add_argument("--output-scale", type=float, default=1.0,
                        help="upscale factor for scanned pages (default 1.0; "
                             "2.0 blurs text while quadrupling pixels)")
    parser.add_argument("--white-point", type=float, default=None)
    parser.add_argument("--black-point", type=float, default=None)
    args = parser.parse_args(argv)

    kwargs = {}
    if args.white_point is not None:
        kwargs["white_point"] = args.white_point
    if args.black_point is not None:
        kwargs["black_point"] = args.black_point
    page_size = None if args.page_size == "keep" else args.page_size
    scan_pdf_to_reference(
        args.input, args.output, dpi=args.dpi, images_out=args.images_out,
        jpeg_quality=args.jpeg_quality, no_trim=args.no_trim,
        reframe=not args.no_reframe, output_scale=args.output_scale,
        page_size=page_size, margin=args.margin,
        page_border=not args.no_border,
        **kwargs,
    )


__all__ = [
    "IMAGE_EXTS",
    "PAGE_SIZES",
    "pixmap_to_bgr",
    "iter_pdf_pages_as_bgr",
    "iter_images_as_bgr",
    "collect_pages",
    "draw_page_border",
    "save_bgr_pages_as_pdf",
    "scan_pdf_to_reference",
    "main",
]


if __name__ == "__main__":
    main()
