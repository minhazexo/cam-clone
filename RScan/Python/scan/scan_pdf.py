"""Scan PDF photos to reference quality.

Feature: convert every page-photo of an input PDF (or a single photo, or a
folder of photos) the same way ``wiki_images/pdf photo..jpg`` was converted
into ``wiki_images/reference.png`` -- flat, deskewed, white background,
readable ink with color preserved.

Usage:
    python scan_pdf.py input.pdf output_scanned.pdf
    python scan_pdf.py photo.jpg output_scanned.pdf
    python scan_pdf.py photos_dir/ output_scanned.pdf --images-out out_imgs/
    python scan_pdf.py input.pdf output_scanned.pdf --dpi 300 --no-trim

Requires: opencv-python, numpy, pymupdf.
"""

import argparse
import os
import sys
import tempfile
import time
import logging

import cv2 as cv
import numpy as np

try:
    import pymupdf  # PyMuPDF >= 1.23
except ImportError:  # pragma: no cover
    pymupdf = None

try:
    from auto_scan import scan_photo_to_reference
except ModuleNotFoundError:
    from RScan.Python.scan.auto_scan import scan_photo_to_reference

LOG_LEVEL = logging.DEBUG if os.environ.get("RSCAN_DEBUG", "0") == "1" else logging.INFO
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("rscan.scan_pdf")
logger.setLevel(LOG_LEVEL)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp")


# ---------------------------------------------------------------------------
# page sources
# ---------------------------------------------------------------------------

def _pixmap_to_bgr(pix):
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


def iter_pdf_pages_as_bgr(pdf_path, dpi=200):
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
            yield i, _pixmap_to_bgr(pix)
    finally:
        doc.close()


def iter_images_as_bgr(path):
    """Yield (index, bgr) for one image file or every image in a directory."""
    if os.path.isdir(path):
        files = sorted(
            f for f in os.listdir(path)
            if f.lower().endswith(IMAGE_EXTS)
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


def collect_pages(source, dpi=200):
    """Return list of BGR pages from a PDF, image, or image directory."""
    if os.path.isdir(source):
        return [img for _, img in iter_images_as_bgr(source)]
    lower = source.lower()
    if lower.endswith(".pdf"):
        return [img for _, img in iter_pdf_pages_as_bgr(source, dpi=dpi)]
    if lower.endswith(IMAGE_EXTS):
        return [img for _, img in iter_images_as_bgr(source)]
    raise ValueError(f"unsupported input (need .pdf or image): {source}")


# ---------------------------------------------------------------------------
# scanned-PDF writer (PyMuPDF only, no extra deps)
# ---------------------------------------------------------------------------

PAGE_SIZES = {
    "A4": (595.0, 842.0),
    "Letter": (612.0, 792.0),
}


def draw_page_border(bgr, thickness=None, inset=None):
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


def save_bgr_pages_as_pdf(pages_bgr, output_pdf, jpeg_quality=78,
                          page_size="A4", margin=0.0,
                          page_border=True):
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


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def scan_pdf_to_reference(input_path, output_pdf, dpi=200, images_out=None,
                          jpeg_quality=78, no_trim=False, page_limit=None,
                          output_scale=1.0, page_size="A4", margin=0.0,
                          page_border=True, **scan_kwargs):
    """Scan ``input_path`` (PDF / image / dir) to reference quality.

    Returns the output PDF path. When ``images_out`` is given, each scanned
    page is also written there as ``page_0001.jpg`` etc. When ``page_limit``
    is provided, only the first ``page_limit`` pages are scanned.

    Defaults (Tier-1 balanced): 200 DPI render, no fake upscale
    (``output_scale=1.0`` — the old 2.0 Lanczos upscale blurs text while
    quadrupling pixels), JPEG q78, uniform A4 pages with 36pt margins.
    ``page_size`` accepts "A4", "Letter", an explicit ``(w, h)`` point tuple,
    or None for the legacy variable-size behaviour.
    """
    scan_kwargs.setdefault("output_scale", output_scale)
    started = time.time()
    logger.info("scan_pdf_to_reference: start input=%s output=%s dpi=%s page_limit=%s", input_path, output_pdf, dpi, page_limit)
    pages = collect_pages(input_path, dpi=dpi)
    if not pages:
        raise ValueError(f"no pages found in: {input_path}")
    total_pages = len(pages)
    if page_limit is not None:
        pages = pages[:page_limit]
        logger.info("scan_pdf_to_reference: page_limit applied requested=%s kept=%d of %d", page_limit, len(pages), total_pages)
    logger.info("scan_pdf_to_reference: loaded pages=%d", len(pages))

    scanned = []
    for i, page in enumerate(pages):
        page_started = time.time()
        logger.info("scanning page %d/%d (%dx%d) ...", i + 1, len(pages), page.shape[1], page.shape[0])
        out = scan_photo_to_reference(page, trim=not no_trim, **scan_kwargs)
        logger.info("scan_pdf_to_reference: page %d scan done elapsed=%.2fs dims=%dx%d", i + 1, time.time() - page_started, out.shape[1], out.shape[0])
        scanned.append(out)
        if images_out:
            os.makedirs(images_out, exist_ok=True)
            cv.imwrite(
                os.path.join(images_out, f"page_{i + 1:04d}.jpg"),
                out,
                [int(cv.IMWRITE_JPEG_QUALITY), jpeg_quality],
            )
    save_started = time.time()
    logger.info("scan_pdf_to_reference: saving scanned pages pages=%d output=%s", len(scanned), output_pdf)
    save_bgr_pages_as_pdf(scanned, output_pdf, jpeg_quality=jpeg_quality,
                          page_size=page_size, margin=margin,
                          page_border=page_border)
    logger.info("scan_pdf_to_reference: saved pdf elapsed=%.2fs", time.time() - save_started)
    logger.info("scan_pdf_to_reference: done pages=%d elapsed=%.2fs output=%s", len(scanned), time.time() - started, output_pdf)
    print(f"done: {len(scanned)} page(s) -> {output_pdf}")
    return output_pdf


def main(argv=None):
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


if __name__ == "__main__":
    main()
