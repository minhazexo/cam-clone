import unittest

import cv2 as cv
import numpy as np

from RScan.Python.scan.auto_scan import REF_MARGIN_TOP, REF_MARGIN_BOTTOM, scan_photo_to_reference


def _ink_bbox(gray, thresh=160):
    ink = gray < thresh
    rows = np.where(ink.any(axis=1))[0]
    cols = np.where(ink.any(axis=0))[0]
    h, w = gray.shape[:2]
    if not len(rows) or not len(cols):
        return (0.0, 1.0, 0.0, 1.0)
    return (rows.min() / h, rows.max() / h, cols.min() / w, cols.max() / w)


class ScanCropTests(unittest.TestCase):
    def test_reference_margins_match_reference_photo(self):
        ref = cv.imread('wiki_images/reference.png', cv.IMREAD_COLOR)
        self.assertIsNotNone(ref)

        gray = cv.cvtColor(ref, cv.COLOR_BGR2GRAY)
        top, bottom, left, right = _ink_bbox(gray, thresh=160)

        self.assertLess(top, 0.025, f'top margin too large: {top}')
        self.assertGreater(bottom, 0.95, f'bottom margin looks wrong: {bottom}')
        self.assertLessEqual(REF_MARGIN_TOP, 0.025, f'expected tighter top margin, got {REF_MARGIN_TOP}')
        self.assertLessEqual(REF_MARGIN_BOTTOM, 0.045, f'expected tighter bottom margin, got {REF_MARGIN_BOTTOM}')

    def test_scan_output_should_not_add_excess_top_bottom_margin(self):
        src = cv.imread('wiki_images/pdf photo..jpg', cv.IMREAD_COLOR)
        self.assertIsNotNone(src)

        out = scan_photo_to_reference(src)
        gray = cv.cvtColor(out, cv.COLOR_BGR2GRAY)
        top, bottom, left, right = _ink_bbox(gray, thresh=160)

        self.assertLess(top, 0.04, f'page is too tall with top margin {top}')
        self.assertGreater(bottom, 0.95, f'page cropping is wrong: bottom {bottom}')


if __name__ == '__main__':
    unittest.main()
