"""Preprocessing: scale-invariant grayscale probes and ink masks.

These two helpers are shared by every geometry estimator, so they live below
``geometry.py`` in the dependency order. Both are deterministic and pure.

Parity note: mirrored as ``probeGray`` / ``adaptiveInkMask`` in
``static/js/workers/scan-geometry.js``. Kernel sizes derive from the probe
width, so changing ``target_width`` moves both implementations together only
if the same value is used there.
"""

from __future__ import annotations

import cv2 as cv
import numpy as np


def probe_gray(image: np.ndarray, target_width: int = 1000) -> tuple[np.ndarray, float]:
    """Grayscale probe scaled to ``target_width`` + the scale factor.

    Scale-invariant estimation: phone photos (~480px) and 300-DPI PDF
    renders (2000px+) are analyzed at the same resolution; fitted
    coordinates are divided by ``scale`` to map back to full resolution.
    """
    gray = cv.cvtColor(image, cv.COLOR_BGR2GRAY)
    if gray.shape[1] > target_width:
        scale = target_width / float(gray.shape[1])
        probe = cv.resize(gray, None, fx=scale, fy=scale,
                          interpolation=cv.INTER_AREA)
        return probe, scale
    return gray, 1.0


def adaptive_ink_mask(probe_blur: np.ndarray) -> np.ndarray:
    """Ink/lines mask robust to uneven lighting (adaptive, inverted).

    Adaptive (not Otsu) thresholds are load-bearing: global thresholds merge
    dense handwriting into blobs under uneven phone-photo lighting, while
    adaptive keeps thin rulings separable.
    """
    pw = probe_blur.shape[1]
    block = max(21, int(pw // 15))
    if block % 2 == 0:
        block += 1
    block = min(block, 101)
    return cv.adaptiveThreshold(
        probe_blur, 255, cv.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv.THRESH_BINARY_INV, block, 7,
    )


__all__ = ["probe_gray", "adaptive_ink_mask"]
