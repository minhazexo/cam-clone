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

import cv2 as cv
import numpy as np

try:
    import pymupdf  # PyMuPDF >= 1.23
except ImportError:  # pragma: no cover
    pymupdf = None

from auto_scan import scan_photo_to_reference

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


def iter_pdf_pages_as_bgr(pdf_path, dpi=300):
    """Yield (page_number, bgr_image) rendering each PDF page at ``dpi``."""
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


def collect_pages(source, dpi=300):
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

def save_bgr_pages_as_pdf(pages_bgr, output_pdf, jpeg_quality=90):
    """Write BGR pages to a PDF, one page per image, original pixel sizes."""
    if pymupdf is None:
        raise ImportError("pymupdf is required for PDF output (pip install pymupdf)")
    if not pages_bgr:
        raise ValueError("no pages to write")
    os.makedirs(os.path.dirname(os.path.abspath(output_pdf)), exist_ok=True)
    doc = pymupdf.open()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for i, page in enumerate(pages_bgr):
                ok, buf = cv.imencode(
                    ".jpg", page, [int(cv.IMWRITE_JPEG_QUALITY), jpeg_quality]
                )
                if not ok:
                    raise RuntimeError(f"JPEG encoding failed for page {i}")
                tmp_path = os.path.join(tmp, f"page_{i:04d}.jpg")
                with open(tmp_path, "wb") as fh:
                    fh.write(buf.tobytes())
                h, w = page.shape[:2]
                pdf_page = doc.new_page(width=w, height=h)
                pdf_page.insert_image(
                    pymupdf.Rect(0, 0, w, h), filename=tmp_path
                )
        doc.save(output_pdf, garbage=4, deflate=True)
    finally:
        doc.close()
    return output_pdf


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def scan_pdf_to_reference(input_path, output_pdf, dpi=300, images_out=None,
                          jpeg_quality=90, no_trim=False, **scan_kwargs):
    """Scan ``input_path`` (PDF / image / dir) to reference quality.

    Returns the output PDF path. When ``images_out`` is given, each scanned
    page is also written there as ``page_0001.jpg`` etc.
    """
    pages = collect_pages(input_path, dpi=dpi)
    if not pages:
        raise ValueError(f"no pages found in: {input_path}")
    scanned = []
    for i, page in enumerate(pages):
        print(f"scanning page {i + 1}/{len(pages)} ({page.shape[1]}x{page.shape[0]}) ...")
        out = scan_photo_to_reference(page, trim=not no_trim, **scan_kwargs)
        scanned.append(out)
        if images_out:
            os.makedirs(images_out, exist_ok=True)
            cv.imwrite(
                os.path.join(images_out, f"page_{i + 1:04d}.jpg"),
                out,
                [int(cv.IMWRITE_JPEG_QUALITY), jpeg_quality],
            )
    save_bgr_pages_as_pdf(scanned, output_pdf, jpeg_quality=jpeg_quality)
    print(f"done: {len(scanned)} page(s) -> {output_pdf}")
    return output_pdf


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Convert PDF photos to reference-quality scans."
    )
    parser.add_argument("input", help="input .pdf, image, or image directory")
    parser.add_argument("output", help="output scanned .pdf path")
    parser.add_argument("--dpi", type=int, default=300,
                        help="render DPI for PDF input (default 300)")
    parser.add_argument("--images-out", default=None,
                        help="optional dir to also write scanned page images")
    parser.add_argument("--jpeg-quality", type=int, default=90)
    parser.add_argument("--no-trim", action="store_true",
                        help="disable edge-trim fallback for full-frame photos")
    parser.add_argument("--no-reframe", action="store_true",
                        help="disable reference-margin re-framing")
    parser.add_argument("--output-scale", type=float, default=2.0,
                        help="upscale factor for scanned pages (default 2.0)")
    parser.add_argument("--white-point", type=float, default=None)
    parser.add_argument("--black-point", type=float, default=None)
    args = parser.parse_args(argv)

    kwargs = {}
    if args.white_point is not None:
        kwargs["white_point"] = args.white_point
    if args.black_point is not None:
        kwargs["black_point"] = args.black_point
    scan_pdf_to_reference(
        args.input, args.output, dpi=args.dpi, images_out=args.images_out,
        jpeg_quality=args.jpeg_quality, no_trim=args.no_trim,
        reframe=not args.no_reframe, output_scale=args.output_scale,
        **kwargs,
    )


if __name__ == "__main__":
    main()
