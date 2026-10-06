"""Unit tests for the scanner domain (geometry, photometry, image I/O).

These are deliberately small and fast: they assert behaviour that another
change could plausibly break (coordinate order, no-op paths, monotonic tone
changes), NOT the algorithm's exact pixels. Exact pixels are the parity
suite's job (tests/parity + tests/fixtures).
"""

import json
import os
import unittest

import cv2 as cv
import numpy as np

from rscan.scanner import image_io, photometry
from rscan.scanner.constants import (
    DEFAULT_BLACK_POINT,
    DEFAULT_BLACK_POINT2,
    DEFAULT_WHITE_POINT,
    REF_ASPECT_FALLBACK,
    REF_CANVAS_MAX_PIXELS,
)
from rscan.scanner.geometry import (
    deskew,
    estimate_skew_angle,
    order_points,
    probe_gray,
    warp_to_rectangle,
)
from rscan.scanner.pipeline import scan_photo_to_reference
from rscan.scanner.postprocessing import reframe_like_reference


def make_page(width=320, height=440, tilt_deg=0.0):
    """Synthetic note photo: grey paper, dark text bars, optional tilt."""
    page = np.full((height, width, 3), 225, np.uint8)
    for y in range(40, height - 40, 30):
        page[y:y + 8, 40:width - 40] = 35
    if tilt_deg:
        m = cv.getRotationMatrix2D((width / 2, height / 2), tilt_deg, 1.0)
        page = cv.warpAffine(page, m, (width, height), flags=cv.INTER_CUBIC,
                             borderMode=cv.BORDER_CONSTANT, borderValue=(240, 240, 240))
    return page


class GeometryTest(unittest.TestCase):
    def test_order_points_returns_tl_tr_br_bl(self):
        pts = np.array([[10, 10], [90, 10], [90, 90], [10, 90]], dtype="float32")
        ordered = order_points(pts[[2, 3, 1, 0]])  # shuffled on purpose
        self.assertEqual(ordered.tolist(), [[10, 10], [90, 10], [90, 90], [10, 90]])

    def test_warp_to_rectangle_maps_a_quad_to_a_rectangle(self):
        image = np.zeros((100, 200, 3), np.uint8)
        corners = np.array([[20, 10], [180, 20], [170, 90], [30, 80]], dtype="float32")
        warped = warp_to_rectangle(image, corners)
        self.assertEqual(warped.ndim, 3)
        self.assertGreater(warped.shape[0], 0)
        self.assertGreater(warped.shape[1], 0)

    def test_probe_gray_downsizes_wide_images_and_reports_scale(self):
        wide = np.zeros((600, 4000, 3), np.uint8)
        probe, scale = probe_gray(wide, target_width=1000)
        self.assertEqual(probe.shape[1], 1000)
        self.assertAlmostEqual(scale, 0.25, places=6)
        self.assertEqual(probe.ndim, 2)

    def test_probe_gray_keeps_small_images_unchanged(self):
        small = np.zeros((200, 300, 3), np.uint8)
        probe, scale = probe_gray(small, target_width=1000)
        self.assertEqual(probe.shape, (200, 300))
        self.assertEqual(scale, 1.0)

    def test_deskew_is_a_no_op_for_a_straight_page(self):
        page = make_page()
        self.assertIs(deskew(page, 0.0), page)

    def test_estimate_skew_angle_is_zero_for_a_straight_page(self):
        self.assertEqual(estimate_skew_angle(make_page()), 0.0)

    def test_residual_and_enhanced_paths_never_raise_on_blank_pages(self):
        blank = np.full((200, 150, 3), 255, np.uint8)
        scanned = scan_photo_to_reference(blank, output_scale=1.0)
        self.assertEqual(scanned.ndim, 3)
        self.assertGreater(scanned.size, 0)


