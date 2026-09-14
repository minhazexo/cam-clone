import io
import os
import unittest
from unittest.mock import patch

import cv2 as cv
import numpy as np

from app import app
from RScan.Python.scan.auto_scan import REF_MARGIN_TOP, REF_MARGIN_BOTTOM, scan_photo_to_reference
from RScan.Python.scan.scan_pdf import scan_pdf_to_reference


def _ink_bbox(gray, thresh=160):
    ink = gray < thresh
    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    h, w = gray.shape[:2]
    if not len(rows) or not len(cols):
        return (0.0, 1.0, 0.0, 1.0)
    return (rows.min() / h, rows.max() / h, cols.min() / w, cols.max() / w)


class ScanCropTests(unittest.TestCase):
    def test_api_scan_deduplicates_identical_files_in_one_request(self):
        image_path = os.path.join(os.path.dirname(__file__), "IMG-20260905-WA0005.jpg")
        self.assertTrue(os.path.exists(image_path), image_path)

        with open(image_path, "rb") as fh:
            image_bytes = fh.read()

        client = app.test_client()
        payload = {
            "files": [
                (io.BytesIO(image_bytes), "IMG-20260905-WA0005.jpg"),
                (io.BytesIO(image_bytes), "IMG-20260905-WA0005.jpg"),
            ]
        }
        resp = client.post("/api/scan", data=payload, content_type="multipart/form-data", follow_redirects=False)
        self.assertEqual(resp.status_code, 200, resp.get_data(as_text=True))
        pages = resp.get_json().get("pages", [])
        self.assertEqual(len(pages), 1)

    def test_scan_pdf_to_reference_honors_page_limit(self):
        fake_pages = [np.zeros((10, 10, 3), dtype=np.uint8) for _ in range(12)]

        with patch("RScan.Python.scan.scan_pdf.collect_pages", return_value=fake_pages), \
             patch("RScan.Python.scan.scan_pdf.scan_photo_to_reference", return_value=np.zeros((10, 10, 3), dtype=np.uint8)), \
             patch("RScan.Python.scan.scan_pdf.save_bgr_pages_as_pdf") as save_pdf:
            scan_pdf_to_reference("input.pdf", "output.pdf", page_limit=10)

        saved_pages = save_pdf.call_args.args[0]
        self.assertEqual(len(saved_pages), 10)

    def test_reference_margins_match_reference_photo(self):
        ref = cv.imread('Work Images/reference.png', cv.IMREAD_COLOR)
        self.assertIsNotNone(ref)

        gray = cv.cvtColor(ref, cv.COLOR_BGR2GRAY)
        top, bottom, left, right = _ink_bbox(gray, thresh=160)

        self.assertLess(top, 0.025, f'top margin too large: {top}')
        self.assertGreater(bottom, 0.95, f'bottom margin looks wrong: {bottom}')
        self.assertLessEqual(REF_MARGIN_TOP, 0.08, f'expected reference top margin, got {REF_MARGIN_TOP}')
        self.assertLessEqual(REF_MARGIN_BOTTOM, 0.055, f'expected reference bottom margin, got {REF_MARGIN_BOTTOM}')

    def test_scan_output_should_not_add_excess_top_bottom_margin(self):
        src = cv.imread('Work Images/pdf photo..jpg', cv.IMREAD_COLOR)
        self.assertIsNotNone(src)

        out = scan_photo_to_reference(src)
        gray = cv.cvtColor(out, cv.COLOR_BGR2GRAY)
        top, bottom, left, right = _ink_bbox(gray, thresh=160)

        self.assertLess(top, 0.08, f'page is too tall with top margin {top}')
        self.assertGreater(bottom, 0.95, f'page cropping is wrong: bottom {bottom}')


if __name__ == '__main__':
    unittest.main()
