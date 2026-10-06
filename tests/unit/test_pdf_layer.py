"""Unit tests for the PDF layer (assembler + service helpers)."""

import tempfile
import unittest
from pathlib import Path

import cv2 as cv
import numpy as np

from rscan.pdf.assembler import PAGE_SIZES, draw_page_border, save_bgr_pages_as_pdf
from rscan.pdf.pdf_service import scan_pdf_page_images
from rscan.scanner.constants import REF_ASPECT_FALLBACK


def make_pages(count=2, width=120, height=170):
    return [np.full((height, width, 3), 240, np.uint8) for _ in range(count)]


class AssemblerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="rscan_pdf_"))

    def test_draw_page_border_paints_an_inset_frame(self):
        page = make_pages(1, 100, 100)[0]
        bordered = draw_page_border(page)
        # The frame is inset so that it stays fully visible: the very corner
        # keeps the page colour while the frame sits one stroke width inside.
        self.assertGreater(int(bordered[0, 0].mean()), 200)
        self.assertLess(int(bordered[3, 50].mean()), 128)
        self.assertGreater(int(bordered[50, 50].mean()), 200)

    def test_draw_page_border_thickness_scales_with_size(self):
        def stroke_width(size):
            """Count consecutive dark pixels inward from the left edge."""
            page = draw_page_border(np.full((size, size, 3), 255, np.uint8))
            column = page[:, size // 2]
            width = 0
            for row in column:
                if row.mean() < 128:
                    width += 1
                elif width:
                    break
            return width

        # ~0.3% of the short side, minimum 3px -> thicker on large pages.
        small = stroke_width(100)
        large = stroke_width(2000)
        self.assertGreaterEqual(small, 3)
        self.assertGreater(large, small)

    def test_save_bgr_pages_as_pdf_writes_a4_pages(self):
        output = self.tmp / "out.pdf"
        save_bgr_pages_as_pdf(make_pages(2), str(output), jpeg_quality=70)
        self.assertTrue(output.is_file())

        import pymupdf

        doc = pymupdf.open(output)
        try:
            self.assertEqual(doc.page_count, 2)
            page = doc[0]
            self.assertAlmostEqual(page.rect.width, PAGE_SIZES["A4"][0], delta=1)
            self.assertAlmostEqual(page.rect.height, PAGE_SIZES["A4"][1], delta=1)
        finally:
            doc.close()

    def test_save_bgr_pages_as_pdf_matches_landscape_orientation(self):
        landscape = [np.full((120, 300, 3), 240, np.uint8)]
        output = self.tmp / "wide.pdf"
        save_bgr_pages_as_pdf(landscape, str(output))
        import pymupdf

        doc = pymupdf.open(output)
        try:
            self.assertGreater(doc[0].rect.width, doc[0].rect.height)
        finally:
            doc.close()

    def test_legacy_page_size_none_keeps_pixel_sized_pages(self):
        page = make_pages(1, 100, 150)[0]
        output = self.tmp / "legacy.pdf"
        save_bgr_pages_as_pdf([page], str(output), page_size=None)
        import pymupdf

        doc = pymupdf.open(output)
        try:
            self.assertAlmostEqual(doc[0].rect.width, 100, delta=1)
            self.assertAlmostEqual(doc[0].rect.height, 150, delta=1)
        finally:
            doc.close()

    def test_empty_page_list_is_rejected(self):
        with self.assertRaises(ValueError):
            save_bgr_pages_as_pdf([], str(self.tmp / "empty.pdf"))


class PdfServiceTest(unittest.TestCase):
    def test_scan_pdf_page_images_scans_each_page(self):
        pages = make_pages(2)
        scanned = scan_pdf_page_images(pages)
        self.assertEqual(len(scanned), 2)
        for original, result in zip(pages, scanned):
            self.assertEqual(result.ndim, 3)
            self.assertGreater(result.size, 0)

    def test_scan_pdf_page_images_reframes_to_the_reference_aspect(self):
        page = make_pages(1, 160, 220)[0]
        scanned = scan_pdf_page_images([page], output_scale=1.0)[0]
        # The pipeline re-frames every page onto a reference-aspect canvas, so
        # dimensions change but the aspect ratio is constrained.
        height, width = scanned.shape[:2]
        self.assertAlmostEqual(width / height, REF_ASPECT_FALLBACK, delta=0.05)


if __name__ == "__main__":
    unittest.main()