class PhotometryTest(unittest.TestCase):
    def test_odd_kernel_is_odd_and_clamped(self):
        self.assertEqual(photometry.odd_kernel(10) % 2, 1)
        self.assertLessEqual(photometry.odd_kernel(100000), 101)
        self.assertGreaterEqual(photometry.odd_kernel(1), 21)

    def test_high_pass_flatten_preserves_shape_and_range(self):
        image = make_page()
        flat = photometry.high_pass_flatten(image, ksize=21)
        self.assertEqual(flat.shape, image.shape)
        self.assertEqual(flat.dtype, np.uint8)

    def test_white_point_stretch_pushes_highlights_to_white(self):
        image = np.full((10, 10, 3), 200, np.uint8)
        stretched = photometry.white_point_stretch(image, 127)
        self.assertTrue((stretched == 255).all())

    def test_black_point_stretch_is_identity_at_zero(self):
        image = make_page(40, 40)
        self.assertIs(photometry.black_point_stretch(image, 0), image)

    def test_black_point_stretch_darkens_midtones(self):
        image = np.full((4, 4, 3), 100, np.uint8)
        stretched = photometry.black_point_stretch(image, DEFAULT_BLACK_POINT)
        self.assertTrue((stretched < 100).all())

    def test_auto_black_point_stays_inside_the_safe_window(self):
        for image in (np.full((50, 50, 3), 255, np.uint8),
                      np.full((50, 50, 3), 0, np.uint8),
                      make_page()):
            value = photometry.auto_black_point(image)
            self.assertGreaterEqual(value, 10)
            self.assertLessEqual(value, 120)

    def test_enhance_reference_look_whitens_paper_and_darkens_ink(self):
        page = make_page()
        enhanced = photometry.enhance_reference_look(page)
        self.assertEqual(enhanced.shape, page.shape)
        self.assertGreater(enhanced.mean(), page.mean())
        # Ink must stay dark while paper turns white.
        paper = enhanced[5, 5].mean()
        ink_rows = enhanced[40:48, 60:200]
        self.assertGreater(paper, 200)
        self.assertLess(float(ink_rows.mean()), 120)

    def test_saturation_of_one_is_a_no_op_path(self):
        page = make_page(40, 40)
        with_sat = photometry.enhance_reference_look(page, saturate=1.0)
        self.assertEqual(with_sat.shape, page.shape)

    def test_defaults_are_the_documented_parity_constants(self):
        self.assertEqual(DEFAULT_WHITE_POINT, 127)
        self.assertEqual(DEFAULT_BLACK_POINT, 66)
        self.assertEqual(DEFAULT_BLACK_POINT2, 20)
        self.assertAlmostEqual(REF_ASPECT_FALLBACK, 893.0 / 1263.0)


class ImageIoTest(unittest.TestCase):
    def test_decode_jpeg_roundtrip(self):
        page = make_page()
        ok, buf = cv.imencode(".jpg", page)
        self.assertTrue(ok)
        decoded = image_io.decode_image_bytes(buf.tobytes())
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded.shape, page.shape)

    def test_decode_returns_none_for_garbage(self):
        self.assertIsNone(image_io.decode_image_bytes(b"this is not an image"))

    def test_encode_jpeg_returns_bytes(self):
        data = image_io.encode_jpeg(make_page(), quality=90)
        self.assertIsInstance(data, bytes)
        self.assertGreater(len(data), 100)

    def test_scan_photo_to_reference_rejects_empty_input(self):
        with self.assertRaises(ValueError):
            scan_photo_to_reference(None)


def make_receipt(width=400, height=8000):
    """Canonical long-receipt page (the canvas-budget regression input).

    Integer-only content so ``tests/parity/parity_receipt.js`` can mirror it
    byte-for-byte without committing multi-MB pixel fixtures. Keep the two
    generators identical.
    """
    page = np.full((height, width, 3), 235, np.uint8)
    for y in range(100, height - 100, 52):
        page[y:y + 14, 60:340] = 40
    page[60:64, 20:380] = (235, 130, 235)
    return page


RECEIPT_DIMS_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "fixtures", "receipt_dims.json")


class ReframeBudgetTest(unittest.TestCase):
    """A long receipt must not explode the re-framed canvas (browser WASM cap)."""

    def test_receipt_canvas_stays_within_the_pixel_budget(self):
        out = reframe_like_reference(make_receipt(), ref_aspect=REF_ASPECT_FALLBACK)
        h, w = out.shape[:2]
        self.assertLessEqual(h * w, REF_CANVAS_MAX_PIXELS,
                             "extreme-aspect canvas must be capped (parity: JS too)")
        # The uniform downscale keeps the reference aspect.
        self.assertAlmostEqual(w / h, REF_ASPECT_FALLBACK, delta=0.01)

    def test_receipt_dims_match_the_parity_anchor(self):
        with open(RECEIPT_DIMS_JSON, "r", encoding="utf-8") as fh:
            anchor = json.load(fh)
        receipt = make_receipt(anchor["w"], anchor["h"])
        re = reframe_like_reference(receipt, ref_aspect=REF_ASPECT_FALLBACK)
        self.assertEqual([re.shape[1], re.shape[0]], anchor["reframe"])
        full = scan_photo_to_reference(receipt, output_scale=1.0)
        self.assertEqual([full.shape[1], full.shape[0]], anchor["full"])

    def test_normal_page_output_stays_small(self):
        out = reframe_like_reference(make_page(800, 1100),
                                     ref_aspect=REF_ASPECT_FALLBACK)
        h, w = out.shape[:2]
        self.assertLessEqual(h * w, REF_CANVAS_MAX_PIXELS)
        # Reference-ish portrait shape, no degenerate canvas.
        self.assertGreater(w, 400)
        self.assertGreater(h, 400)
        self.assertLess(w / h, 0.9)
        self.assertGreater(w / h, 0.5)


if __name__ == "__main__":
    unittest.main()
