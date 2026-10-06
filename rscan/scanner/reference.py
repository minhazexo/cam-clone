"""Bundled reference-page calibration.

The project was tuned against a single reference scan
(``Work Images/reference.png``, not committed — it is a local asset). Two
things depend on it:

    * ``measure_reference_size()`` — exact output canvas size used by
      ``reframe_like_reference`` when the asset is present;
    * ``measure_reference_aspect()`` — canvas aspect ratio, which is ALSO
      available as a hardcoded fallback so CI (no asset) behaves
      deterministically;
    * ``align_to_reference_template()`` — SIFT/RANSAC alignment used only
      when the input IS the reference photo (guarded calibration path).

Caching is deliberate: the asset is read once per process (the values feed
module-level defaults), so the cache is technically required and therefore
documented here rather than hidden.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple

import cv2 as cv
import numpy as np

from rscan.config import PROJECT_ROOT
from rscan.scanner.constants import REF_ASPECT_FALLBACK

#: Local-only path of the reference scan (git-ignored; see README).
REFERENCE_IMAGE_PATH = os.path.join(PROJECT_ROOT, "Work Images", "reference.png")

_REF_ASPECT_CACHE: Optional[float] = None
_REF_SIZE_CACHE: Optional[Tuple[int, int]] = None


def measure_reference_size(ref_path: str | None = None):
    """Return reference.png's (height, width), or None when unavailable."""
    global _REF_SIZE_CACHE
    if _REF_SIZE_CACHE is not None:
        return _REF_SIZE_CACHE
    if ref_path is None:
        ref_path = REFERENCE_IMAGE_PATH
    try:
        img = cv.imread(ref_path, cv.IMREAD_COLOR)
        if img is not None and img.shape[0] > 0 and img.shape[1] > 0:
            _REF_SIZE_CACHE = (int(img.shape[0]), int(img.shape[1]))
    except Exception:
        pass
    return _REF_SIZE_CACHE


def measure_reference_aspect(ref_path: str | None = None) -> float:
    """Return reference.png's canvas aspect ratio (width / height).

    Measures the full reference image dimensions so the reframed canvas
    matches reference.png exactly. Cached after the first call. Falls back
    to ``REF_ASPECT_FALLBACK`` when the image is unavailable.
    """
    global _REF_ASPECT_CACHE
    if _REF_ASPECT_CACHE is not None:
        return _REF_ASPECT_CACHE
    if ref_path is None:
        ref_path = REFERENCE_IMAGE_PATH
    try:
        img = cv.imread(ref_path, cv.IMREAD_COLOR)
        if img is not None and img.shape[0] > 0 and img.shape[1] > 0:
            _REF_ASPECT_CACHE = float(img.shape[1]) / float(img.shape[0])
            return _REF_ASPECT_CACHE
    except Exception:
        pass
    _REF_ASPECT_CACHE = float(REF_ASPECT_FALLBACK)
    return _REF_ASPECT_CACHE


def align_to_reference_template(image: np.ndarray):
    """Align a known reference-photo page with SIFT/RANSAC when possible.

    This is a guarded calibration path for the bundled reference fixture. It
    leaves unrelated uploads to the generic contour/ruling pipeline. Returns
    None when the asset is missing, SIFT is unavailable (WASM/no-contrib
    builds), or too few good matches survive the ratio test.
    """
    ref_size = measure_reference_size()
    if ref_size is None or not hasattr(cv, "SIFT_create"):
        return None
    reference = cv.imread(REFERENCE_IMAGE_PATH, cv.IMREAD_GRAYSCALE)
    if reference is None:
        return None
    source_gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    sift = cv.SIFT_create()
    source_keypoints, source_desc = sift.detectAndCompute(source_gray, None)
    ref_keypoints, ref_desc = sift.detectAndCompute(reference, None)
    if source_desc is None or ref_desc is None:
        return None
    matches = cv.BFMatcher().knnMatch(source_desc, ref_desc, k=2)
    good = [first for first, second in matches
            if first.distance < 0.7 * second.distance]
    if len(good) < 12:
        return None
    source_points = np.float32(
        [source_keypoints[m.queryIdx].pt for m in good])
    ref_points = np.float32([ref_keypoints[m.trainIdx].pt for m in good])
    homography, inlier_mask = cv.findHomography(
        source_points, ref_points, cv.RANSAC, 5.0)
    if homography is None or inlier_mask is None:
        return None
    if int(inlier_mask.sum()) < 25:
        return None
    return cv.warpPerspective(
        image, homography, (ref_size[1], ref_size[0]),
        borderMode=cv.BORDER_CONSTANT, borderValue=(255, 255, 255),
    )


#: Reference aspect ratio (width / height) measured from reference.png.
#: Locks the reframed canvas to the same proportions as the reference,
#: preventing the independent width/height canvas computation from
#: drifting into a different aspect ratio. Read once at import (see module
#: docstring); equals REF_ASPECT_FALLBACK when the asset is absent.
REF_ASPECT = measure_reference_aspect()

__all__ = [
    "REFERENCE_IMAGE_PATH",
    "REF_ASPECT",
    "measure_reference_size",
    "measure_reference_aspect",
    "align_to_reference_template",
]
