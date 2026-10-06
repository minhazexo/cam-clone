"""Photometry stage: turn a rectified photo into reference-quality pixels.

Pipeline position: runs SECOND, after geometry, on the warped/deskewed page.

    1. high_pass_flatten   remove illumination gradients (img - blur + 127)
    2. optional saturation slight chroma boost so colored ink survives
    3. white-point stretch truncate highlights, stretch to pure white
    4. black-point stretch run twice (66 then 20) to deepen ink

All math is per BGR channel, which is why colored headings keep their hue.
Every constant comes from ``rscan.scanner.constants`` and is parity-sensitive:
the JS mirror is ``enhanceReferenceLook`` in
``static/js/workers/scan-worker-v2.js``.
"""

from __future__ import annotations

import cv2 as cv
import numpy as np

from rscan.scanner.constants import (
    DEFAULT_BLACK_POINT,
    DEFAULT_BLACK_POINT2,
    DEFAULT_KSIZE_DIVISOR,
    DEFAULT_SATURATE,
    DEFAULT_WHITE_POINT,
    KERNEL_MAX_SIZE,
    KERNEL_MIN_SIZE,
)


def odd_kernel(min_dim: int, divisor: int = DEFAULT_KSIZE_DIVISOR,
               minimum: int = KERNEL_MIN_SIZE,
               maximum: int = KERNEL_MAX_SIZE) -> int:
    """Kernel size for illumination flattening: odd, clamped, size-scaled."""
    ksize = max(minimum, int(min_dim // divisor))
    ksize = min(maximum, ksize)
    if ksize % 2 == 0:
        ksize += 1
    return ksize


def high_pass_flatten(image: np.ndarray, ksize: int | None = None) -> np.ndarray:
    """Flatten uneven lighting: img - background + 127, per channel."""
    if ksize is None:
        h, w = image.shape[:2]
        ksize = odd_kernel(min(h, w))
    if ksize % 2 == 0:
        ksize += 1
    kernel = np.ones((ksize, ksize), np.float32) / float(ksize * ksize)
    background = cv.filter2D(image, -1, kernel)
    flat = (
        image.astype(np.float32) - background.astype(np.float32) + 127.0
    )
    return np.clip(flat, 0, 255).astype(np.uint8)


def white_point_stretch(image: np.ndarray,
                        white_point: float = DEFAULT_WHITE_POINT) -> np.ndarray:
    """TRUNC highlights above white_point, then stretch [0, wp] -> [0, 255]."""
    white_point = float(np.clip(white_point, 1, 255))
    _, truncated = cv.threshold(image, white_point, 255, cv.THRESH_TRUNC)
    return np.clip(
        truncated.astype(np.float32) * (255.0 / white_point), 0, 255
    ).astype(np.uint8)


def black_point_stretch(image: np.ndarray,
                        black_point: float = DEFAULT_BLACK_POINT) -> np.ndarray:
    """Push shadows to black: (img - bp) * 255 / (255 - bp)."""
    black_point = float(np.clip(black_point, 0, 254))
    if black_point <= 0:
        return image
    return np.clip(
        (image.astype(np.float32) - black_point)
        * (255.0 / (255.0 - black_point)),
        0,
        255,
    ).astype(np.uint8)


def auto_black_point(image: np.ndarray, pct: float = 8.0) -> float:
    """Pick a black point from the dark-text tail of the histogram.

    After white-point stretching the background is ~255. Reference scans
    (CamScanner) carry deep blacks through ~5-10% of pixels, so the point
    tracks a higher percentile than just the darkest cores; clamped so
    blank pages cannot blow out.
    """
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    value = float(np.percentile(gray, pct))
    return float(np.clip(value, 10, 120))


def enhance_reference_look(image: np.ndarray, ksize: int | None = None,
                           white_point: float | None = None,
                           black_point: float | None = None,
                           black_point2: float | None = None,
                           saturate: float = DEFAULT_SATURATE) -> np.ndarray:
    """Photometric pass that reproduces the reference's white background.

    Per-channel mirror of the original RScan GCMODE: HPF flattens the
    illumination, highlights are truncated/stretched to pure white, then a
    black stretch (done twice) pushes ink cores near-black. Runs per BGR
    channel so colored ink (blue headings, colored markings) keeps its hue,
    which is why the reference.png still shows color. Optional saturation
    boost amplifies faint colored ink the same way the reference shows it.

    Note: the white/black point math is intentionally inlined here (instead
    of calling the helpers above) to keep the float pipeline identical to the
    original implementation and the JS port.
    """
    ksize = KERNEL_MAX_SIZE if ksize is None else ksize
    flat = high_pass_flatten(image, ksize=ksize)
    if flat.ndim == 3 and abs(saturate - 1.0) > 1e-6:
        b, g, r = cv.split(flat.astype(np.float32))
        lum = (r + g + b) / 3.0
        flat = cv.merge([lum + (b - lum) * saturate,
                         lum + (g - lum) * saturate,
                         lum + (r - lum) * saturate])
    wp = DEFAULT_WHITE_POINT if white_point is None else float(white_point)
    _, truncated = cv.threshold(flat, wp, 255, cv.THRESH_TRUNC)
    out = np.clip(truncated.astype(np.float32) * (255.0 / wp), 0, 255)
    bp = DEFAULT_BLACK_POINT if black_point is None else float(black_point)
    out = np.clip((out - bp) * (255.0 / (255.0 - bp)), 0, 255)
    bp2 = DEFAULT_BLACK_POINT2 if black_point2 is None else float(black_point2)
    out = np.clip((out - bp2) * (255.0 / (255.0 - bp2)), 0, 255)
    _, out = cv.threshold(out, 0, 255, cv.THRESH_TOZERO)
    return out.astype(np.uint8)


__all__ = [
    "odd_kernel",
    "high_pass_flatten",
    "white_point_stretch",
    "black_point_stretch",
    "auto_black_point",
    "enhance_reference_look",
]
